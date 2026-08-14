import shutil
from datetime import datetime


def backup_config(path):
    backup_path = f"{path}.bak.{datetime.now():%Y%m%d_%H%M%S}"
    shutil.copy2(path, backup_path)
    return backup_path


def restore_config(path, backup_path):
    shutil.copy2(backup_path, path)
