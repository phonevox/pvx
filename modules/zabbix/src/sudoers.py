import os

HEADER = "# gerenciado pelo pvx zabbix -- não editar à mão, use `pvx zabbix script add/remove`\n"


def write_rules(path, user, commands):
    # sobrescreve o arquivo inteiro a cada chamada -- fonte de verdade é sempre a lista
    # de comandos que precisam de root (scripts.py), nunca acesso amplo tipo
    # "ALL=(ALL) NOPASSWD: ALL" (era assim no script bash antigo, o próprio autor não
    # gostava disso). Cada script pede sudo só pro comando exato que ele roda.
    if not commands:
        remove(path)
        return

    lines = [HEADER]
    for command in commands:
        lines.append(f"{user} ALL=(root) NOPASSWD: {command}\n")
    open(path, "w").write("".join(lines))
    os.chmod(path, 0o440)  # sudoers.d exige 440, senão sudo ignora o arquivo


def remove(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


# rastro do pzabbix (script bash antigo): ele acrescentava essa linha direto no
# /etc/sudoers principal -- acesso root irrestrito pro usuário zabbix, nunca escopado
# num arquivo em sudoers.d como o pvx faz (ver write_rules() acima).
LEGACY_FILE = "/etc/sudoers"
LEGACY_LINE = "%zabbix ALL=(ALL) NOPASSWD: ALL"


def detect_legacy_rule(path=LEGACY_FILE):
    try:
        content = open(path).read()
    except OSError:
        return False
    return any(line.strip() == LEGACY_LINE for line in content.splitlines())


def remove_legacy_rule(path=LEGACY_FILE):
    try:
        lines = open(path).read().splitlines()
    except OSError:
        return False
    kept = [line for line in lines if line.strip() != LEGACY_LINE]
    if len(kept) == len(lines):
        return False
    open(path, "w").write("\n".join(kept) + "\n")
    return True
