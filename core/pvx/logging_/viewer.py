from pvx import config


def read_log(name, lines=None):
    path = config.logs_dir() / f"{name}.log"
    if not path.exists():
        return ""

    content = path.read_text()
    if lines is None:
        return content
    return "\n".join(content.splitlines()[-lines:])
