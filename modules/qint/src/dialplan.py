_INCLUDE_DIRECTIVE = {"ixcsoft": "#include", "sgp": "#tryinclude"}


def build_include_line(tipo, filename):
    return f'{_INCLUDE_DIRECTIVE[tipo]} "{filename}"'


def add_include_if_absent(text, include_line):
    if include_line in text.splitlines():
        return text
    return text.rstrip("\n") + "\n" + include_line + "\n"


def add_moh_class_if_absent(text, class_name, moh_dir):
    header = f"[{class_name}]"
    if header in text:
        return text
    block = f"{header}\nmode=files\ndirectory={moh_dir}\n"
    return (text.rstrip("\n") + "\n\n" + block) if text.strip() else block
