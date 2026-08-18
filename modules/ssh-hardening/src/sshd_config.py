import re


def set_directive(config_text, directive, value):
    target_line = f"{directive} {value}"
    active_re = re.compile(rf"^{re.escape(directive)}\s+\S", re.IGNORECASE)

    new_lines = []
    already_satisfied = False
    changed = False

    for line in config_text.splitlines():
        if line.startswith("#") or not active_re.match(line):
            new_lines.append(line)
        elif line == target_line:
            already_satisfied = True
            new_lines.append(line)
        else:
            new_lines.append(f"#{line}  # disabled by ssh-hardening")
            changed = True

    if already_satisfied and not changed:
        return config_text

    new_lines.append(target_line)
    return "\n".join(new_lines) + "\n"
