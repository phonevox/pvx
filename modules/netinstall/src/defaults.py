MIRROR_PROBE_URL = "http://mirror.issabel.org"
MIN_MEM_KB = 1536 * 1024  # RAM+swap mínimo recomendado (aviso, não bloqueio)

# chave pública principal da Phonevox -- default do usuário dedicado do ssh-hardening.
SSH_DEFAULT_PUBKEY = (
    "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQC5S9t+CHuQYVe9It/zVWNEYWq7fuGBF1oll63MujAREeP3sB3N"
    "VhrWs8AcDNOwPQ+8Z7s4Yc8/r8BKCquujugkWv3ilZjJAbeyR7A6rddRM1ai1bfc8gRV7CD1tExQuO+QE9RORQ0f0"
    "J+0+Fu4vB3YRMeSx4czq5tbYKwvdfP6pgWWRppyA8uM7nKXnYsdwkyKxJZb4I353cC4C+ZvaEUQahygNs9XgblBB9"
    "TM0UuttdoBi4pTj4aqLXTBhcLqghkQP45JaQ8/G5qSzs2U2eGH4L+mEqFSg+ybL3KxGmyHxtCBOqhFTm/s3EqkSQ80"
    "OSwdYSzH7GMTWWfKZ4UoeFiQucHYto83LmfBYdqckbtw7ZNsXU/egQR5eSwtwQBK5yLnPSnQldozMKoS2gKayWtxqv"
    "jiYpQacw48DaB1mZUfl7SJ/fa9LEUrQ2CnizQJSemwsteJqDII95mzCpyGXAeNfXdhI52dx0YXx3D62LXQBAn1HSIg"
    "nzsrEVh29CumZ28cxpOL0djI2Y8VyHgw6fFSAZqmn3Xr2yCxBvzN4rlEvtzGVw8PxAZT33duLEgPFV2XBrU5I98bufg"
    "g8cE3NXTLtMwuYWbtKtbRZkpRJesQEkaL70kLvvsYCZAaqDhwLAO8q41czunYLt6MyKcAHrb5whFBz6Fx/WrEEpM1p5"
    "KhSw== MAIN@PHONEVOX"
)

DEFAULT_TIMEZONE = "America/Sao_Paulo"
DEFAULT_LANG = "pt_BR"

# senha temporária do MySQL root durante a instalação -- zerada antes de _set_passwords rodar
# (install_amp/issabel-admin-passwords não precisa dela em branco).
TEMP_MYSQL_PASSWORD = "iSsAbEl.2o17"

ASTERISK_VERSIONS = ("16", "18")

# --addpkgs (issabel5): chave -> pacotes reais. "licensed"/"community-blocklist" pré-marcados
# na checklist; "wanpipe" (hardware específico) fica desmarcado.
ADDPKGS = {
    "licensed": [
        "issabel-license", "webconsole", "issabel-wizard", "issabel-packet_capture",
        "issabel-upnpc", "issabel-two_factor_auth", "issabel-theme_designer", "issabel-network-agent",
    ],
    "community-blocklist": ["issabel-packetbl"],
    "wanpipe": ["wanpipe-utils", "wanpipe"],
}
ADDPKGS_DEFAULTS = {"licensed": True, "community-blocklist": True, "wanpipe": False}

# lista de pacotes base -- "asterisk$ASTVER" é placeholder literal (substituído em runtime),
# igual ao bash original (arquivo de dados puro, sem $ASTVER de shell de verdade).
PACKAGES_BASE = [
    "httpd", "httpd-tools", "mariadb", "mariadb-connector-c", "mariadb-connector-odbc",
    "mariadb-server", "php", "php-bcmath", "php-cli", "php-common", "php-gd",
    "php-IDNA_Convert", "php-imap", "php-jpgraph", "php-magpierss", "php-mbstring",
    "php-mcrypt", "php-mysqlnd", "php-pdo", "php-pear", "php-pear-DB", "php-PHPMailer",
    "php-process", "php-simplepie", "php-Smarty", "php-soap", "php-tcpdf", "php-tidy",
    "php-xml", "asterisk$ASTVER", "asterisk$ASTVER-devel", "asterisk$ASTVER-curl",
    "asterisk-codec-g729", "asterisk-perl", "asterisk-es-sounds", "asterisk-fr-sounds",
    "asterisk-sounds-en-gsm", "asterisk-pt_BR-sounds", "certbot", "vim", "jq", "whois",
    "bind-utils", "dhcp-server", "langpacks-es", "langpacks-en", "langpacks-pt",
    "langpacks-pt_BR", "langpacks-fa", "langpacks-fr", "mailx",
]
PACKAGES_ISSABEL = [
    "issabel-geoip", "issabel", "issabel-prosody-auth", "issabel-endpointconfig2",
    "xtables-addons", "RoundCubeMail", "php-ioncubeloader", "libnsl", "fop2",
]

# tweaks Phonevox: chave -> (default_on, label). "ssh-hardening"/"firewall"/"qint" já têm
# módulo pvx real (integrations.py); "operator-panel" é passo local (control_panel.py).
TWEAKS_CATALOG = {
    "operator-panel": (True, "Painel do operador (control_panel -- visão de recepção/switchboard)"),
    "ssh-hardening": (True, "Hardening de acesso SSH (bloqueia root, cria usuário admin dedicado, muda porta)"),
    "firewall": (True, "Firewall (iptables/firewalld) com as listas padrão da Phonevox + sync"),
    "qint": (False, "Integração de URA (IXCSoft/SGP) com Asterisk/Issabel -- precisa de dados do cliente, default off"),
}

SSH_HARDENING_DEFAULTS = {
    "lock_root": True,
    "root_password": "phonevox@@",
    "create_user": True,
    "username": "phonevox",
    "pubkey": SSH_DEFAULT_PUBKEY,
    "allow_password": False,
    "change_port": True,
    "port": "21122",
}
