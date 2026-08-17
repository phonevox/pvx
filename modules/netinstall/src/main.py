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


_SSH_FLAG_KEYS = (
    "tweak_ssh_lock_root", "tweak_ssh_root_password", "tweak_ssh_create_user",
    "tweak_ssh_username", "tweak_ssh_pubkey", "tweak_ssh_allow_password",
    "tweak_ssh_user_password", "tweak_ssh_change_port", "tweak_ssh_port",
)


def _resolve_ssh_hardening_config(flags, interactive):
    # atalho: com TTY e nenhuma flag --tweak-ssh-* dada, pergunta UMA vez se quer os
    # padrões da Phonevox de cara (sem repetir as perguntas seguintes) ou revisar item
    # por item -- uma flag explícita em qualquer campo pula direto pro fluxo de sempre.
    if interactive and not any(flags[k] is not None for k in _SSH_FLAG_KEYS):
        choice = ask_select(
            "ssh-hardening: como configurar?",
            ["Usar padrões da Phonevox (recomendado)", "Personalizar cada opção"],
        )
        if choice is None:
            return None
        if choice.startswith("Usar padrões"):
            return {**defaults.SSH_HARDENING_DEFAULTS, "allow_password": False, "user_password": ""}

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
    version = "0.1.1"

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

            def _resolve_password(flag_value, prompt):
                if flag_value:
                    return flag_value
                if not interactive:
                    return os_ops.gen_password()
                entered = ask_text(f"{prompt} (enter vazio = gera aleatória):")
                if entered is None:
                    return None  # esc -- aborta
                return entered or os_ops.gen_password()

            sql_pw = _resolve_password(flags["sql_password"], "Senha do MySQL root")
            if sql_pw is None:
                return
            web_pw = _resolve_password(flags["web_password"], "Senha admin da interface Web")
            if web_pw is None:
                return

            ssh_config = None
            if "ssh-hardening" in tweak_keys:
                ssh_config = _resolve_ssh_hardening_config(flags, interactive)
                if ssh_config is None:
                    return

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
            major = preflight.version_major()

            with widgets.spinner("Adicionando repositórios (epel, tmux/htop, Issabel 5)..."):
                install_steps.add_repos(pyz_path)
            with widgets.spinner("Preparando o sistema (SELinux, usuário asterisk)..."):
                install_steps.prepare_system()
            with widgets.spinner(f"Habilitando repo Remi + módulo PHP (RHEL/Rocky {major})..."):
                install_steps.enable_php_remi(major)
            with widgets.spinner("Instalando pacotes (base + Asterisk + Issabel -- vários minutos)..."):
                install_steps.install_packages(astver, extra_packages)
            with widgets.spinner("Pós-instalação (mariadb, httpd, firewalld, asterisk)..."):
                install_steps.post_install()

            if ssh_config is not None:
                with widgets.spinner("Aplicando ssh-hardening..."):
                    result = integrations.run_ssh_hardening(ssh_config)
                _report_tweak("ssh-hardening", result)
            if "firewall" in tweak_keys:
                with widgets.spinner("Sincronizando firewall..."):
                    result = integrations.run_firewall_sync()
                _report_tweak("firewall", result)
            if qint_config is not None:
                with widgets.spinner("Aplicando integração qint..."):
                    result = integrations.run_qint(qint_config)
                _report_tweak("qint", result)

            with widgets.spinner("Instalando o schema do banco de dados..."):
                install_steps.install_db()
            if "operator-panel" in tweak_keys:
                with widgets.spinner("Instalando o painel do operador..."):
                    install_steps.install_control_panel(pyz_path)
            tz = flags["timezone"] or defaults.DEFAULT_TIMEZONE
            with widgets.spinner(f"Ajustando timezone ({tz})..."):
                install_steps.set_timezone(tz)

            extra_kv = {}
            if ssh_config is not None and ssh_config["change_port"]:
                extra_kv["ssh_port"] = ssh_config["port"]
            with widgets.spinner("Definindo senhas de acesso (MySQL root / admin Web)..."):
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
