import glob
import os
import pwd
import subprocess

# mesmos diretórios que a migração nativa (issabel_migration.sh) e os
# restores do pvx tocam -- se algum desses não for gravável pelo usuário
# asterisk, backup/restore/CDR/astdb quebram de formas bem diferentes e
# difíceis de relacionar na hora (achado ao vivo, 2026-10).
ASTERISK_PATHS = (
    "/var/lib/asterisk",
    "/etc/asterisk",
    "/var/spool/asterisk",
    "/var/www/db",
    "/var/www/backup",
)
ASTERISK_USER = "asterisk"
ASTDB_PATH = "/var/lib/asterisk/astdb.sqlite3"
_TEST_KEY = "_pvx_health_check"


class CheckResult:
    def __init__(self, name, passed, detail=""):
        self.name = name
        self.passed = passed
        self.detail = detail


def _run(args):
    return subprocess.run(args, capture_output=True, text=True)


# achado ao vivo: um restore pode deixar o Asterisk com uma conexão presa no
# astdb.sqlite3 antigo (db.c ast_db_put: SQL logic error) mesmo com o
# arquivo no disco já correto -- put+get+del aqui é o teste funcional de
# verdade, não só olhar o arquivo.
def check_astdb_write():
    put = _run(["asterisk", "-rx", f"database put {_TEST_KEY} teste valor"])
    get = _run(["asterisk", "-rx", f"database get {_TEST_KEY} teste"])
    _run(["asterisk", "-rx", f"database del {_TEST_KEY} teste"])

    if "Updated database successfully" not in put.stdout:
        detail = (put.stderr or put.stdout or "").strip() or "put falhou sem detalhe"
        return CheckResult("astdb_write", False, detail)
    if "valor" not in get.stdout:
        return CheckResult("astdb_write", False, f"valor gravado não foi lido de volta: {get.stdout.strip()}")
    return CheckResult("astdb_write", True)


def _sqlite_integrity(path):
    result = _run(["sqlite3", path, "PRAGMA integrity_check;"])
    if result.returncode != 0:
        return False, (result.stderr or "falha ao abrir o arquivo").strip()
    output = result.stdout.strip()
    return output == "ok", output


# PRAGMA integrity_check confere estrutura de página -- não é o mesmo teste
# que check_astdb_write (que confere se a ESCRITA funciona de verdade).
# Também confere os outros .db do Issabel (acl.db, settings.db, etc. --
# mesmos que issabel_migration.sh restaura em /var/www/db).
def check_astdb_integrity():
    paths = [ASTDB_PATH] + sorted(glob.glob("/var/www/db/*.db"))
    problems = []
    for path in paths:
        if not os.path.isfile(path):
            continue
        ok, detail = _sqlite_integrity(path)
        if not ok:
            problems.append(f"{path}: {detail}")
    if problems:
        return CheckResult("astdb_integrity", False, "; ".join(problems))
    return CheckResult("astdb_integrity", True)


def check_odbc():
    result = _run(["asterisk", "-rx", "odbc show"])
    if result.returncode != 0:
        return CheckResult("odbc", False, (result.stderr or result.stdout or "comando falhou").strip())

    disconnected = []
    current_dsn = None
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("Name:"):
            current_dsn = line.split(":", 1)[1].strip()
        elif line.startswith("Connected:") and "No" in line:
            disconnected.append(current_dsn or "?")

    if disconnected:
        return CheckResult("odbc", False, f"DSN(s) desconectado(s): {', '.join(disconnected)}")
    return CheckResult("odbc", True)


def check_asterisk_paths():
    try:
        expected_uid = pwd.getpwnam(ASTERISK_USER).pw_uid
    except KeyError:
        return CheckResult("asterisk_paths", False, f"usuário {ASTERISK_USER} não existe")

    problems = []
    for path in ASTERISK_PATHS:
        if not os.path.isdir(path):
            problems.append(f"{path}: não existe")
            continue
        st = os.stat(path)
        if st.st_uid != expected_uid:
            owner = pwd.getpwuid(st.st_uid).pw_name
            problems.append(f"{path}: dono é {owner}, esperado {ASTERISK_USER}")
        elif not st.st_mode & 0o200:
            problems.append(f"{path}: sem permissão de escrita pro dono")
    if problems:
        return CheckResult("asterisk_paths", False, "; ".join(problems))
    return CheckResult("asterisk_paths", True)


CHECKS = {
    "astdb_write": check_astdb_write,
    "astdb_integrity": check_astdb_integrity,
    "odbc": check_odbc,
    "asterisk_paths": check_asterisk_paths,
}


def run_checks(names=None):
    names = list(names) if names else list(CHECKS)
    return [CHECKS[name]() for name in names]
