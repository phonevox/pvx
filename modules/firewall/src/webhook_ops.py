import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

MARKER_FILENAME = "webhook.conf"


def _path(state_dir):
    return Path(state_dir) / MARKER_FILENAME


def get(state_dir):
    path = _path(state_dir)
    if not path.exists():
        return None
    content = path.read_text().strip()
    return content or None


def set_url(state_dir, url):
    path = _path(state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(url.strip() + "\n")


def clear(state_dir):
    path = _path(state_dir)
    if path.exists():
        path.unlink()


def notify(state_dir, event, detail=""):
    # aditivo e best-effort, de propósito -- uma falha aqui nunca pode
    # interromper a ação real que está sendo notificada (ban, drift, etc.).
    url = get(state_dir)
    if not url:
        return False, "nenhuma URL de webhook configurada"

    payload = json.dumps({
        "event": event,
        "detail": detail,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }).encode()
    request = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5):
            pass
    except (urllib.error.URLError, OSError) as e:
        return False, f"falha ao notificar webhook: {e}"
    return True, None
