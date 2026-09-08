import os

_APACHE_INFO = {
    "rhel": {"service": "httpd", "conf_dir": "/etc/httpd/conf.d"},
    "debian": {"service": "apache2", "conf_dir": "/etc/apache2/sites-available"},
}


def detect_distro():
    if os.path.exists("/etc/redhat-release"):
        return "rhel"
    if os.path.exists("/etc/debian_version"):
        return "debian"
    return None


def apache_info(distro):
    return _APACHE_INFO.get(distro)
