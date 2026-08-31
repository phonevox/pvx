import ipaddress
import os
import sys

import click

from pvx import config as pvx_config
from pvx.interactive import widgets
from pvx.interactive.inputs import ask_confirm, ask_text
from pvx.modules.base import PvxModule

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


def _echo_list(title, entries):
    click.echo(title)
    if not entries:
        click.echo("  (vazio)")
    for entry, comment in entries:
        click.echo(f"  {entry}" + (f"  # {comment}" if comment else ""))


class FirewallModule(PvxModule):
    name = "firewall"
    version = "0.1.11"

    def cli_group(self):
        @click.group(name="firewall")
        def group():
            pass

        @group.group(name="port")
        def port_group():
            pass

        @port_group.command(name="accept")
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
            lists.add_entry(_list_path("port_accept"), spec, comment)
            click.echo(f"porta {spec} liberada.")
            if _is_interactive():
                widgets.pause()

        @port_group.command(name="deny")
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
            lists.add_entry(_list_path("port_deny"), spec, comment)
            click.echo(f"porta {spec} bloqueada.")
            if _is_interactive():
                widgets.pause()

        @port_group.command(name="remove")
        @click.argument("spec", required=False, default=None)
        def port_remove_cmd(spec):
            _require_root()
            spec = _resolve_arg(
                spec, "Porta/faixa a remover:", "informe a porta: `pvx firewall port remove <spec>`.",
            )
            if spec is None:
                return
            removed = lists.remove_entry(_list_path("port_accept"), spec)
            removed = lists.remove_entry(_list_path("port_deny"), spec) or removed
            if not removed:
                raise click.ClickException(f"{spec} não está em nenhuma lista de portas.")
            click.echo(f"{spec} removido.")
            if _is_interactive():
                widgets.pause()

        @port_group.command(name="list")
        def port_list_cmd():
            _echo_list("liberadas:", _read("port_accept"))
            _echo_list("bloqueadas:", _read("port_deny"))
            if _is_interactive():
                widgets.pause()

        @group.group(name="ip")
        def ip_group():
            pass

        @ip_group.command(name="accept")
        @click.argument("cidr", required=False, default=None)
        @click.option("--comment", default="")
        def ip_accept_cmd(cidr, comment):
            _require_root()
            cidr = _resolve_arg(
                cidr, "IP/CIDR (ex.: 203.0.113.9, 10.0.0.0/8):",
                "informe o CIDR: `pvx firewall ip accept <cidr> [--comment]`.",
            )
            if cidr is None:
                return
            if not validators.validate_cidr(cidr):
                raise click.ClickException(f"CIDR inválido: {cidr}")
            lists.add_entry(_list_path("ip_accept"), cidr, comment)
            click.echo(f"{cidr} adicionado à lista de confiáveis.")
            if _is_interactive():
                widgets.pause()

        @ip_group.command(name="deny")
        @click.argument("cidr", required=False, default=None)
        @click.option("--comment", default="")
        @click.option("--force", is_flag=True, help="ignora a checagem de auto-bloqueio")
        def ip_deny_cmd(cidr, comment, force):
            _require_root()
            cidr = _resolve_arg(
                cidr, "IP/CIDR (ex.: 203.0.113.9, 10.0.0.0/8):",
                "informe o CIDR: `pvx firewall ip deny <cidr> [--comment] [--force]`.",
            )
            if cidr is None:
                return
            if not validators.validate_cidr(cidr):
                raise click.ClickException(f"CIDR inválido: {cidr}")
            if not force:
                session = session_ip.detect_session_ip()
                if session and ipaddress.ip_address(session) in ipaddress.ip_network(cidr, strict=False):
                    raise click.ClickException(
                        f"{cidr} inclui o IP da sua sessão atual ({session}) -- use --force se tiver certeza."
                    )
            lists.add_entry(_list_path("ip_deny"), cidr, comment)
            click.echo(f"{cidr} adicionado à lista de bloqueio.")
            if _is_interactive():
                widgets.pause()

        @ip_group.command(name="remove")
        @click.argument("cidr", required=False, default=None)
        def ip_remove_cmd(cidr):
            _require_root()
            cidr = _resolve_arg(
                cidr, "IP/CIDR a remover:", "informe o CIDR: `pvx firewall ip remove <cidr>`.",
            )
            if cidr is None:
                return
            removed = lists.remove_entry(_list_path("ip_accept"), cidr)
            removed = lists.remove_entry(_list_path("ip_deny"), cidr) or removed
            if not removed:
                raise click.ClickException(f"{cidr} não está em nenhuma lista de IPs.")
            click.echo(f"{cidr} removido.")
            if _is_interactive():
                widgets.pause()

        @ip_group.command(name="list")
        def ip_list_cmd():
            _echo_list("confiáveis:", _read("ip_accept"))
            _echo_list("bloqueados:", _read("ip_deny"))
            if _is_interactive():
                widgets.pause()

        @group.command(name="status")
        @click.option("--engine", default=None, type=ENGINE_CHOICE)
        def status_cmd(engine):
            result = status_module.get_status(engine=engine)
            click.echo(f"engine: {result['engine']}")
            click.echo(f"IP da sessão: {result['session_ip'] or 'não detectado'}")
            click.echo()

            if result["synced"]:
                detail = f"sincronizado -- {result['rule_count']} regra(s) ativa(s)"
                if result["session_ip"] and not result["failsafe_ok"]:
                    detail += " -- atenção: IP da sessão atual sem failsafe confirmado, rode `sync` de novo"
                widgets.state(detail, ok=True)
            else:
                widgets.state("não sincronizado -- rode `pvx firewall sync` pra aplicar as regras", ok=False)

            if _is_interactive():
                widgets.pause()

        @group.command(name="sync")
        @click.option("--engine", default=None, type=ENGINE_CHOICE)
        @click.option("--force", is_flag=True, help="prossegue mesmo sem detectar o IP da sessão atual")
        @click.option("--yes", is_flag=True)
        def sync_cmd(engine, force, yes):
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
                logger.error(f"sync falhou: {e}")
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

        @group.command(name="start-on-boot")
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
