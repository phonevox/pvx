import os


def read_params(path):
    try:
        lines = open(path).read().splitlines()
    except OSError:
        return {}

    params = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, sep, value = stripped.partition("=")
        if sep:
            params[key] = value
    return params


def ensure_include(path, confd_dir):
    # garante Include=<confd_dir>/*.conf no config principal -- é o que faz o Zabbix ler
    # os UserParameter de scripts customizados (scripts.py), sem precisar mexer no
    # arquivo principal de novo a cada script adicionado.
    directive = f"Include={confd_dir}/*.conf"
    try:
        content = open(path).read()
    except OSError:
        raise FileNotFoundError(f"arquivo de configuração não encontrado: {path}")

    # zabbix_agent2 recusa subir se o diretório do glob não existir de verdade
    # ("cannot include ...: no such file or directory") -- criar aqui é o que garante
    # isso pra qualquer distro, mesmo quando o pacote não pré-cria o dir.
    os.makedirs(confd_dir, exist_ok=True)

    if directive in content:
        return
    with open(path, "a") as f:
        if content and not content.endswith("\n"):
            f.write("\n")
        f.write(directive + "\n")


def set_params(path, values):
    # idempotente: parâmetro já com o valor certo não muda a linha (não gera diff à
    # toa). Duplicado no arquivo é erro real -- ambíguo qual linha é "a certa" (o script
    # bash antigo tinha essa checagem, mas quebrada, nunca barrava nada de fato).
    try:
        lines = open(path).read().splitlines()
    except OSError:
        raise FileNotFoundError(f"arquivo de configuração não encontrado: {path}")

    managed = set(values)
    remaining = dict(values)
    seen = set()
    output = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            key, sep, _ = stripped.partition("=")
            if sep and key in managed:
                if key in seen:
                    raise ValueError(f"parâmetro '{key}' duplicado em {path}")
                seen.add(key)
                output.append(f"{key}={remaining.pop(key)}")
                continue
        output.append(line)

    for key, value in remaining.items():
        output.append(f"{key}={value}")

    open(path, "w").write("\n".join(output) + "\n")
