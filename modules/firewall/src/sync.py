from pathlib import Path

import defaults
import engine_detect
import firewalld_engine
import iptables_engine
import lists
import magnus_detect
import session_ip

_ENGINES = {"iptables": iptables_engine, "firewalld": firewalld_engine}


def resolve_engine(explicit=None):
    return explicit or engine_detect.detect_engine()


def resolve_firewalld_zone():
    # achado ao vivo: o instalador do MagnusBilling já vincula a interface real à
    # zona "public" -- nossa zona própria (pvxfw) fica inerte lá. Nessa central,
    # miramos direto na "public" (sem tomar posse dela); em qualquer outra, seguimos
    # dono da nossa própria zona, como sempre.
    if magnus_detect.is_magnusbilling():
        return defaults.MAGNUS_FIREWALLD_ZONE, False
    return defaults.FIREWALLD_ZONE, True


def run(base_dir, engine=None, force=False):
    engine_name = resolve_engine(engine)
    ip = session_ip.detect_session_ip()
    if not ip and not force:
        raise RuntimeError("não consegui detectar o IP da sessão atual -- use --force pra prosseguir sem failsafe.")

    base_dir = Path(base_dir)
    lists_data = {
        key: lists.read_list(base_dir / filename, seed=defaults.DEFAULT_LISTS[key])
        for key, filename in defaults.CONFIG_FILENAMES.items()
    }

    sync_kwargs = dict(
        ip_accept=lists_data["ip_accept"],
        ip_deny=lists_data["ip_deny"],
        port_accept=lists_data["port_accept"],
        port_deny=lists_data["port_deny"],
        failsafe_ip=ip,
    )

    firewalld_zone = None
    if engine_name == "firewalld":
        firewalld_zone, manage_zone = resolve_firewalld_zone()
        sync_kwargs["zone"] = firewalld_zone
        sync_kwargs["manage_zone"] = manage_zone

    _ENGINES[engine_name].sync(**sync_kwargs)
    return {"engine": engine_name, "session_ip": ip, "firewalld_zone": firewalld_zone}
