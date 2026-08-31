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
    "agent2": "/etc/zabbix/zabbix_agent2.conf.d",
    "agent": "/etc/zabbix/zabbix_agentd.conf.d",
}

SUDOERS_FILE = "/etc/sudoers.d/pvx-zabbix"
SUDOERS_USER = "zabbix"

SCRIPTS_STATE_FILENAME = "scripts.json"
SCRIPTS_CONF_FILENAME = "pvx-scripts.conf"

PROVIDERS = ("ovh", "qnax", "aws", "eveo", "local")
