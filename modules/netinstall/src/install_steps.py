import os
import re
import shutil

import assets
import defaults
import os_ops


def _disable_ipv6(sysctl_path="/etc/sysctl.conf"):
    line = "net.ipv6.conf.all.disable_ipv6 = 1"
    try:
        content = open(sysctl_path).read()
    except OSError:
        content = ""
    if line not in content:
        with open(sysctl_path, "a") as f:
            f.write(line + "\n")
    os_ops.run_cmd(["sysctl", "-p"])


def _pkg_install_or_raise(packages, on_line=None):
    # os_ops.pkg_install() já sabe quais pacotes falharam -- ignorar isso deixa o
    # processo seguir quieto e crashar (confuso) várias etapas depois, num ponto sem
    # relação nenhuma com o pacote que de fato não instalou.
    # on_line só é encaminhado se dado -- mantém a chamada idêntica à de antes (sem
    # kwarg extra) pros call sites que não streamam nada.
    kwargs = {"on_line": on_line} if on_line is not None else {}
    failed = os_ops.pkg_install(packages, **kwargs)
    if failed:
        raise RuntimeError(f"falha ao instalar pacote(s): {', '.join(failed)}")


def add_repos(pyz_path):
    _pkg_install_or_raise(["epel-release"])
    os_ops.run_cmd(["dnf", "makecache"])
    _pkg_install_or_raise(["htop", "tmux"])
    _disable_ipv6()
    # arquivos .repo vêm de DENTRO do próprio .pyz (ver assets.py) -- no host instalado só
    # module.pyz+manifest.json existem no diretório do módulo, nunca uma pasta config/ solta.
    assets.extract_prefix(pyz_path, "config/repos", "/etc/yum.repos.d")


def _set_selinux_config_disabled(path="/etc/selinux/config"):
    try:
        content = open(path).read()
    except OSError:
        return
    new_content = re.sub(r"^SELINUX=.*", "SELINUX=disabled", content, flags=re.MULTILINE)
    if new_content != content:
        open(path, "w").write(new_content)


def _user_exists(name, passwd_path="/etc/passwd"):
    try:
        content = open(passwd_path).read()
    except OSError:
        return False
    return any(line.startswith(f"{name}:") for line in content.splitlines())


def prepare_system():
    os_ops.run_cmd(["setenforce", "0"])
    _set_selinux_config_disabled()
    os_ops.run_cmd(["groupadd", "-f", "-r", "asterisk"])
    if not _user_exists("asterisk"):
        os_ops.run_cmd([
            "useradd", "-r", "-g", "asterisk", "-c", "Asterisk PBX",
            "-s", "/bin/bash", "-d", "/var/lib/asterisk", "asterisk",
        ])
    _pkg_install_or_raise(["issabel-config_helpers"])


def enable_php_remi(major):
    # sem repo Remi + módulo php:remi-7.4, php-imap/php-mcrypt/php-tidy (e quem depende
    # deles, ex. php-PHPMailer/php-tcpdf) não existem no módulo php padrão do AppStream.
    _pkg_install_or_raise([f"https://rpms.remirepo.net/enterprise/remi-release-{major}.rpm"])
    os_ops.run_cmd(["dnf", "module", "reset", "php", "-y"])
    os_ops.run_cmd(["dnf", "module", "enable", "php:remi-7.4", "-y"])
    os_ops.run_cmd(["dnf", "config-manager", "--set-enabled", "remi"])
    os_ops.run_cmd(["dnf", "config-manager", "--set-enabled", "powertools"])
    os_ops.run_cmd(["dnf", "config-manager", "--set-enabled", "devel"])


def install_packages(astver, extra_packages=(), on_line=None, skip_clean=False):
    base = [pkg.replace("$ASTVER", astver) for pkg in defaults.PACKAGES_BASE]
    if not skip_clean:
        os_ops.run_cmd(["dnf", "clean", "all"])
    _pkg_install_or_raise(base, on_line=on_line)
    _pkg_install_or_raise(defaults.PACKAGES_ISSABEL + list(extra_packages), on_line=on_line)


def post_install():
    os_ops.run_cmd(["systemctl", "enable", "mariadb.service"])
    os_ops.run_cmd(["systemctl", "start", "mariadb"])
    # MariaDB novo autentica root via unix_socket (sem senha) -- só até esta chamada, que
    # troca o auth pra mysql_native_password. Se ela falhar, a senha real do root fica
    # desconhecida e o reset abaixo (que precisa dessa senha pra autenticar) não funciona.
    if not os_ops.run_cmd([
        "mysql", "-e",
        f"SET PASSWORD FOR 'root'@'localhost' = PASSWORD('{defaults.TEMP_MYSQL_PASSWORD}')",
    ]):
        raise RuntimeError("falha ao definir a senha temporária do MySQL root.")
    os_ops.run_cmd(["systemctl", "enable", "httpd"])

    # firewalld é OPCIONAL: várias imagens de VPS/cloud não vêm com ele instalado.
    if shutil.which("firewall-cmd"):
        os_ops.run_cmd(["systemctl", "disable", "firewalld"])
        os_ops.run_cmd(["systemctl", "stop", "firewalld"])

    os_ops.run_cmd(["rm", "-f", "/etc/issabel.conf"])
    # install_db/set_passwords assumem senha root em branco depois daqui (ver
    # defaults.TEMP_MYSQL_PASSWORD) -- se o reset falhar, os dois quebram em cascata
    # depois, sem relação óbvia com a causa real. Precisa autenticar com a senha
    # temporária de fato (setada acima) -- sem isso o MariaDB recusa a conexão
    # silenciosamente (achado ao vivo numa instalação real: "Access denied").
    ok = os_ops.run_cmd([
        "mysql", f"--password={defaults.TEMP_MYSQL_PASSWORD}", "-e",
        "SET PASSWORD FOR 'root'@'localhost' = PASSWORD('')",
    ])
    if not ok:
        raise RuntimeError("falha ao zerar a senha do MySQL root -- install_db/set_passwords dependem dela em branco.")
    os_ops.run_cmd(["mkdir", "--parents", "/var/log/asterisk/cdr-csv"])
    os_ops.run_cmd(["/usr/sbin/amportal", "chown"])


def install_db():
    ok = os_ops.run_cmd([
        "/usr/src/issabelPBX/framework/install_amp", "--dbuser=root",
        "--installdb", "--scripted", "--language=en",
    ])
    if not ok:
        raise RuntimeError("install_amp --installdb falhou -- schema do banco não foi criado.")


def set_timezone(tz):
    if not os_ops.run_cmd(["timedatectl", "set-timezone", tz]):
        os_ops.run_cmd(["ln", "-sf", f"/usr/share/zoneinfo/{tz}", "/etc/localtime"])
    os_ops.run_cmd(["hwclock", "--hctosys"])


def install_control_panel(pyz_path):
    dest = "/var/www/html/modules/control_panel"
    os_ops.run_cmd(["rm", "-rf", dest])
    if not assets.extract_prefix(pyz_path, "config/control_panel", dest):
        return

    os_ops.run_cmd(["chown", "-R", "asterisk:asterisk", dest])
    os_ops.run_cmd(["chmod", "-R", "755", dest])
    os_ops.run_cmd([
        "sqlite3", "/var/www/db/acl.db",
        "INSERT INTO acl_resource (name, description) SELECT 'control_panel','Issabel Panel' "
        "WHERE NOT EXISTS (SELECT 1 FROM acl_resource WHERE name='control_panel');",
    ])
    os_ops.run_cmd([
        "sqlite3", "/var/www/db/menu.db",
        "INSERT INTO menu (id, IdParent, Link, Name, Type, order_no) SELECT 'control_panel',"
        "'pbxconfig','','Issabel Panel','module',8 WHERE NOT EXISTS (SELECT 1 FROM menu WHERE id='control_panel');",
    ])
    os_ops.run_cmd([
        "sqlite3", "/var/www/db/acl.db",
        "INSERT INTO acl_group_permission (id_action, id_group, id_resource) SELECT 1,1,"
        "(SELECT id FROM acl_resource WHERE name='control_panel') WHERE NOT EXISTS "
        "(SELECT 1 FROM acl_group_permission WHERE id_group=1 AND id_resource="
        "(SELECT id FROM acl_resource WHERE name='control_panel'));",
    ])


def _sync_fop2_secret():
    script = "/usr/local/fop2/create_fop2_manager_user.pl"
    if not (os.path.exists(script) and os.access(script, os.X_OK)):
        return
    os_ops.run_cmd([script])


def set_passwords(sql_password, web_password):
    ok = os_ops.run_cmd(["/usr/bin/issabel-admin-passwords", "--cli", "init", sql_password, web_password])
    if not ok:
        # --cli init roda o retrieve_conf por dentro (promove sip.conf e os outros
        # .confnew) -- uma falha aqui silenciosa deixava esses arquivos sem promover, sem
        # aviso nenhum (achado investigando o chan_sip não carregar numa instalação real).
        raise RuntimeError("issabel-admin-passwords --cli init falhou -- senhas/sip.conf não foram configurados.")
    # --cli init nunca roda o equivalente a action_changeFop2() (só o dialog legado
    # roda) -- sem isto o fop2.cfg fica com a senha AMI de fábrica.
    _sync_fop2_secret()
