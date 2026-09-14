import hashlib
import io
import os
import re
import shutil
import subprocess
import tarfile
import tempfile

from known_good_hashes import KNOWN_GOOD_HASHES

# Assinaturas heurísticas de webshell/backdoor -- não é um antivírus
# completo, é o que apareceu de verdade num incidente real numa central
# comprometida (dev/pvxbackup.sh, porta 1:1 pra dentro do pvx).
PHP_SIG_RE = re.compile(
    r"eval\(\$[A-Za-z0-9_]+\(|chr\(1[01][0-9]\)\.chr\(|base64_decode\s*\(|"
    r"gzuncompress\s*\(|str_rot13\s*\(|strrev\s*\(|"
    r"(system|exec|shell_exec|passthru|popen|proc_open)\s*\(\s*\$_(GET|POST|REQUEST|COOKIE|SERVER)"
)
SHELL_SIG_RE = re.compile(
    r"/dev/tcp/|nc\s+-e|bash\s+-i|python\s+-c|perl\s+-e|os\.system\s*\(|"
    r"subprocess\.(Popen|call|run)\s*\(|base64\.b64decode\s*\(|"
    r"(wget|curl)[^;]*\|\s*(bash|sh)\b",
    re.IGNORECASE,
)
DIALPLAN_SIG_RE = re.compile(
    r"(System|TrySystem|Shell)\([^)]*(nc\s+-e|/dev/tcp/|bash\s+-i|wget[^)]*\|\s*sh|"
    r"curl[^)]*\|\s*sh|base64\s+-d|/tmp/|/var/tmp/|/dev/shm/)|"
    r"AGI\([^,)]*(\.\.|/tmp/|/var/tmp/)"
)
KNOWN_BAD_NAMES = {
    "ab.php", "actors.php", "alex.php", "ayeshsalem.php", "Bo.php",
    "c58a155379a0.php", "crmmng.php", "Do.php", "fa.php", "free.php",
    "graph.php", "hamed.php", "hero.php", "italy.php", "jeep.php",
    "jnkp.php", "juba.php", "mae.php", "maf.php", "MeSSi.php", "oBo.php",
    "paloSantoDB.php", "phpversions.php", "rumio.php", "saher.php",
    "SaLeM-123.php", "S!n4.php", "salem.php", "super.php", "uk.php",
    "Ultimatex.php", "usa.php", "W__A__H.php", "config.all.php",
    "configs.php", "domdom.php",
}
SCRIPT_EXTENSIONS = (".agi", ".pl", ".py", ".sh", ".cgi")
DIALPLAN_EXTENSIONS = (".conf", ".ael")

# os 3 blobs de código nativos do backupengine que hospedaram webshell no
# incidente real -- vêm embutidos nas categorias as_db (admin/agi-bin) e
# as_config_files (etc.asterisk), sem como excluir só eles do backup
# nativo. valor = (path real no filesystem, quais extensões escanear).
CODE_BLOBS = {
    "var.www.html.admin.tgz": ("/var/www/html", "php_only"),
    "var.lib.asterisk.agi-bin.tgz": ("/var/lib/asterisk", "scripts"),
    "etc.asterisk.tgz": ("/etc", "full"),
}


class SecurityScanError(Exception):
    pass


class Finding:
    def __init__(self, level, label, path, reason):
        self.level = level  # "suspeito" | "ok"
        self.label = label
        self.path = path
        self.reason = reason

    def __repr__(self):
        return f"Finding({self.level!r}, {self.label!r}, {self.path!r}, {self.reason!r})"

    def __str__(self):
        return f"{self.label} :: {self.path} -- {self.reason}"


def rpm_confirms_clean(abspath, content):
    if not shutil.which("rpm"):
        return False
    pkg_result = subprocess.run(["rpm", "-qf", abspath], capture_output=True, text=True)
    if pkg_result.returncode != 0 or not pkg_result.stdout.strip():
        return False
    pkg = pkg_result.stdout.strip().splitlines()[0]

    algo_result = subprocess.run(
        ["rpm", "-q", "--qf", "%{FILEDIGESTALGO}", pkg], capture_output=True, text=True,
    )
    hasher = {"1": hashlib.md5, "2": hashlib.sha1}.get(algo_result.stdout.strip(), hashlib.sha256)

    files_result = subprocess.run(
        ["rpm", "-q", "--qf", "[%{FILENAMES} %{FILEDIGESTS}\n]", pkg], capture_output=True, text=True,
    )
    for line in files_result.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] == abspath:
            return hasher(content).hexdigest() == parts[1]
    return False


def baseline_confirms_clean(label, rel_path, content):
    expected = KNOWN_GOOD_HASHES.get(f"{label}:{rel_path}")
    return expected is not None and hashlib.sha256(content).hexdigest() == expected


def _scan_signature_file(full_path, rel_path, label, parent, sig_re, reason):
    content = open(full_path, "rb").read()
    known_bad = os.path.basename(full_path) in KNOWN_BAD_NAMES
    matched = bool(sig_re.search(content.decode("utf-8", "replace")))

    if not known_bad and not matched:
        return None

    if matched and not known_bad:
        if parent and rpm_confirms_clean(f"{parent}/{rel_path}", content):
            return Finding("ok", label, rel_path, "bate com o pacote original (rpm)")
        if baseline_confirms_clean(label, rel_path, content):
            return Finding("ok", label, rel_path, "bate com o hash conhecido do Issabel")

    reasons = []
    if known_bad:
        reasons.append("nome conhecido do incidente")
    if matched:
        reasons.append(reason)
    return Finding("suspeito", label, rel_path, " + ".join(reasons))


def _scan_dialplan_file(full_path, rel_path, label):
    findings = []
    with open(full_path, encoding="utf-8", errors="replace") as f:
        for lineno, line in enumerate(f, start=1):
            if DIALPLAN_SIG_RE.search(line):
                findings.append(Finding("suspeito", label, f"{rel_path} (linha {lineno})", line.strip()))
            if len(findings) >= 20:
                break
    return findings


def scan_directory(root_dir, label, parent=None, mode="full"):
    findings = []
    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            full_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(full_path, root_dir)
            ext = os.path.splitext(filename)[1].lower()
            finding = None
            if ext == ".php":
                finding = _scan_signature_file(full_path, rel_path, label, parent, PHP_SIG_RE, "ofuscacao")
            elif mode != "php_only" and ext in SCRIPT_EXTENSIONS:
                finding = _scan_signature_file(
                    full_path, rel_path, label, parent, SHELL_SIG_RE, "shell reverso/exec remoto",
                )
            elif mode == "full" and ext in DIALPLAN_EXTENSIONS:
                findings.extend(_scan_dialplan_file(full_path, rel_path, label))
                continue
            if finding:
                findings.append(finding)
    return findings


# filter="data" (PEP 706) só existe em Python 3.8.17+/3.9.17+/3.12+ -- pvx
# promete 3.8+ genérico, então usa quando dá (silencia o RuntimeWarning novo
# do tarfile) e cai pro extract sem filtro nas versões mais antigas.
_EXTRACT_SUPPORTS_FILTER = "filter" in tarfile.TarFile.extractall.__code__.co_varnames
_EXTRACT_KWARGS = {"filter": "data"} if _EXTRACT_SUPPORTS_FILTER else {}


def _extract_blob(tar, member_name, tmp_dir):
    tar.extract(member_name, path=tmp_dir, **_EXTRACT_KWARGS)  # o próprio .tgz -- sempre arquivo regular
    blob_path = os.path.join(tmp_dir, member_name)
    extract_dir = os.path.join(tmp_dir, "extracted")
    os.makedirs(extract_dir, exist_ok=True)
    with tarfile.open(blob_path) as inner:
        # só arquivo regular -- a varredura só lê conteúdo, nunca segue
        # symlink/device, e o admin/ real do Issabel tem link absoluto
        # legítimo (ex.: admin/assets/recordings -> /var/spool/asterisk/...)
        # que o filtro "data" rejeitaria com erro se tentássemos extrair.
        for member in inner.getmembers():
            if member.isfile():
                inner.extract(member, path=extract_dir, **_EXTRACT_KWARGS)
    return extract_dir


def scan_backup(path):
    findings = []
    blobs_scanned = []
    try:
        with tarfile.open(path) as tar:
            for member_name in tar.getnames():
                base = os.path.basename(member_name)
                if base not in CODE_BLOBS:
                    continue
                blobs_scanned.append(base)
                parent, mode = CODE_BLOBS[base]
                with tempfile.TemporaryDirectory() as tmp_dir:
                    extract_dir = _extract_blob(tar, member_name, tmp_dir)
                    findings.extend(scan_directory(extract_dir, base, parent, mode))
    except (OSError, tarfile.TarError) as e:
        raise SecurityScanError(f"falha ao auditar o backup: {e}")
    return {"findings": findings, "blobs_scanned": blobs_scanned}


def _prune_blob(blob_bytes, rel_paths_to_remove):
    targets = {os.path.normpath(p) for p in rel_paths_to_remove}
    removed = 0
    with tarfile.open(fileobj=io.BytesIO(blob_bytes), mode="r:gz") as src:
        out_buf = io.BytesIO()
        with tarfile.open(fileobj=out_buf, mode="w:gz") as dst:
            for member in src.getmembers():
                if member.isfile() and os.path.normpath(member.name) in targets:
                    removed += 1
                    continue
                data = src.extractfile(member) if member.isfile() else None
                dst.addfile(member, data)
    return out_buf.getvalue(), removed


def prune_backup(path, findings):
    # só arquivo (php/script) é removível de verdade -- achado de dialplan
    # aponta uma LINHA dentro de um .conf que também carrega dialplan
    # legítimo, apagar o arquivo inteiro destruiria configuração real junto.
    by_blob = {}
    for f in findings:
        by_blob.setdefault(f.label, set()).add(f.path)
    if not by_blob:
        return 0

    tmp_path = path + ".pruning"
    removed_total = 0
    try:
        with tarfile.open(path) as src, tarfile.open(tmp_path, "w") as dst:
            for member in src.getmembers():
                base = os.path.basename(member.name)
                if member.isfile() and base in by_blob:
                    blob_bytes = src.extractfile(member).read()
                    new_bytes, removed = _prune_blob(blob_bytes, by_blob[base])
                    removed_total += removed
                    info = tarfile.TarInfo(member.name)
                    info.size = len(new_bytes)
                    info.mtime = member.mtime
                    info.mode = member.mode
                    dst.addfile(info, io.BytesIO(new_bytes))
                else:
                    data = src.extractfile(member) if member.isfile() else None
                    dst.addfile(member, data)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    return removed_total


def verdict(scan_result):
    suspects = [f for f in scan_result["findings"] if f.level == "suspeito"]
    if suspects:
        return "error", f"{len(suspects)} achado(s) suspeito(s) -- revise antes de restaurar, não é fatal por si só."
    if scan_result["blobs_scanned"]:
        return "ok", "nenhum sinal de webshell nos blobs de código analisados."
    return "ok", "backup não inclui blobs de código (as_db/as_config_files) pra analisar."
