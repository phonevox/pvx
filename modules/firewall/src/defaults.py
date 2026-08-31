CONFIG_FILENAMES = {
    "ip_accept": "ip_accept.conf",
    "ip_deny": "ip_deny.conf",
    "port_accept": "port_accept.conf",
    "port_deny": "port_deny.conf",
}

DEFAULT_LISTS = {
    "ip_accept": [
        ("127.0.0.1", "LOCALHOST"),
        ("10.0.0.0/8", "INTERNO"),
        ("172.16.0.0/12", "INTERNO"),
        ("192.168.0.0/16", "INTERNO"),
        ("189.124.85.75", "PHONEVOX PRINCIPAL"),
        ("186.233.124.252", "PHONEVOX SECUNDARIO"),
        ("189.124.85.152/29", "PHONEVOX REDE"),
        ("186.233.120.72/29", "PHONEVOX REDE"),
        ("179.199.136.199", "MAGNUSBILLING PHONEVOX"),
        ("149.78.185.36", "PHONEVOX MAGNUS 2"),
        ("31.97.160.127", "PHONEVOX INTERNO V2"),
        ("45.140.193.125", "PHONEVOX HELPDESK"),
        ("186.233.122.92", "PHONEVOX ABNER"),
    ],
    "ip_deny": [],
    "port_accept": [
        ("5060/udp", "SIP"),
        ("5060/tcp", "SIP"),
        ("5061/tcp", "SIP TLS"),
        ("50007/tcp", "SIP custom"),
        ("50007/udp", "SIP custom"),
        ("10000-20000/udp", "RTP audio/video"),
    ],
    # portas de administração (MySQL, AMI, Zabbix, SSH -- padrão 22 E o
    # custom do ssh-hardening, 21122) ficam fechadas pro mundo por padrão,
    # de propósito -- acesso real é só via ip_accept (IP de confiança) ou o
    # failsafe de sessão, nunca abrindo a porta geral. ssh-hardening nunca
    # mexe em firewall (só troca a porta no sshd_config), então mudar de 22
    # pra outra porta não abre nada aqui sozinho -- é o esperado.
    # engines aplicam deny ANTES de accept na mesma chain: se uma porta cair
    # nas duas listas, deny sempre vence (sync() nunca alerta sobre isso).
    "port_deny": [
        ("995/udp", "POP3D"),
        ("995/tcp", "POP3D"),
        ("110/udp", "POP3D"),
        ("110/tcp", "POP3D"),
        ("4569/udp", "IAX"),
        ("5353/udp", "mDNS"),
        ("20-23", "ftp-data/ftp/ssh/telnet"),
        ("80/tcp", "HTTP"),
        ("443/tcp", "HTTPS"),
        ("3306/tcp", "MySQL"),
        ("5038/tcp", "Asterisk Manager Interface"),
        ("21122/tcp", "SSH custom"),
        ("10050/tcp", "Zabbix agent"),
        ("10051/tcp", "Zabbix server"),
    ],
}

# nomes das chains/zona -- iguais nos dois engines onde faz sentido.
IPTABLES_TRUSTED_CHAIN = "ptrusted"
IPTABLES_DENY_CHAIN = "pdenyip"
IPTABLES_PORT_CHAIN = "pdrop"

FIREWALLD_ZONE = "pvxfw"
FIREWALLD_PRIORITY_FAILSAFE = -2000
FIREWALLD_PRIORITY_ICMP = -1500
FIREWALLD_PRIORITY_DENY_IP = -1000
FIREWALLD_PRIORITY_TRUSTED_IP = -500
FIREWALLD_PRIORITY_PORT_DENY = 100
FIREWALLD_PRIORITY_PORT_ACCEPT = 200

SYSTEMD_UNIT_PATH = "/etc/systemd/system/pvx-firewall.service"
