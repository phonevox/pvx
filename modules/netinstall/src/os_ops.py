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


def run_cmd(args, on_line=None):
    # bash original roda tudo com "&> /dev/null" sem checar $? -- "command not found"
    # (binário ainda não existe nesse ponto do fluxo, ex.: amportal antes do
    # issabel-firstboot rodar) é falha muda por lá, nunca derruba o script.
    # subprocess.run() levanta FileNotFoundError nesse caso (diferente de "rodou e
    # falhou", já coberto pelo returncode) -- sem isso, o processo inteiro crasha.
    if on_line is None:
        try:
            return subprocess.run(args, capture_output=True, text=True).returncode == 0
        except FileNotFoundError:
            return False

    # on_line dado -- transmite linha por linha assim que sai (docker-build-style),
    # em vez de subprocess.run(capture_output=True) que só entrega tudo no final.
    try:
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    except FileNotFoundError:
        return False
    # lê char a char em vez de "for line in proc.stdout" -- dnf atualiza barra de
    # progresso via "\r" (sem "\n"), e a iteração padrão do arquivo só quebra em "\n",
    # escondendo os updates de progresso até o "\n" de verdade aparecer (ex.: só quando
    # aquele download termina).
    buffer = ""
    for char in iter(lambda: proc.stdout.read(1), ""):
        if char in ("\n", "\r"):
            if buffer:
                on_line(buffer)
                buffer = ""
        else:
            buffer += char
    if buffer:
        on_line(buffer)
    proc.wait()
    return proc.returncode == 0


def pkg_install(packages, on_line=None):
    # tenta a lista inteira num único dnf install (paga o custo de metadata uma vez só); se
    # a transação em lote falhar (típico: um nome de pacote não existe mais no repo), cai pra
    # instalação pacote a pacote, isolando só o(s) problemático(s) em vez de perder a lista
    # inteira por causa de um nome só.
    if not packages:
        return []
    if run_cmd(["dnf", "install", "-y", *packages], on_line=on_line):
        return []

    failed = []
    for pkg in packages:
        if not run_cmd(["dnf", "install", "-y", pkg], on_line=on_line):
            failed.append(pkg)
    return failed
