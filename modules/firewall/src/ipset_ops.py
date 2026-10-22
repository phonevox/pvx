import shutil
import subprocess


def _run(args, check=False):
    return subprocess.run(["ipset"] + args, capture_output=True, text=True, check=check)


def available():
    return shutil.which("ipset") is not None


def exists(name):
    return _run(["list", name]).returncode == 0


def create(name):
    if not exists(name):
        _run(["create", name, "hash:net"])


def destroy(name):
    if exists(name):
        _run(["destroy", name])


def add(name, cidr):
    # -exist: idempotente, não erra se o CIDR já estiver no set.
    _run(["add", name, cidr, "-exist"])


def add_many(name, cidrs):
    # um `ipset restore` só no lugar de um `ipset add` por CIDR (~11k pro BR).
    payload = "".join(f"add {name} {cidr}\n" for cidr in cidrs)
    result = subprocess.run(["ipset", "restore", "-exist"], input=payload, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"falha ao carregar o ipset {name}: {result.stderr.strip()}")


def members(name):
    result = _run(["list", name])
    if result.returncode != 0:
        return []
    lines = result.stdout.splitlines()
    try:
        header_index = lines.index("Members:")
    except ValueError:
        return []
    return [line.strip() for line in lines[header_index + 1:] if line.strip()]


def swap(tmp_name, real_name):
    # troca o CONTEÚDO dos dois sets num passo só -- nunca existe uma janela
    # em que `real_name` está vazio ou com membros parciais. Depois do swap,
    # tmp_name fica com o conteúdo antigo (stale) -- descarta.
    _run(["swap", tmp_name, real_name])
    destroy(tmp_name)


def replace_members(name, cidrs):
    create(name)  # garante que o set final existe (mesmo vazio) -- swap sempre funciona
    tmp_name = f"{name}-new"
    destroy(tmp_name)  # limpa sobra de uma falha anterior, se houver
    create(tmp_name)
    add_many(tmp_name, cidrs)  # se falhar, levanta antes do swap -- o set antigo continua valendo
    swap(tmp_name, name)
