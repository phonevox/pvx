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
