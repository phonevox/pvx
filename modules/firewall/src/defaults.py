CONFIG_FILENAMES = {
    "ip_accept": "ip_accept.conf",
    "ip_deny": "ip_deny.conf",
    "port_accept": "port_accept.conf",
    "port_deny": "port_deny.conf",
    "geo_accept": "geo_accept.conf",
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
        ("145.223.92.246", "PHONEVOX"),
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
    # vazio por padrão, de propósito -- diferente de ip_accept/port_deny,
    # ligar isso BLOQUEIA (não só restringe) todo IP fora dos países
    # listados, em toda porta. Nunca pode ser semeado por uma leitura
    # passiva (check/list) -- só por uma ação explícita (`geo enable`,
    # ver DEFAULT_GEO_ACCEPT).
    "geo_accept": [],
}

# seed usado só pelo comando explícito `geo enable` -- nunca por
# lists.read_list(seed=...) numa leitura passiva.
DEFAULT_GEO_ACCEPT = [("BR", "Brasil")]

# nomes das chains/zona -- iguais nos dois engines onde faz sentido.
IPTABLES_TRUSTED_CHAIN = "ptrusted"
IPTABLES_DENY_CHAIN = "pdenyip"
IPTABLES_PORT_CHAIN = "pdrop"

FIREWALLD_ZONE = "pvxfw"
# achado ao vivo: o instalador do MagnusBilling já vincula a interface real à zona
# "public" (--change-interface) e o próprio Magnus depende do firewalld pra isso
# (chega a desabilitar o serviço "iptables" pra não conflitar). --set-default-zone
# (nosso jeito normal de assumir a zona pvxfw) não move uma interface que já tem
# zona explícita -- nessa central, pvxfw fica 100% inerte. Integrar direto na
# "public" funciona: nossas rich-rules de IP (prioridade negativa) rodam ANTES das
# portas simples do Magnus, e as de porta (prioridade positiva) rodam DEPOIS -- ou
# seja, o próprio allow de porta do Magnus (80/443/etc.) sempre vence o nosso
# port_deny pra essas portas, nunca corre risco de trancar o painel do cliente.
MAGNUS_FIREWALLD_ZONE = "public"
FIREWALLD_PRIORITY_FAILSAFE = -2000
FIREWALLD_PRIORITY_ICMP = -1500
FIREWALLD_PRIORITY_DENY_IP = -1000
FIREWALLD_PRIORITY_TRUSTED_IP = -500
FIREWALLD_PRIORITY_PORT_DENY = 100
FIREWALLD_PRIORITY_PORT_ACCEPT = 200

SYSTEMD_UNIT_PATH = "/etc/systemd/system/pvx-firewall.service"

# logging de pacotes dropados -- opt-in (ver log_ops.py), rate-limited pra
# não virar vetor de disk-fill/log-flood vindo de um scanner qualquer.
IPTABLES_LOG_RATE_LIMIT = "5/min"
LOG_PREFIX_DENY = "pvx-fw-deny: "
LOG_PREFIX_PORT = "pvx-fw-port: "

# geoban -- opt-in (ver geoip_ops.py/ipset_ops.py), só iptables por enquanto.
IPTABLES_GEO_CHAIN = "pgeo"
GEO_IPSET_NAME = "pvx-geo"

# fail2ban -- override que soma os IPs confiáveis ao ignoreip de cada jail
# (ver fail2ban_ops.py). Vale pros dois engines.
FAIL2BAN_OVERRIDE_PATH = "/etc/fail2ban/jail.d/pvx-firewall.local"
