import os
import subprocess
from pathlib import Path
from tempfile import NamedTemporaryFile


def build_rule(username):
    return f"{username} ALL=(ALL) NOPASSWD: ALL\n"


def validate_rule_syntax(rule_text):
    with NamedTemporaryFile("w", suffix=".sudoers", delete=False) as f:
        f.write(rule_text)
        temp_path = f.name
    try:
        return subprocess.run(["visudo", "-c", "-f", temp_path], capture_output=True).returncode == 0
    finally:
        os.unlink(temp_path)


def install_rule(username, sudoers_dir="/etc/sudoers.d"):
    rule = build_rule(username)
    rule_path = Path(sudoers_dir) / username

    if rule_path.exists() and rule_path.read_text() == rule:
        return True

    if not validate_rule_syntax(rule):
        return False

    rule_path.write_text(rule)
    rule_path.chmod(0o440)
    os.chown(str(rule_path), 0, 0)
    return True


def remove_rule(username, sudoers_dir="/etc/sudoers.d"):
    try:
        (Path(sudoers_dir) / username).unlink()
    except FileNotFoundError:
        pass
