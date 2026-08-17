import sys

import click

from pvx import config as pvx_config
from pvx.interactive import widgets
from pvx.interactive.inputs import ask_checkbox, ask_confirm, ask_select, ask_text
from pvx.modules.base import PvxModule

import credentials
import defaults
import install_steps
import integrations
import os_ops
import preflight

QINT_FIELDS = (
    "tipo", "sftp", "url", "token", "timecondition_out", "filas", "asterisk_ip",
    "versao", "filial", "departamentos", "assuntos", "app", "setores",
    "ocorrencias", "motivo_os",
)


def _is_interactive():
    return sys.stdin.isatty()


def _pyz_path():
    # assets estáticos (repos, control_panel) vêm de DENTRO do .pyz (ver assets.py) -- no
    # host instalado só module.pyz+manifest.json existem no diretório do módulo.
    return str(pvx_config.modules_dir() / "netinstall" / "module.pyz")


def _state_dir():
    return pvx_config.modules_dir() / "netinstall" / "state"


def _default_tweaks():
    return [key for key, (on, _) in defaults.TWEAKS_CATALOG.items() if on]


def _resolve_ssh_hardening_config(flags, interactive):
    if flags["tweak_ssh_lock_root"] is None and interactive:
        lock_root = ask_confirm("ssh-hardening: bloquear login SSH do root?", default=True)
    else:
        lock_root = flags["tweak_ssh_lock_root"] if flags["tweak_ssh_lock_root"] is not None else True

    root_password = flags["tweak_ssh_root_password"] or defaults.SSH_HARDENING_DEFAULTS["root_password"]

    if flags["tweak_ssh_create_user"] is None and interactive:
        create_user = ask_confirm("ssh-hardening: criar usuário dedicado com sudo?", default=True)
    else:
        create_user = flags["tweak_ssh_create_user"] if flags["tweak_ssh_create_user"] is not None else True

    username = flags["tweak_ssh_username"] or defaults.SSH_HARDENING_DEFAULTS["username"]
    pubkey = flags["tweak_ssh_pubkey"] or defaults.SSH_HARDENING_DEFAULTS["pubkey"]
    allow_password = flags["tweak_ssh_allow_password"] or False
    user_password = flags["tweak_ssh_user_password"] or ""

    if flags["tweak_ssh_change_port"] is None and interactive:
        change_port = ask_confirm("ssh-hardening: trocar a porta padrão do SSH?", default=True)
    else:
        change_port = flags["tweak_ssh_change_port"] if flags["tweak_ssh_change_port"] is not None else True

    port = flags["tweak_ssh_port"] or defaults.SSH_HARDENING_DEFAULTS["port"]

    return {
        "lock_root": lock_root, "root_password": root_password,
        "create_user": create_user, "username": username, "pubkey": pubkey,
        "allow_password": allow_password, "user_password": user_password,
        "change_port": change_port, "port": port,
    }


def _resolve_qint_config(flags, interactive):
    config = {k: flags[f"qint_{k}"] for k in QINT_FIELDS}
    if config["tipo"] is None:
        if not interactive:
            return None
        label = ask_select("qint: tipo de integração:", ["IXCSoft", "SGP"])
        if label is None:
            return None
        config["tipo"] = "ixcsoft" if label == "IXCSoft" else "sgp"
    return config


def _report_tweak(name, result):
    if result["ok"]:
        widgets.success(f"{name} aplicado.")
    else:
        widgets.failed(f"{name}: {result.get('stderr') or 'falha desconhecida'}")


class NetinstallModule(PvxModule):
    name = "netinstall"
    version = "0.1.0"

    def cli_group(self):
        @click.group(name="netinstall")
        def group():
            pass

        @group.command(name="issabel5")
        @click.option("--astver", type=click.Choice(defaults.ASTERISK_VERSIONS), default=None)
        @click.option("--addpkgs", multiple=True, type=click.Choice(list(defaults.ADDPKGS)))
        @click.option("--tweaks", multiple=True, type=click.Choice(list(defaults.TWEAKS_CATALOG)))
        @click.option("--timezone", default=None)
        @click.option("--sql-password", default=None)
        @click.option("--web-password", default=None)
        @click.option("--force", is_flag=True)
        @click.option("--yes", is_flag=True)
        @click.option("--reboot/--no-reboot", default=True)
        @click.option("--tweak-ssh-lock-root/--tweak-ssh-no-lock-root", default=None)
        @click.option("--tweak-ssh-root-password", default=None)
        @click.option("--tweak-ssh-create-user/--tweak-ssh-no-create-user", default=None)
        @click.option("--tweak-ssh-username", default=None)
        @click.option("--tweak-ssh-pubkey", default=None)
        @click.option("--tweak-ssh-allow-password/--tweak-ssh-no-allow-password", default=None)
        @click.option("--tweak-ssh-user-password", default=None)
        @click.option("--tweak-ssh-change-port/--tweak-ssh-no-change-port", default=None)
        @click.option("--tweak-ssh-port", default=None)
        @click.option("--qint-tipo", default=None)
        @click.option("--qint-sftp", default=None)
        @click.option("--qint-url", default=None)
        @click.option("--qint-token", default=None)
        @click.option("--qint-timecondition-out", default=None)
        @click.option("--qint-filas", default=None)
        @click.option("--qint-asterisk-ip", default=None)
        @click.option("--qint-versao", default=None)
        @click.option("--qint-filial", default=None)
        @click.option("--qint-departamentos", default=None)
        @click.option("--qint-assuntos", default=None)
        @click.option("--qint-app", default=None)
        @click.option("--qint-setores", default=None)
        @click.option("--qint-ocorrencias", default=None)
        @click.option("--qint-motivo-os", default=None)
        def issabel5_cmd(**flags):
            interactive = _is_interactive()

            errors, warnings = preflight.check(min_version=8, force=flags["force"])
            for warning in warnings:
                click.echo(f"aviso: {warning}")
            if errors:
                raise click.ClickException("\n".join(errors))

            astver = flags["astver"]
            if astver is None:
                if not interactive:
                    raise click.ClickException("informe --astver (16 ou 18).")
                choice = ask_select("Versão do Asterisk:", list(defaults.ASTERISK_VERSIONS))
                if choice is None:
                    return
                astver = choice

            addpkgs_keys = list(flags["addpkgs"])
            if not addpkgs_keys and interactive:
                selected = ask_checkbox(
                    "Pacotes adicionais:", list(defaults.ADDPKGS),
                    defaults=[k for k, v in defaults.ADDPKGS_DEFAULTS.items() if v],
                )
                if selected is None:
                    return
                addpkgs_keys = selected
            extra_packages = [pkg for key in addpkgs_keys for pkg in defaults.ADDPKGS[key]]

            tweak_keys = list(flags["tweaks"])
            if not tweak_keys:
                if interactive:
                    selected = ask_checkbox(
                        "Tweaks Phonevox:", list(defaults.TWEAKS_CATALOG), defaults=_default_tweaks(),
                    )
                    if selected is None:
                        return
                    tweak_keys = selected
                else:
                    tweak_keys = _default_tweaks()

            sql_pw = flags["sql_password"] or (ask_text("Senha do MySQL root:") if interactive else None)
            web_pw = flags["web_password"] or (ask_text("Senha admin da interface Web:") if interactive else None)
            if not sql_pw or not web_pw:
                raise click.ClickException("informe --sql-password e --web-password (sem terminal).")

            ssh_config = None
            if "ssh-hardening" in tweak_keys:
                ssh_config = _resolve_ssh_hardening_config(flags, interactive)

            qint_config = None
            if "qint" in tweak_keys:
                qint_config = _resolve_qint_config(flags, interactive)
                if qint_config is None:
                    raise click.ClickException(
                        "tweak qint selecionada mas --qint-tipo não informado (ou sem terminal pra perguntar)."
                    )

            click.echo("Resumo:")
            click.echo(f"  Asterisk: {astver}")
            click.echo(f"  Pacotes extras: {', '.join(addpkgs_keys) or 'nenhum'}")
            click.echo(f"  Tweaks: {', '.join(tweak_keys) or 'nenhum'}")
            if not flags["yes"] and not ask_confirm("Prosseguir com a instalação?", default=False):
                click.echo("Operação cancelada.")
                return

            pyz_path = _pyz_path()
            install_steps.add_repos(pyz_path)
            install_steps.prepare_system()
            install_steps.enable_php_remi(preflight.version_major())
            install_steps.install_packages(astver, extra_packages)
            install_steps.post_install()

            if ssh_config is not None:
                _report_tweak("ssh-hardening", integrations.run_ssh_hardening(ssh_config))
            if "firewall" in tweak_keys:
                _report_tweak("firewall", integrations.run_firewall_sync())
            if qint_config is not None:
                _report_tweak("qint", integrations.run_qint(qint_config))

            install_steps.install_db()
            if "operator-panel" in tweak_keys:
                install_steps.install_control_panel(pyz_path)
            install_steps.set_timezone(flags["timezone"] or defaults.DEFAULT_TIMEZONE)

            extra_kv = {}
            if ssh_config is not None and ssh_config["change_port"]:
                extra_kv["ssh_port"] = ssh_config["port"]
            install_steps.set_passwords(sql_pw, web_pw)
            cred_path = credentials.save_credentials(str(_state_dir()), "issabel5", sql_pw, web_pw, extra=extra_kv)
            widgets.success(f"credenciais salvas em {cred_path} (0600)")

            if flags["reboot"]:
                click.echo("reiniciando o servidor...")
                os_ops.run_cmd(["reboot"])
            else:
                click.echo("--no-reboot -- reinicie manualmente quando quiser.")

        return group


cli = NetinstallModule()
