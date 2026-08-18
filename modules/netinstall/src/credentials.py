import os
from datetime import datetime
from pathlib import Path


def save_credentials(state_dir, product, sql_password, web_password, extra=None):
    # grava uma única vez, 0600 -- é a única cópia recuperável depois que a tela rolar.
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    path = state_dir / f"credentials-{product}-{ts}.txt"

    lines = [
        f"produto={product}",
        f"data={ts}",
        f"mysql_root_password={sql_password}",
        f"web_admin_password={web_password}",
    ]
    for key, value in (extra or {}).items():
        lines.append(f"{key}={value}")

    path.write_text("\n".join(lines) + "\n")
    os.chmod(path, 0o600)
    return str(path)
