import secrets
import string
import subprocess


def mem_total_kb(path="/proc/meminfo"):
    # soma RAM+swap TOTAL, não livre -- swap alocável é o que importa pro risco de OOM,
    # já usado ou não no momento da checagem. 0 (não bloqueia nada) se o arquivo não existir.
    try:
        lines = open(path).read().splitlines()
    except OSError:
        return 0

    mem_total = swap_total = 0
    for line in lines:
        key, _, rest = line.partition(":")
        if key == "MemTotal":
            mem_total = int(rest.split()[0])
        elif key == "SwapTotal":
            swap_total = int(rest.split()[0])
    return mem_total + swap_total


def gen_password(length=24):
    # senha aleatória por instalação -- nunca um default fixo/compartilhado entre máquinas.
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def run_cmd(args):
    return subprocess.run(args, capture_output=True, text=True).returncode == 0


def pkg_install(packages):
    # tenta a lista inteira num único dnf install (paga o custo de metadata uma vez só); se
    # a transação em lote falhar (típico: um nome de pacote não existe mais no repo), cai pra
    # instalação pacote a pacote, isolando só o(s) problemático(s) em vez de perder a lista
    # inteira por causa de um nome só.
    if not packages:
        return []
    if run_cmd(["dnf", "install", "-y", *packages]):
        return []

    failed = []
    for pkg in packages:
        if not run_cmd(["dnf", "install", "-y", pkg]):
            failed.append(pkg)
    return failed
