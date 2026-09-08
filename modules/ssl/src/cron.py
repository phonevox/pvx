import subprocess

MARKER = "# gerenciado pelo pvx ssl -- não editar à mão, use `pvx ssl setup`/`pvx ssl remove`"


def read_crontab():
    # `crontab -l` sai com status != 0 quando o usuário nunca teve uma cron --
    # não é erro, é "vazio".
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if result.returncode != 0:
        return []
    return result.stdout.splitlines()


def write_crontab(lines):
    content = "\n".join(lines)
    if content and not content.endswith("\n"):
        content += "\n"
    subprocess.run(["crontab", "-"], input=content, text=True, check=True)


def find_managed_entry(lines):
    for index, line in enumerate(lines):
        if line == MARKER and index + 1 < len(lines):
            return index + 1, lines[index + 1]
    return None


def ensure_scheduled(apache_service):
    # uma única entrada compartilhada pra todo domínio gerenciado por este módulo --
    # "certbot renew" já renova tudo que o certbot conhece, não precisa (e não deve)
    # de uma linha por domínio.
    lines = read_crontab()
    if find_managed_entry(lines) is not None:
        return False
    command = f"0 3 * * * certbot renew --quiet --deploy-hook 'systemctl reload {apache_service}'"
    write_crontab(lines + [MARKER, command])
    return True


def remove_scheduled():
    lines = read_crontab()
    existing = find_managed_entry(lines)
    if existing is None:
        return False
    index, _ = existing
    write_crontab(lines[: index - 1] + lines[index + 1 :])
    return True
