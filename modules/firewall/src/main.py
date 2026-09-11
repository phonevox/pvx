import ipaddress
import os
import sys

import click

from pvx import config as pvx_config
from pvx.interactive import widgets
from pvx.interactive.inputs import ask_confirm, ask_text
from pvx.modules.base import PvxModule

import asterisk_ips
import defaults
import lists
import session_ip
import status as status_module
import sync as sync_module
import systemd_unit
import validators

ENGINE_CHOICE = click.Choice(["iptables", "firewalld"])


def _state_dir():
    return pvx_config.modules_dir() / "firewall" / "state"


def _list_path(key):
    return _state_dir() / defaults.CONFIG_FILENAMES[key]


def _read(key):
    return lists.read_list(_list_path(key), seed=defaults.DEFAULT_LISTS[key])


def _is_interactive():
    return sys.stdin.isatty()


def _require_root():
    if os.geteuid() != 0:
        raise click.ClickException("firewall precisa rodar como root (sudo).")


def _resolve_arg(value, prompt, usage):
    if value is not None:
        return value
    if not _is_interactive():
        raise click.ClickException(usage)
    return ask_text(prompt)


def _echo_list(label, entries):
    widgets.section(label)
    if not entries:
        widgets.description("(vazio)")
        return
    for entry, comment in entries:
        widgets.item(entry, comment)


class FirewallModule(PvxModule):
    name = "firewall"
    version = "0.2.15"

    def cli_group(self):
        @click.group(name="firewall")
        def group():
            pass

        @group.group(name="port", help="libera/bloqueia portas.")
        def port_group():
            pass

        @port_group.command(name="accept", help="libera uma porta/faixa.")
        @click.argument("spec", required=False, default=None)
        @click.option("--comment", default="")
        def port_accept_cmd(spec, comment):
            _require_root()
            spec = _resolve_arg(
                spec, "Porta/faixa (ex.: 5060/udp, 10000-20000/tcp):",
                "informe a porta: `pvx firewall port accept <spec> [--comment]`.",
            )
            if spec is None:
                return
            try:
                validators.parse_port_spec(spec)
            except ValueError as e:
                raise click.ClickException(str(e))
            lists.add_entry(_list_path("port_accept"), spec, comment, seed=defaults.DEFAULT_LISTS["port_accept"])
            click.echo(f"porta {spec} liberada.")
            if _is_interactive():
                widgets.pause()

        @port_group.command(name="deny", help="bloqueia uma porta/faixa.")
        @click.argument("spec", required=False, default=None)
        @click.option("--comment", default="")
        def port_deny_cmd(spec, comment):
            _require_root()
            spec = _resolve_arg(
                spec, "Porta/faixa (ex.: 5060/udp, 10000-20000/tcp):",
                "informe a porta: `pvx firewall port deny <spec> [--comment]`.",
            )
            if spec is None:
                return
            try:
                validators.parse_port_spec(spec)
            except ValueError as e:
                raise click.ClickException(str(e))
            lists.add_entry(_list_path("port_deny"), spec, comment, seed=defaults.DEFAULT_LISTS["port_deny"])
            click.echo(f"porta {spec} bloqueada.")
            if _is_interactive():
                widgets.pause()

        @port_group.command(name="remove", help="remove uma porta das listas de liberação/bloqueio.")
        @click.argument("spec", required=False, default=None)
        def port_remove_cmd(spec):
            _require_root()
            spec = _resolve_arg(
                spec, "Porta/faixa a remover:", "informe a porta: `pvx firewall port remove <spec>`.",
            )
            if spec is None:
                return
            removed = lists.remove_entry(_list_path("port_accept"), spec, seed=defaults.DEFAULT_LISTS["port_accept"])
            removed = lists.remove_entry(
                _list_path("port_deny"), spec, seed=defaults.DEFAULT_LISTS["port_deny"],
            ) or removed
            if not removed:
                raise click.ClickException(f"{spec} não está em nenhuma lista de portas.")
            click.echo(f"{spec} removido.")
            if _is_interactive():
                widgets.pause()

        @port_group.command(name="list", help="lista as portas liberadas e bloqueadas.")
        def port_list_cmd():
            _echo_list("Portas liberadas", _read("port_accept"))
            _echo_list("Portas bloqueadas", _read("port_deny"))
            if _is_interactive():
                widgets.pause()

        @group.group(name="ip", help="libera/bloqueia IPs e faixas (CIDR).")
        def ip_group():
            pass

        @ip_group.command(
            name="accept", help="adiciona um ou mais IP/CIDR (separados por vírgula) à lista de confiáveis.",
        )
        @click.argument("cidr", required=False, default=None)
        @click.option("--comment", default="")
        def ip_accept_cmd(cidr, comment):
            _require_root()
            cidr = _resolve_arg(
                cidr, "IP/CIDR (ex.: 203.0.113.9, 10.0.0.0/8 -- vários separados por vírgula):",
                "informe o CIDR: `pvx firewall ip accept <cidr>[,<cidr>...] [--comment]`.",
            )
            if cidr is None:
                return
            try:
                entries = validators.parse_cidr_list(cidr)
            except ValueError as e:
                raise click.ClickException(str(e))
            for entry in entries:
                added = lists.add_entry(_list_path("ip_accept"), entry, comment, seed=defaults.DEFAULT_LISTS["ip_accept"])
                verb = "adicionado à" if added else "já estava na"
                click.echo(f"{entry} {verb} lista de confiáveis.")
            if _is_interactive():
                widgets.pause()

        @ip_group.command(
            name="deny", help="adiciona um ou mais IP/CIDR (separados por vírgula) à lista de bloqueio.",
        )
        @click.argument("cidr", required=False, default=None)
        @click.option("--comment", default="")
        @click.option("--force", is_flag=True, help="ignora a checagem de auto-bloqueio")
        def ip_deny_cmd(cidr, comment, force):
            _require_root()
            cidr = _resolve_arg(
                cidr, "IP/CIDR (ex.: 203.0.113.9, 10.0.0.0/8 -- vários separados por vírgula):",
                "informe o CIDR: `pvx firewall ip deny <cidr>[,<cidr>...] [--comment] [--force]`.",
            )
            if cidr is None:
                return
            try:
                entries = validators.parse_cidr_list(cidr)
            except ValueError as e:
                raise click.ClickException(str(e))
            if not force:
                session = session_ip.detect_session_ip()
                if session:
                    session_addr = ipaddress.ip_address(session)
                    self_banning = [
                        entry for entry in entries
                        if session_addr in ipaddress.ip_network(entry, strict=False)
                    ]
                    if self_banning:
                        raise click.ClickException(
                            f"{', '.join(self_banning)} inclui o IP da sua sessão atual ({session}) -- "
                            "use --force se tiver certeza."
                        )
            for entry in entries:
                added = lists.add_entry(_list_path("ip_deny"), entry, comment, seed=defaults.DEFAULT_LISTS["ip_deny"])
                verb = "adicionado à" if added else "já estava na"
                click.echo(f"{entry} {verb} lista de bloqueio.")
            if _is_interactive():
                widgets.pause()

        @ip_group.command(name="remove", help="remove um IP das listas de confiáveis/bloqueio.")
        @click.argument("cidr", required=False, default=None)
        def ip_remove_cmd(cidr):
            _require_root()
            cidr = _resolve_arg(
                cidr, "IP/CIDR a remover:", "informe o CIDR: `pvx firewall ip remove <cidr>`.",
            )
            if cidr is None:
                return
            removed = lists.remove_entry(_list_path("ip_accept"), cidr, seed=defaults.DEFAULT_LISTS["ip_accept"])
            removed = lists.remove_entry(
                _list_path("ip_deny"), cidr, seed=defaults.DEFAULT_LISTS["ip_deny"],
            ) or removed
            if not removed:
                raise click.ClickException(f"{cidr} não está em nenhuma lista de IPs.")
            click.echo(f"{cidr} removido.")
            if _is_interactive():
                widgets.pause()

        @ip_group.command(
            name="trust-phonevox",
            help="garante os IPs base da Phonevox na lista de confiáveis (upsert, nunca duplica).",
        )
        def ip_trust_phonevox_cmd():
            _require_root()
            added = []
            for ip, comment in defaults.DEFAULT_LISTS["ip_accept"]:
                if lists.add_entry(_list_path("ip_accept"), ip, comment, seed=defaults.DEFAULT_LISTS["ip_accept"]):
                    added.append(ip)

            if added:
                click.echo(f"{len(added)} IP(s) adicionado(s) à lista de confiáveis: {', '.join(added)}")
            else:
                click.echo("nenhum IP novo -- todos já estavam na lista de confiáveis.")
            if _is_interactive():
                widgets.pause()

        @ip_group.command(
            name="trust-asterisk",
            help="adiciona os IPs conectados no Asterisk à lista de confiáveis.",
        )
        def ip_trust_asterisk_cmd():
            _require_root()
            found = asterisk_ips.discover_asterisk_ips()
            if not found:
                click.echo("nenhum IP encontrado no Asterisk.")
                if _is_interactive():
                    widgets.pause()
                return

            added = []
            for ip, source in sorted(found.items()):
                if lists.add_entry(_list_path("ip_accept"), ip, source, seed=defaults.DEFAULT_LISTS["ip_accept"]):
                    added.append(ip)

            if added:
                click.echo(f"{len(added)} IP(s) adicionado(s) à lista de confiáveis: {', '.join(added)}")
            else:
                click.echo("nenhum IP novo -- todos já estavam na lista de confiáveis.")
            if _is_interactive():
                widgets.pause()

        @ip_group.command(name="list", help="lista os IPs confiáveis e bloqueados.")
        def ip_list_cmd():
            _echo_list("IPs confiáveis", _read("ip_accept"))
            _echo_list("IPs bloqueados", _read("ip_deny"))
            if _is_interactive():
                widgets.pause()

        @group.command(name="check", help="mostra engine, IPs, portas e se o firewall está ativo agora.")
        @click.option("--engine", default=None, type=ENGINE_CHOICE)
        def check_cmd(engine):
            result = status_module.get_status(engine=engine, base_dir=_state_dir())
            engine_state = "ativo" if result["engine_active"] else "inativo"
            boot_state = "habilitado" if result["boot_persistent"] else "desabilitado"

            widgets.title("pvx > firewall > check")
            widgets.section("Status")
            click.echo(f"  engine: {result['engine']} ({engine_state})")
            if result.get("firewalld_zone"):
                click.echo(f"  zona firewalld: {result['firewalld_zone']}")
            click.echo(f"  reaplica no boot: {boot_state}")
            click.echo(f"  IP da sessão: {result['session_ip'] or 'não detectado'}")
            click.echo()

            if result["synced"]:
                detail = f"sincronizado -- {result['rule_count']} regra(s) ativa(s)"
                widgets.state(detail, ok=True)
                if result["session_ip"] and not result["failsafe_ok"]:
                    widgets.warning("IP da sessão atual sem failsafe confirmado, rode `apply` de novo")
            else:
                widgets.state("não sincronizado -- rode `pvx firewall apply` pra aplicar as regras", ok=False)

            if result["lists"]:
                _echo_list("IPs confiáveis", result["lists"]["ip_accept"])
                _echo_list("IPs bloqueados", result["lists"]["ip_deny"])
                _echo_list("Portas liberadas", result["lists"]["port_accept"])
                _echo_list("Portas bloqueadas", result["lists"]["port_deny"])

            if _is_interactive():
                widgets.pause()

        @group.command(name="apply", help="aplica as listas no firewall de verdade (iptables/firewalld).")
        @click.option("--engine", default=None, type=ENGINE_CHOICE)
        @click.option("--force", is_flag=True, help="prossegue mesmo sem detectar o IP da sessão atual")
        @click.option("--yes", is_flag=True)
        def apply_cmd(engine, force, yes):
            _require_root()
            logger = self.get_logger()
            if not yes and not ask_confirm(
                "Isso vai reescrever as regras de firewall deste host. Confirma?", default=False
            ):
                click.echo("Operação cancelada.")
                if _is_interactive():
                    widgets.pause()
                return

            try:
                with widgets.spinner("Sincronizando firewall..."):
                    result = sync_module.run(str(_state_dir()), engine=engine, force=force)
            except Exception as e:
                logger.error(f"apply falhou: {e}")
                widgets.failed(str(e))
                if _is_interactive():
                    widgets.pause()
                return

            logger.info(f"firewall sincronizado (engine: {result['engine']}).")
            widgets.success(f"firewall sincronizado (engine: {result['engine']}).")
            if result["session_ip"] is None:
                click.echo("aviso: IP da sessão não detectado -- nenhum failsafe foi inserido (rodou com --force).")
            if _is_interactive():
                widgets.pause()

        @group.command(name="start-on-boot", help="instala um serviço systemd que reaplica o firewall no boot.")
        @click.option("--dry-run", is_flag=True)
        @click.option("--pvx-bin", default="/usr/local/bin/pvx")
        def start_on_boot_cmd(dry_run, pvx_bin):
            _require_root()
            content = systemd_unit.install(pvx_bin=pvx_bin, dry_run=dry_run)
            if dry_run:
                click.echo(content)
            else:
                self.get_logger().info("serviço pvx-firewall habilitado no boot.")
                widgets.success("serviço pvx-firewall habilitado no boot.")
            if _is_interactive():
                widgets.pause()

        return group


cli = FirewallModule()
