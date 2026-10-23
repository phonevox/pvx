import ipaddress
import shutil
import subprocess
from pathlib import Path

import defaults

_HEADER = "# gerado pelo pvx firewall (apply) -- reescrito a cada apply, não editar à mão."


def _run(args):
    return subprocess.run(["fail2ban-client", *args], capture_output=True, text=True, check=False)


def available():
    if not shutil.which("fail2ban-client"):
        return False
    return _run(["ping"]).returncode == 0


def active_jails():
    for line in _run(["status"]).stdout.splitlines():
        if "Jail list:" in line:
            return [name.strip() for name in line.split("Jail list:", 1)[1].split(",") if name.strip()]
    return []


def banned_ips(jail):
    for line in _run(["status", jail]).stdout.splitlines():
        if "Banned IP list:" in line:
            return line.split("Banned IP list:", 1)[1].split()
    return []


def render_override(jails, trusted):
    # validado contra o parser real do fail2ban 1.0.2: %(known/ignoreip)s no
    # [DEFAULT] quebra a config inteira (recursão de interpolação). DEFAULT
    # leva o valor puro; cada jail ativo soma ao ignoreip que já tinha --
    # o Issabel define ignoreip por jail (jail.d/issabel.conf), que um
    # DEFAULT sozinho nunca sobrescreveria. .local é lido depois dos .conf.
    ips = " ".join(trusted)
    lines = [_HEADER, "[DEFAULT]", f"ignoreip = {ips}", ""]
    for jail in jails:
        lines += [f"[{jail}]", f"ignoreip = %(known/ignoreip)s {ips}", ""]
    return "\n".join(lines)


def _networks(trusted):
    networks = []
    for entry in trusted:
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            continue
    return networks


def sync(trusted, path=defaults.FAIL2BAN_OVERRIDE_PATH):
    if not available():
        return None
    jails = active_jails()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_override(jails, trusted))

    # --restart (não reload simples): o `firewall-cmd --reload` do engine
    # firewalld descarta as regras de runtime onde o fail2ban guarda os bans
    # -- reiniciar os jails recria tudo e restaura os bans do banco dele.
    result = _run(["reload", "--restart"])
    if result.returncode != 0:
        raise RuntimeError(f"fail2ban-client reload falhou: {(result.stderr or result.stdout).strip()}")

    # ignoreip só impede ban novo -- ban que já existia de IP confiável sai na mão.
    networks = _networks(trusted)
    unbanned = set()
    for jail in jails:
        for ip in banned_ips(jail):
            try:
                addr = ipaddress.ip_address(ip)
            except ValueError:
                continue
            if any(addr.version == net.version and addr in net for net in networks):
                _run(["set", jail, "unbanip", ip])
                unbanned.add(ip)
    return {"jails": len(jails), "trusted": len(trusted), "unbanned": sorted(unbanned)}


def is_synced(trusted, path=defaults.FAIL2BAN_OVERRIDE_PATH):
    if not available():
        return None
    try:
        current = Path(path).read_text()
    except OSError:
        return False
    return current == render_override(active_jails(), trusted)
