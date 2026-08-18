import shutil
import subprocess


def is_asterisk_available():
    return shutil.which("asterisk") is not None


def reload_dialplan():
    if not is_asterisk_available():
        return False
    subprocess.run(["asterisk", "-rx", "dialplan reload"], check=True)
    return True
