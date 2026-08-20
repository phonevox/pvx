from pvx import config


def read_log(name, lines=None):
    path = config.logs_dir() / f"{name}.log"
    if not path.exists():
        return ""

    content = path.read_text()
    if lines is None:
        return content
    return "\n".join(content.splitlines()[-lines:])


def list_log_names():
    logs_dir = config.logs_dir()
    if not logs_dir.exists():
        return []
    return sorted(p.stem for p in logs_dir.glob("*.log"))


def read_combined_logs(names, lines=None):
    # cada linha já vem com o timestamp do Formatter (get_module_logger) no início --
    # dá pra intercalar logs de fontes diferentes só ordenando as linhas como string.
    all_lines = []
    for name in names:
        all_lines.extend(read_log(name).splitlines())
    all_lines.sort()
    if lines is not None:
        all_lines = all_lines[-lines:]
    return "\n".join(all_lines)


class LogFollower:
    # tail -f caseiro: guarda a posição de leitura de cada arquivo no momento da
    # construção (nunca mostra o que já existia, só o que chega depois) e cada poll()
    # devolve as linhas novas desde a última chamada. Sem lib externa (watchdog etc.) --
    # é só rastrear offset de arquivo, o stdlib já resolve.
    def __init__(self, names):
        self._paths = [config.logs_dir() / f"{name}.log" for name in names]
        self._positions = {path: (path.stat().st_size if path.exists() else 0) for path in self._paths}

    def poll(self):
        new_lines = []
        for path in self._paths:
            if not path.exists():
                continue
            with open(path) as f:
                f.seek(self._positions[path])
                content = f.read()
                self._positions[path] = f.tell()
            new_lines.extend(content.splitlines())
        new_lines.sort()
        return new_lines
