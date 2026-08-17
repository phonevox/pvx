import subprocess
from pathlib import Path

import defaults

_UNIT_TEMPLATE = """[Unit]
Description=pvx firewall sync
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart={pvx_bin} firewall sync --force --yes

[Install]
WantedBy=multi-user.target
"""


def render_unit(pvx_bin):
    return _UNIT_TEMPLATE.format(pvx_bin=pvx_bin)


def install(pvx_bin="/usr/local/bin/pvx", unit_path=None, dry_run=False):
    content = render_unit(pvx_bin)
    if dry_run:
        return content

    Path(unit_path or defaults.SYSTEMD_UNIT_PATH).write_text(content)
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "enable", "pvx-firewall.service"], check=True)
    return content
