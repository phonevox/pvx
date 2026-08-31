import os
import sys

import click

from pvx import config as pvx_config
from pvx.interactive import widgets
from pvx.interactive.inputs import ask_confirm, ask_select, ask_text
from pvx.modules.base import PvxModule

import config
import defaults
import install_steps
import metadata
import scripts
import sudoers
import system_info

_AGENT_VARIANT_FILENAME = "agent_variant.txt"


def _is_interactive():
    return sys.stdin.isatty()


def _state_dir():
    path = pvx_config.modules_dir() / "zabbix" / "state"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _save_agent_variant(variant):
    (_state_dir() / _AGENT_VARIANT_FILENAME).write_text(variant)


def _current_agent_variant():
    path = _state_dir() / _AGENT_VARIANT_FILENAME
    if not path.exists():
        raise click.ClickException("zabbix ainda não foi instalado -- rode `pvx zabbix install` primeiro.")
    return path.read_text().strip()


def _write_confd_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").write(content)


def _sync_scripts(entries, agent_variant):
    confd_dir = defaults.AGENT_CONFD_DIRS[agent_variant]
    conf_path = os.path.join(confd_dir, defaults.SCRIPTS_CONF_FILENAME)
    _write_confd_file(conf_path, scripts.render_userparameter_conf(entries))
    sudoers.write_rules(defaults.SUDOERS_FILE, defaults.SUDOERS_USER, scripts.root_requiring_commands(entries))


class ZabbixModule(PvxModule):
    name = "zabbix"
    version = "0.1.1"

    def cli_group(self):
        @click.group(name="zabbix")
        def group():
            pass

        @group.command(name="install")
        @click.option("--server", default=None)
        @click.option("--server-active", default=None)
        @click.option("--hostname", default=None)
        @click.option(
            "--metadata", "extra_metadata", default=None,
            help="HostMetadata literal, sobrescreve o auto-calculado (sem terminal pra editar).",
        )
        @click.option("--provider", type=click.Choice(defaults.PROVIDERS), default=None)
        @click.option("--agent-version", type=click.Choice(defaults.AGENT_VARIANTS), default=None)
        @click.option("--test", is_flag=True)
        @click.option("--yes", is_flag=True)
        def install_cmd(server, server_active, hostname, extra_metadata, provider, agent_version, test, yes):
            if os.geteuid() != 0:
                raise click.ClickException("zabbix precisa rodar como root (sudo).")

            logger = self.get_logger()
            interactive = _is_interactive()

            os_release = system_info.read_os_release()
            os_major = os_release.get("VERSION_ID", "0").split(".")[0]
            os_label = system_info.os_label(os_release)

            if provider is None:
                detected_provider = system_info.detect_provider()
                if interactive:
                    provider = ask_select("Provider (location):", list(defaults.PROVIDERS), default=detected_provider)
                    if provider is None:
                        return
                else:
                    provider = detected_provider

            if agent_version is None:
                if interactive:
                    label = ask_select(
                        "Versão do Zabbix Agent:", ["Agent 2 (recomendado)", "Agent clássico"],
                        default="Agent 2 (recomendado)",
                    )
                    if label is None:
                        return
                    agent_version = "agent2" if label.startswith("Agent 2") else "agent"
                else:
                    agent_version = "agent2"

            if hostname is None:
                detected_hostname = system_info.detect_hostname(provider)
                if interactive:
                    hostname = ask_text("Hostname (identificação no Zabbix):", default=detected_hostname)
                    if hostname is None:
                        return
                else:
                    hostname = detected_hostname

            if not server and interactive:
                server = ask_text("Zabbix Server (endereço):")
                if server is None:
                    return
            if not server:
                raise click.ClickException("informe --server (endereço do Zabbix server).")

            if server_active is None:
                if interactive:
                    server_active = ask_text("ServerActive (checks ativos):", default=server)
                    if server_active is None:
                        return
                else:
                    server_active = server

            if not test and interactive:
                test = ask_confirm("Esta é uma máquina de teste?", default=False)

            asterisk_version = system_info.asterisk_version()
            auto_metadata = metadata.build(
                provider=provider, os_label=os_label, asterisk_version=asterisk_version, test=test,
            )
            if interactive:
                # edita o valor inteiro ali mesmo -- sem prompt separado de "extra", já
                # que na prática o usuário quase sempre só aperta Enter e aceita o
                # auto-calculado como está.
                host_metadata = ask_text("HostMetadata (edite se quiser, ou só Enter):", default=auto_metadata)
                if host_metadata is None:
                    return
            else:
                host_metadata = extra_metadata if extra_metadata else auto_metadata
            metadata.validate(host_metadata)

            click.echo("Resumo:")
            click.echo(f"  Agent: {defaults.AGENT_PACKAGES[agent_version]}")
            click.echo(f"  Server: {server}")
            click.echo(f"  ServerActive: {server_active}")
            click.echo(f"  Hostname: {hostname}")
            click.echo(f"  HostMetadata: {host_metadata}")
            if not yes and not ask_confirm("Prosseguir com a instalação?", default=False):
                click.echo("Operação cancelada.")
                return

            with widgets.spinner("Adicionando repositório do Zabbix..."):
                repo_ok = install_steps.install_repo(defaults.ZABBIX_VERSION, os_major)
            if not repo_ok:
                logger.error("falha ao adicionar o repositório do Zabbix.")
                raise click.ClickException("falha ao adicionar o repositório do Zabbix.")
            widgets.success("Repositório adicionado.")

            package = defaults.AGENT_PACKAGES[agent_version]
            with widgets.spinner(f"Instalando {package}..."):
                agent_ok = install_steps.install_agent(package)
            if not agent_ok:
                logger.error(f"falha ao instalar {package}.")
                raise click.ClickException(f"falha ao instalar {package}.")
            widgets.success(f"{package} instalado.")

            config_path = defaults.AGENT_CONFIG_PATHS[agent_version]
            confd_dir = defaults.AGENT_CONFD_DIRS[agent_version]
            config.set_params(config_path, {
                "Server": server,
                "ServerActive": server_active,
                "Hostname": hostname,
                "HostMetadata": host_metadata,
            })
            config.ensure_include(config_path, confd_dir)
            widgets.success("Configuração aplicada.")
            _save_agent_variant(agent_version)

            service = defaults.AGENT_SERVICES[agent_version]
            with widgets.spinner("Reiniciando o serviço..."):
                start_ok = install_steps.enable_and_start(service)
            if not start_ok:
                logger.error(f"falha ao (re)iniciar {service}.")
                raise click.ClickException(
                    f"falha ao (re)iniciar {service} -- confere `systemctl status {service}`."
                )
            widgets.success(f"{service} rodando.")
            logger.info(f"zabbix ({agent_version}) instalado -- hostname={hostname} metadata={host_metadata}")

            if interactive:
                widgets.pause()

        @group.command(name="check")
        def check_cmd():
            variant_path = _state_dir() / _AGENT_VARIANT_FILENAME
            if not variant_path.exists():
                widgets.state("Zabbix NÃO configurado -- rode `pvx zabbix install` primeiro.", ok=False)
                return

            agent_variant = variant_path.read_text().strip()
            service = defaults.AGENT_SERVICES[agent_variant]
            params = config.read_params(defaults.AGENT_CONFIG_PATHS[agent_variant])
            status = install_steps.service_status(service)

            widgets.state(f"Zabbix configurado ({defaults.AGENT_PACKAGES[agent_variant]})", ok=True)
            click.echo(f"  Server: {params.get('Server', '-')}")
            click.echo(f"  ServerActive: {params.get('ServerActive', '-')}")
            click.echo(f"  Hostname: {params.get('Hostname', '-')}")
            click.echo(f"  HostMetadata: {params.get('HostMetadata', '-')}")
            click.echo()

            active_ok = status["active"] == "active"
            enabled_ok = status["enabled"] == "enabled"
            widgets.state(f"Serviço {service}: {'ativo' if active_ok else 'inativo'}", ok=active_ok)
            widgets.state(f"Habilitado no boot: {'sim' if enabled_ok else 'não'}", ok=enabled_ok)
            click.echo()

            entries = scripts.list_all(str(_state_dir() / defaults.SCRIPTS_STATE_FILENAME))
            if not entries:
                click.echo("Scripts customizados: nenhum cadastrado.")
            else:
                click.echo(f"Scripts customizados ({len(entries)}):")
                for key in sorted(entries):
                    suffix = " (root)" if entries[key].get("needs_root") else ""
                    click.echo(f"  {key}: {entries[key]['command']}{suffix}")

            if _is_interactive():
                widgets.pause()

        @group.group(name="script")
        def script_group():
            pass

        @script_group.command(name="add")
        @click.argument("key", required=False, default=None)
        @click.argument("command", required=False, default=None)
        @click.option("--needs-root", is_flag=True)
        def script_add_cmd(key, command, needs_root):
            logger = self.get_logger()
            interactive = _is_interactive()
            agent_variant = _current_agent_variant()

            if key is None:
                if not interactive:
                    raise click.ClickException("informe a chave: `pvx zabbix script add <chave> <comando>`.")
                key = ask_text("Chave do item (ex.: disco.custom):")
                if key is None:
                    return
            if command is None:
                if not interactive:
                    raise click.ClickException("informe o comando: `pvx zabbix script add <chave> <comando>`.")
                command = ask_text("Comando a executar:")
                if command is None:
                    return
            if not needs_root and interactive:
                needs_root = ask_confirm("Esse comando precisa de root?", default=False)

            state_path = str(_state_dir() / defaults.SCRIPTS_STATE_FILENAME)
            try:
                entries = scripts.add(state_path, key, command, needs_root=needs_root)
            except KeyError as e:
                raise click.ClickException(str(e))

            _sync_scripts(entries, agent_variant)
            logger.info(f"script '{key}' adicionado (needs_root={needs_root}).")
            widgets.success(f"script '{key}' adicionado.")
            if interactive:
                widgets.pause()

        @script_group.command(name="remove")
        @click.argument("key", required=False, default=None)
        def script_remove_cmd(key):
            logger = self.get_logger()
            interactive = _is_interactive()
            agent_variant = _current_agent_variant()
            state_path = str(_state_dir() / defaults.SCRIPTS_STATE_FILENAME)

            if key is None:
                if not interactive:
                    raise click.ClickException("informe a chave: `pvx zabbix script remove <chave>`.")
                existing = scripts.list_all(state_path)
                if not existing:
                    click.echo("nenhum script cadastrado.")
                    return
                key = ask_select("Remover qual script?", list(existing))
                if key is None:
                    return

            try:
                entries = scripts.remove(state_path, key)
            except KeyError as e:
                raise click.ClickException(str(e))

            _sync_scripts(entries, agent_variant)
            logger.info(f"script '{key}' removido.")
            widgets.success(f"script '{key}' removido.")
            if interactive:
                widgets.pause()

        @script_group.command(name="list")
        def script_list_cmd():
            entries = scripts.list_all(str(_state_dir() / defaults.SCRIPTS_STATE_FILENAME))
            if not entries:
                click.echo("nenhum script cadastrado.")
            for key in sorted(entries):
                suffix = " (root)" if entries[key].get("needs_root") else ""
                click.echo(f"{key}: {entries[key]['command']}{suffix}")
            if _is_interactive():
                widgets.pause()

        return group


cli = ZabbixModule()
