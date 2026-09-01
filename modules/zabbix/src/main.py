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
import known_scripts
import metadata
import scripts
import sudoers
import system_info

_AGENT_VARIANT_FILENAME = "agent_variant.txt"
_MANUAL_PROVIDER_LABEL = "Definir manualmente..."


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
        raise click.ClickException("zabbix ainda não foi instalado -- rode `pvx zabbix setup` primeiro.")
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
    version = "0.2.0"

    def cli_group(self):
        @click.group(name="zabbix")
        def group():
            pass

        @group.command(name="setup")
        @click.option("--server", default=None)
        @click.option("--server-active", default=None)
        @click.option("--hostname", default=None)
        @click.option(
            "--metadata", "extra_metadata", default=None,
            help="HostMetadata literal, sobrescreve o auto-calculado (sem terminal pra editar).",
        )
        @click.option("--provider", default=None, help="location conhecida ou qualquer texto livre.")
        @click.option("--agent-version", type=click.Choice(defaults.AGENT_VARIANTS), default=None)
        @click.option("--test", is_flag=True)
        @click.option("--yes", is_flag=True)
        def setup_cmd(server, server_active, hostname, extra_metadata, provider, agent_version, test, yes):
            if os.geteuid() != 0:
                raise click.ClickException("zabbix precisa rodar como root (sudo).")

            logger = self.get_logger()
            interactive = _is_interactive()

            existing_package = install_steps.detect_existing_agent(defaults.AGENT_PACKAGES.values())
            legacy_sudo = sudoers.detect_legacy_rule()
            if existing_package or legacy_sudo:
                widgets.state("zabbix já parece instalado nessa máquina (possivelmente via pzabbix):", ok=False)
                if existing_package:
                    click.echo(f"  - pacote já instalado: {existing_package}")
                if legacy_sudo:
                    click.echo(
                        "  - regra sudoers antiga e insegura em /etc/sudoers "
                        "(%zabbix ALL=(ALL) NOPASSWD: ALL)"
                    )
                if not yes:
                    if not interactive:
                        raise click.ClickException(
                            "zabbix já instalado nessa máquina -- use --yes pra sobrescrever mesmo assim."
                        )
                    if not ask_confirm("Sobrescrever a instalação existente?", default=False):
                        widgets.message("nada foi alterado.")
                        widgets.pause()
                        return

            os_release = system_info.read_os_release()
            os_major = os_release.get("VERSION_ID", "0").split(".")[0]
            os_label = system_info.os_label(os_release)

            if provider is None:
                with widgets.spinner("Detectando provider..."):
                    detected_provider = system_info.detect_provider()
                if interactive:
                    widgets.success(f"provider detectado: {detected_provider}")
                    choices = list(defaults.PROVIDERS) + [_MANUAL_PROVIDER_LABEL]
                    provider = ask_select("Provider (location):", choices, default=detected_provider)
                    if provider is None:
                        return
                    if provider == _MANUAL_PROVIDER_LABEL:
                        provider = ask_text("Digite a location:")
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
                with widgets.spinner("Detectando hostname..."):
                    detected_hostname = system_info.detect_hostname(provider)
                if interactive:
                    widgets.success(f"hostname detectado: {detected_hostname}")
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
                widgets.message("nada foi alterado.")
                if interactive:
                    widgets.pause()
                return

            with widgets.spinner("Adicionando repositório do Zabbix..."):
                repo_ok = install_steps.install_repo(defaults.ZABBIX_VERSION, os_major)
            if not repo_ok:
                logger.error("falha ao adicionar o repositório do Zabbix.")
                raise click.ClickException("falha ao adicionar o repositório do Zabbix.")
            widgets.success("Repositório adicionado.")

            package = defaults.AGENT_PACKAGES[agent_version]
            if existing_package and existing_package != package:
                # variante diferente da já instalada (ex.: trocando pzabbix/agent
                # clássico por agent2) -- os dois disputariam a mesma porta 10050.
                with widgets.spinner(f"Removendo {existing_package} antigo..."):
                    install_steps.remove_agent(existing_package)
                widgets.success(f"{existing_package} antigo removido.")

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

            if legacy_sudo:
                sudoers.remove_legacy_rule()
                widgets.success("regra sudoers antiga (insegura) removida de /etc/sudoers.")

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

        @group.command(name="remove")
        @click.option("--yes", is_flag=True)
        def remove_cmd(yes):
            if os.geteuid() != 0:
                raise click.ClickException("zabbix precisa rodar como root (sudo).")

            logger = self.get_logger()
            interactive = _is_interactive()

            variant_path = _state_dir() / _AGENT_VARIANT_FILENAME
            if not variant_path.exists():
                click.echo("zabbix não está configurado pelo pvx -- nada a remover.")
                if interactive:
                    widgets.pause()
                return

            agent_variant = variant_path.read_text().strip()
            package = defaults.AGENT_PACKAGES[agent_variant]
            service = defaults.AGENT_SERVICES[agent_variant]

            if not yes and not ask_confirm(
                f"Isso vai remover o Zabbix ({package}) e as configurações dele nessa máquina. Confirma?",
                default=False,
            ):
                widgets.message("nada foi alterado.")
                if interactive:
                    widgets.pause()
                return

            with widgets.spinner(f"Parando {service}..."):
                install_steps.disable_and_stop(service)

            with widgets.spinner(f"Removendo {package}..."):
                install_steps.remove_agent(package)

            state_path = str(_state_dir() / defaults.SCRIPTS_STATE_FILENAME)
            for key in scripts.list_all(state_path):
                known_scripts.remove_deployed(defaults.PVX_SCRIPTS_DIR, key)
            sudoers.remove(defaults.SUDOERS_FILE)

            confd_dir = defaults.AGENT_CONFD_DIRS[agent_variant]
            try:
                os.remove(os.path.join(confd_dir, defaults.SCRIPTS_CONF_FILENAME))
            except FileNotFoundError:
                pass

            for name in (defaults.SCRIPTS_STATE_FILENAME, _AGENT_VARIANT_FILENAME):
                try:
                    (_state_dir() / name).unlink()
                except FileNotFoundError:
                    pass

            logger.info(f"zabbix ({agent_variant}) removido.")
            widgets.success("zabbix removido.")
            if interactive:
                widgets.pause()

        @group.command(name="check")
        def check_cmd():
            variant_path = _state_dir() / _AGENT_VARIANT_FILENAME
            legacy_sudo = sudoers.detect_legacy_rule()
            if not variant_path.exists():
                # marcador do pvx ausente não significa "não instalado" -- pode ter
                # vindo do pzabbix (script bash antigo) ou de instalação manual.
                existing_package = install_steps.detect_existing_agent(defaults.AGENT_PACKAGES.values())
                if existing_package:
                    widgets.state(
                        f"Zabbix ({existing_package}) instalado mas NÃO gerenciado pelo pvx "
                        "-- rode `pvx zabbix setup` pra assumir.",
                        ok=False,
                    )
                else:
                    widgets.state("Zabbix NÃO configurado -- rode `pvx zabbix setup` primeiro.", ok=False)
                if legacy_sudo:
                    click.echo(
                        "  aviso: regra sudoers antiga e insegura em /etc/sudoers "
                        "(%zabbix ALL=(ALL) NOPASSWD: ALL)"
                    )
                if _is_interactive():
                    widgets.pause()
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

            if legacy_sudo:
                click.echo()
                click.echo(
                    "aviso: regra sudoers antiga e insegura ainda presente em /etc/sudoers "
                    "(%zabbix ALL=(ALL) NOPASSWD: ALL) -- rode `pvx zabbix setup` de novo pra limpar."
                )

            if _is_interactive():
                widgets.pause()

        @group.group(name="scripts")
        def script_group():
            pass

        @script_group.command(name="add")
        @click.argument("key", required=False, default=None)
        def script_add_cmd(key):
            # só scripts do catálogo do pvx (known_scripts.CATALOG) -- nunca comando
            # arbitrário. quem quiser um script próprio mexe direto na pasta do zabbix.
            logger = self.get_logger()
            interactive = _is_interactive()
            agent_variant = _current_agent_variant()
            catalog_hint = ", ".join(sorted(known_scripts.CATALOG))

            if key is None:
                if not interactive:
                    raise click.ClickException(f"informe a chave: `pvx zabbix scripts add <chave>` ({catalog_hint}).")
                choices = [
                    f"{k} -- {v['description']}" for k, v in sorted(known_scripts.CATALOG.items())
                ]
                label = ask_select("Script do pvx pra adicionar:", choices)
                if label is None:
                    return
                key = label.split(" -- ")[0]

            if key not in known_scripts.CATALOG:
                raise click.ClickException(f"script desconhecido: '{key}' (opções: {catalog_hint}).")

            entry = known_scripts.CATALOG[key]
            dest_path = known_scripts.deploy(defaults.PVX_SCRIPTS_DIR, key)
            command = f"{dest_path} {entry['args']}".strip()

            state_path = str(_state_dir() / defaults.SCRIPTS_STATE_FILENAME)
            try:
                entries = scripts.add(state_path, key, command, needs_root=entry["needs_root"])
            except KeyError as e:
                raise click.ClickException(str(e))

            _sync_scripts(entries, agent_variant)
            logger.info(f"script '{key}' adicionado (needs_root={entry['needs_root']}).")
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
                    raise click.ClickException("informe a chave: `pvx zabbix scripts remove <chave>`.")
                existing = scripts.list_all(state_path)
                if not existing:
                    click.echo("nenhum script cadastrado.")
                    if interactive:
                        widgets.pause()
                    return
                key = ask_select("Remover qual script?", list(existing))
                if key is None:
                    return

            try:
                entries = scripts.remove(state_path, key)
            except KeyError as e:
                raise click.ClickException(str(e))

            known_scripts.remove_deployed(defaults.PVX_SCRIPTS_DIR, key)
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
