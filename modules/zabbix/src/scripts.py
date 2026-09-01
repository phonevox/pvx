import json


def _load(state_path):
    try:
        return json.loads(open(state_path).read())
    except (OSError, ValueError):
        return {}


def _save(state_path, entries):
    open(state_path, "w").write(json.dumps(entries, indent=2, sort_keys=True))


def add(state_path, key, command, needs_root=False):
    entries = _load(state_path)
    if key in entries:
        raise KeyError(f"script '{key}' já existe -- use `pvx zabbix script remove {key}` primeiro.")
    entries[key] = {"command": command, "needs_root": needs_root}
    _save(state_path, entries)
    return entries


def remove(state_path, key):
    entries = _load(state_path)
    if key not in entries:
        raise KeyError(f"script '{key}' não existe.")
    del entries[key]
    _save(state_path, entries)
    return entries


def list_all(state_path):
    return _load(state_path)


def render_userparameter_conf(entries):
    lines = []
    for key in sorted(entries):
        command = entries[key]["command"]
        if entries[key].get("needs_root"):
            command = f"sudo -n {command}"
        lines.append(f"UserParameter={key},{command}\n")
    return "".join(lines)


def root_requiring_commands(entries):
    return [entry["command"] for entry in entries.values() if entry.get("needs_root")]
