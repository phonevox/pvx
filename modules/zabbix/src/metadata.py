MAX_LENGTH = 255


class MetadataTooLongError(ValueError):
    pass


def build(provider, os_label, asterisk_version=None, test=False, extra=None):
    parts = [f"l:{provider}", "os:linux", f"osn:{os_label}"]
    if asterisk_version:
        parts.append(f"av:{asterisk_version}")
    if test:
        parts.append("test:true")
    if extra:
        parts.append(extra)

    result = " ".join(parts)
    if len(result) > MAX_LENGTH:
        raise MetadataTooLongError(
            f"HostMetadata excede {MAX_LENGTH} caracteres ({len(result)}): {result}"
        )
    return result
