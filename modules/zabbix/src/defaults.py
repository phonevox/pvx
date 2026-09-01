# versão do Zabbix SERVER (não do agent) -- o repo é versionado por essa major.minor,
# tem que bater com a versão real do server pra evitar incompatibilidade de protocolo.
ZABBIX_VERSION = "5.0"

AGENT_VARIANTS = ("agent2", "agent")

AGENT_PACKAGES = {"agent2": "zabbix-agent2", "agent": "zabbix-agent"}
AGENT_SERVICES = {"agent2": "zabbix-agent2", "agent": "zabbix-agent"}
AGENT_CONFIG_PATHS = {
    "agent2": "/etc/zabbix/zabbix_agent2.conf",
    "agent": "/etc/zabbix/zabbix_agentd.conf",
}
AGENT_CONFD_DIRS = {
    # agent2 usa "zabbix_agent2.d" (sem "conf." no meio) -- é o nome real que o
    # pacote RPM já publica no Include= default do próprio zabbix_agent2.conf.
    "agent2": "/etc/zabbix/zabbix_agent2.d",
    "agent": "/etc/zabbix/zabbix_agentd.conf.d",
}

SUDOERS_FILE = "/etc/sudoers.d/pvx-zabbix"
SUDOERS_USER = "zabbix"

# scripts que o pvx distribui (known_scripts.CATALOG) são copiados pra cá --
# caminho fixo de sistema, mundo-legível/executável, nunca $HOME (mesma lição
# do core.pyz: sudo troca $HOME, o agente zabbix roda como usuário próprio).
PVX_SCRIPTS_DIR = "/etc/zabbix/pvx-scripts.d"

SCRIPTS_STATE_FILENAME = "scripts.json"
SCRIPTS_CONF_FILENAME = "pvx-scripts.conf"

PROVIDERS = ("ovh", "qnax", "aws", "eveo", "local")
