import subprocess

_INSTALL_ARGS = {
    "rhel": ["yum", "install", "-y", "epel-release", "mod_ssl", "python3-certbot-apache"],
    "debian": ["apt-get", "install", "-y", "certbot", "python3-certbot-apache", "apache2"],
}


class PackageError(Exception):
    pass


def install(distro):
    args = _INSTALL_ARGS.get(distro)
    if args is None:
        raise PackageError(f"distribuição não suportada: {distro}")

    if distro == "debian":
        subprocess.run(["apt-get", "update"], capture_output=True, text=True)

    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        raise PackageError(f"falha ao instalar pacotes: {(result.stderr or result.stdout).strip()}")
