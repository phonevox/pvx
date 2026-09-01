import subprocess

MARKER = "# gerenciado pelo pvx uoe -- não editar à mão, use `pvx uoe relogin`"

# qualquer linha de cron com uma dessas palavras E que não seja a managed entry é
# candidata a "legacy backup routine" -- nunca removida sozinha, só listada (ver
# CONTEXT.md/ADR 0002: identificação por marcador, não por conteúdo).
_BACKUP_KEYWORDS = ("pbackup", "issabel-helper", "rclone", "backup")


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


def upsert_managed_entry(lines, command):
    existing = find_managed_entry(lines)
    if existing is None:
        return lines + [MARKER, command]
    index, _ = existing
    result = list(lines)
    result[index] = command
    return result


def remove_managed_entry(lines):
    existing = find_managed_entry(lines)
    if existing is None:
        return lines, False
    index, _ = existing
    result = lines[: index - 1] + lines[index + 1 :]
    return result, True


def find_legacy_candidates(lines):
    managed = find_managed_entry(lines)
    managed_index = managed[0] if managed else None

    candidates = []
    for index, line in enumerate(lines):
        if index == managed_index:
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lowered = stripped.lower()
        if any(keyword in lowered for keyword in _BACKUP_KEYWORDS):
            candidates.append(stripped)
    return candidates
