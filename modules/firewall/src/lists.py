import os
from pathlib import Path


def read_list(path, seed=None):
    path = Path(path)
    if not path.exists():
        if seed is None:
            return []
        _write_all(path, seed)
        return list(seed)

    entries = []
    for line in path.read_text().splitlines():
        content, _, comment = line.partition("#")
        content = content.strip()
        if not content:
            continue
        entries.append((content, comment.strip()))
    return entries


def _write_all(path, entries):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{entry}  # {comment}" if comment else entry for entry, comment in entries]
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text("\n".join(lines) + ("\n" if lines else ""))
    os.replace(tmp_path, path)


def add_entry(path, entry, comment=None):
    entries = read_list(path)
    if any(existing == entry for existing, _ in entries):
        return False
    entries.append((entry, comment or ""))
    _write_all(path, entries)
    return True


def remove_entry(path, entry):
    entries = read_list(path)
    remaining = [(e, c) for e, c in entries if e != entry]
    if len(remaining) == len(entries):
        return False
    _write_all(path, remaining)
    return True
