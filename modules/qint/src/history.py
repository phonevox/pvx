from datetime import datetime
from pathlib import Path


def append(path, message):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {message}\n")
