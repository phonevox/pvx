import subprocess
from pathlib import Path

_TEMPLATE = """<VirtualHost *:80>
    ServerAdmin {email}
    ServerName {domain}
    DocumentRoot /var/www/html
</VirtualHost>
"""


def conf_path(conf_dir, domain):
    return str(Path(conf_dir) / f"{domain}.conf")


def exists(conf_dir, domain):
    return Path(conf_path(conf_dir, domain)).exists()


def create(conf_dir, domain, email, distro):
    path = Path(conf_path(conf_dir, domain))
    path.write_text(_TEMPLATE.format(email=email, domain=domain))
    if distro == "debian":
        # a2ensite falhando (ex.: já habilitado) não deve travar o setup -- não checa
        # returncode, igual ao script-base ("|| true").
        subprocess.run(["a2ensite", domain], capture_output=True)
    return str(path)


def remove(conf_dir, domain, distro):
    if distro == "debian":
        subprocess.run(["a2dissite", domain], capture_output=True)
    path = Path(conf_path(conf_dir, domain))
    if path.exists():
        path.unlink()


def reload_apache(service):
    subprocess.run(["systemctl", "reload", service], capture_output=True)
