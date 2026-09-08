import os
import sys

import click

from pvx.interactive import widgets
from pvx.interactive.inputs import ask_confirm, ask_select, ask_text
from pvx.modules.base import PvxModule

import certbot_ops
import cron
import firewall_guard
import packages
import system_detect
import validators
import vhost

DEFAULT_EMAIL = "suporte@phonevox.com.br"
_RENEW_WARNING_DAYS = 15


def _is_interactive():
    # mesma seam de qint/ssh-hardening: CliRunner troca sys.stdin inteiro durante o
    # invoke(), então mockar sys.stdin.isatty direto não pega.
    return sys.stdin.isatty()


def _require_root():
    if os.geteuid() != 0:
        raise click.ClickException("ssl precisa rodar como root (sudo).")


def _detect_apache():
    distro = system_detect.detect_distro()
    if distro is None:
        raise click.ClickException("sistema não suportado -- use Debian 11+ ou RHEL/CentOS 7+.")
    info = system_detect.apache_info(distro)
    return distro, info["service"], info["conf_dir"]


def _resolve_new_domain(domain, interactive):
    if domain:
        if not validators.is_valid_domain(domain):
            raise click.ClickException(f"domínio inválido: {domain}")
        return domain
    if not interactive:
        raise click.ClickException("informe o domínio.")
    while True:
        entered = ask_text("Domínio (ex.: central.falevox.com.br):")
        if entered is None:
            return None
        if validators.is_valid_domain(entered):
            return entered
        click.echo("domínio inválido -- confira e tente de novo.")


def _resolve_managed_domain(domain, interactive):
    # renew/reissue/remove só agem sobre um domínio que este módulo já geriu --
    # escolher de uma lista existente evita erro de digitação e evita apontar pra um
    # domínio que nunca teve certificado emitido por aqui.
    known = certbot_ops.list_domains()
    if domain:
        if domain not in known:
            raise click.ClickException(
                f"nenhum certificado gerenciado por este host pra {domain} -- "
                "rode `pvx ssl check` pra ver os disponíveis."
            )
        return domain
    if not known:
        click.echo("nenhum domínio com certificado gerenciado por este host ainda.")
        return None
    if not interactive:
        raise click.ClickException("informe o domínio.")
    return ask_select("Domínio:", known)


def _run_setup(logger, domain, email, interactive):
    domain = _resolve_new_domain(domain, interactive)
    if domain is None:
        return
    email = email or DEFAULT_EMAIL
    if not validators.is_valid_email(email):
        raise click.ClickException(f"e-mail inválido: {email}")

    distro, service, conf_dir = _detect_apache()

    with widgets.step("Instalando pacotes (certbot + apache)..."):
        try:
            packages.install(distro)
        except packages.PackageError as e:
            raise click.ClickException(str(e))
    widgets.success("Pacotes instalados.")

    if vhost.exists(conf_dir, domain):
        widgets.message(f"VirtualHost já existe em {vhost.conf_path(conf_dir, domain)} -- pulando criação.")
    else:
        path = vhost.create(conf_dir, domain, email, distro)
        widgets.success(f"VirtualHost criado em {path}.")
    vhost.reload_apache(service)

    try:
        with firewall_guard.temporarily_open(80):
            if not certbot_ops.has_certificate(domain):
                with widgets.step(f"Emitindo certificado pra {domain}..."):
                    certbot_ops.issue(domain, email)
                widgets.success("Certificado emitido.")
            else:
                days_left = certbot_ops.days_until_expiry(domain)
                force = days_left is not None and days_left <= _RENEW_WARNING_DAYS
                with widgets.step("Renovando certificado..."):
                    certbot_ops.renew(domain, force=force)
                widgets.success(f"Certificado renovado (faltavam {days_left} dia(s)).")
    except certbot_ops.CertbotError as e:
        logger.error(f"ssl setup falhou: {e}")
        raise click.ClickException(str(e))

    vhost.reload_apache(service)

    if cron.ensure_scheduled(service):
        widgets.success("Renovação automática agendada (diariamente às 03:00).")
    else:
        widgets.message("Renovação automática já estava agendada.")

    logger.info(f"ssl setup concluído pra {domain}.")
    click.echo(f"SSL ativo pra {domain}. E-mail de registro: {email}")


def _echo_expiry(domain, days_left):
    if days_left is None:
        click.echo(f"{domain}: sem certificado emitido.")
    elif days_left < 0:
        click.echo(f"{domain}: expirado há {-days_left} dia(s).")
    else:
        click.echo(f"{domain}: expira em {days_left} dia(s).")


def _run_check(domain):
    domains = [domain] if domain else certbot_ops.list_domains()
    if not domains:
        click.echo("nenhum domínio com certificado gerenciado por este host ainda.")
        return
    for d in domains:
        _echo_expiry(d, certbot_ops.days_until_expiry(d))


def _run_renew(logger, domain, interactive, force):
    domain = _resolve_managed_domain(domain, interactive)
    if domain is None:
        return
    _, service, _ = _detect_apache()

    try:
        with firewall_guard.temporarily_open(80):
            message = "Reemitindo certificado..." if force else "Renovando certificado..."
            with widgets.step(message):
                certbot_ops.renew(domain, force=force)
    except certbot_ops.CertbotError as e:
        logger.error(f"ssl renew falhou: {e}")
        raise click.ClickException(str(e))

    vhost.reload_apache(service)
    days_left = certbot_ops.days_until_expiry(domain)
    widgets.success(f"certificado de {domain} renovado -- expira em {days_left} dia(s).")
    logger.info(f"ssl renew ({domain}, force={force}) concluído.")


def _run_remove(logger, domain, interactive, yes):
    domain = _resolve_managed_domain(domain, interactive)
    if domain is None:
        return
    if not yes and not ask_confirm(f"Remover o certificado e o VirtualHost de {domain}?", default=False):
        click.echo("Operação cancelada.")
        return

    distro, service, conf_dir = _detect_apache()
    try:
        certbot_ops.remove(domain)
    except certbot_ops.CertbotError as e:
        logger.error(f"ssl remove falhou: {e}")
        raise click.ClickException(str(e))
    vhost.remove(conf_dir, domain, distro)
    vhost.reload_apache(service)

    if not certbot_ops.list_domains():
        cron.remove_scheduled()

    widgets.success(f"certificado e VirtualHost de {domain} removidos.")
    logger.info(f"ssl remove ({domain}) concluído.")


class SslModule(PvxModule):
    name = "ssl"
    version = "0.1.1"

    def cli_group(self):
        @click.group(name="ssl")
        def group():
            pass

        @group.command(name="setup", help="emite/renova o certificado, cria o vhost e agenda a renovação.")
        @click.argument("dominio", required=False, default=None)
        @click.option(
            "--email", default=None,
            help=f"e-mail de registro no Let's Encrypt (padrão: {DEFAULT_EMAIL}).",
        )
        def setup_cmd(dominio, email):
            _require_root()
            logger = self.get_logger()
            interactive = _is_interactive()
            try:
                _run_setup(logger, dominio, email, interactive)
            except click.ClickException:
                raise
            else:
                if interactive:
                    widgets.pause()

        @group.command(name="check", help="mostra quanto tempo falta pro certificado expirar.")
        @click.argument("dominio", required=False, default=None)
        def check_cmd(dominio):
            _require_root()
            _run_check(dominio)
            if _is_interactive():
                widgets.pause()

        @group.command(name="renew", help="renova o certificado agora, só se estiver perto de expirar.")
        @click.argument("dominio", required=False, default=None)
        def renew_cmd(dominio):
            _require_root()
            logger = self.get_logger()
            interactive = _is_interactive()
            try:
                _run_renew(logger, dominio, interactive, force=False)
            except click.ClickException:
                raise
            else:
                if interactive:
                    widgets.pause()

        @group.command(name="reissue", help="força a reemissão do certificado agora, mesmo longe de expirar.")
        @click.argument("dominio", required=False, default=None)
        def reissue_cmd(dominio):
            _require_root()
            logger = self.get_logger()
            interactive = _is_interactive()
            try:
                _run_renew(logger, dominio, interactive, force=True)
            except click.ClickException:
                raise
            else:
                if interactive:
                    widgets.pause()

        @group.command(name="remove", help="remove o certificado e o VirtualHost de um domínio.")
        @click.argument("dominio", required=False, default=None)
        @click.option("--yes", is_flag=True, help="pula a confirmação de remover certificado + VirtualHost.")
        def remove_cmd(dominio, yes):
            _require_root()
            logger = self.get_logger()
            interactive = _is_interactive()
            try:
                _run_remove(logger, dominio, interactive, yes)
            except click.ClickException:
                raise
            else:
                if interactive:
                    widgets.pause()

        return group


cli = SslModule()
