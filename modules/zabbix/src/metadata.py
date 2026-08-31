MAX_LENGTH = 255


class MetadataTooLongError(ValueError):
    pass


def validate(value):
    if len(value) > MAX_LENGTH:
        raise MetadataTooLongError(
            f"HostMetadata excede {MAX_LENGTH} caracteres ({len(value)}): {value}"
        )


def build(provider, os_label, asterisk_version=None, test=False):
    # só monta a parte auto-detectada -- o usuário edita o resultado inteiro depois
    # (ver main.py: ask_text com default=build(...), geralmente só aperta Enter).
    parts = [f"l:{provider}", "os:linux", f"osn:{os_label}"]
    if asterisk_version:
        parts.append(f"av:{asterisk_version}")
    if test:
        parts.append("test:true")

    result = " ".join(parts)
    validate(result)
    return result
