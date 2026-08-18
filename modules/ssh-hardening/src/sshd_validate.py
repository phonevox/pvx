import subprocess

from backup import restore_config


def validate_config(config_path):
    return subprocess.run(["sshd", "-t", "-f", config_path], capture_output=True).returncode == 0


def apply_with_rollback(config_path, backup_path):
    if validate_config(config_path):
        return True
    restore_config(config_path, backup_path)
    return False
