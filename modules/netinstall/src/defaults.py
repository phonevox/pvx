MIRROR_PROBE_URL = "http://mirror.issabel.org"
MIN_MEM_KB = 1536 * 1024  # RAM+swap mínimo recomendado (aviso, não bloqueio)

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

# tweaks Phonevox: chave -> (default_on, label). Pedido ao vivo: ssh-hardening/firewall/qint
# saíram daqui -- rodar durante o netinstall obrigava a resolver a configuração de 3 módulos
# no meio da instalação do Issabel; agora é sempre um `pvx <módulo> setup/apply` separado,
# depois que o Issabel já está de pé. "operator-panel" é passo local (control_panel.py), não
# um módulo pvx -- continua aqui.
TWEAKS_CATALOG = {
    "operator-panel": (True, "Painel do operador (control_panel -- visão de recepção/switchboard)"),
}
