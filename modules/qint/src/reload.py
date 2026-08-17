import shutil
import subprocess


def reload_dialplan():
    if shutil.which("asterisk") is None:
        return False
    subprocess.run(["asterisk", "-rx", "dialplan reload"], check=True)
    return True
