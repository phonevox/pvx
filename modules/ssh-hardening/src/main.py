import os
import sys

import click

from pvx import config
from pvx.interactive import widgets
from pvx.interactive.inputs import ask_confirm, ask_select, ask_text
from pvx.modules.base import PvxModule

import apply as apply_module
import user_setup
from plan import DEFAULT_PORT, DEFAULT_PUBLIC_KEY, DEFAULT_ROOT_PASSWORD, DEFAULT_USERNAME, build_plan

CONFIG_PATH = "/etc/ssh/sshd_config"
SUDOERS_DIR = "/etc/sudoers.d"

MODE_DEFAULTS = "Usar os padrões da Phonevox (recomendado)"
MODE_CUSTOMIZE = "Customizar cada opção"


def _is_interactive():
    # seam próprio em vez de checar sys.stdin.isatty() direto -- o
    # CliRunner (testes) substitui sys.stdin inteiro durante o invoke(),
    # então um mock em cima do stdin de antes da chamada não pega.
    return sys.stdin.isatty()


class SSHHardeningModule(PvxModule):
    name = "ssh-hardening"
    version = "0.2.1"

    def cli_group(self):
        @click.group(name="ssh-hardening")
        def group():
            pass

        @group.command(name="setup")
        @click.option("--quick", is_flag=True, help="usa os padrões da Phonevox, não pergunta nada")
        @click.option("--yes", is_flag=True, help="pula a confirmação final")
        @click.option("--lock-root/--no-lock-root", default=None)
        @click.option("--root-password", default=None)
        @click.option("--create-user/--no-create-user", default=None)
        @click.option("--username", default=None)
        @click.option("--public-key", default=None)
        @click.option("--allow-password/--no-allow-password", default=None)
        @click.option("--user-password", default=None)
        @click.option("--change-port/--no-change-port", default=None)
        @click.option("--port", default=None)
        def setup_cmd(
            quick, yes, lock_root, root_password, create_user, username, public_key,
            allow_password, user_password, change_port, port,
        ):
            if os.geteuid() != 0:
                raise click.ClickException("ssh-hardening precisa rodar como root (sudo).")

            logger = self.get_logger()
            is_tty = _is_interactive()
            any_flag_given = quick or any(
                v is not None
                for v in (
                    lock_root, root_password, create_user, username, public_key,
                    allow_password, user_password, change_port, port,
                )
            )

            if not is_tty and not any_flag_given:
                click.echo("Nada informado e sem terminal -- nenhuma ação foi tomada.")
                return

            if quick:
                lock_root = True if lock_root is None else lock_root
                create_user = True if create_user is None else create_user
                change_port = True if change_port is None else change_port
            elif is_tty and not any_flag_given:
                mode = ask_select(
                    "Como quer configurar o SSH hardening?", [MODE_DEFAULTS, MODE_CUSTOMIZE]
                )
                if mode == MODE_DEFAULTS:
                    lock_root = True if lock_root is None else lock_root
                    create_user = True if create_user is None else create_user
                    change_port = True if change_port is None else change_port
                else:
                    if lock_root is None:
                        lock_root = ask_confirm("Bloquear login do root via SSH?", default=True)
                    if lock_root and root_password is None:
                        root_password = ask_text(
                            "Senha do root (usada só via KVM/console)", default=DEFAULT_ROOT_PASSWORD
                        )

                    if create_user is None:
                        create_user = ask_confirm(
                            "Criar um usuário administrativo dedicado?", default=True
                        )
                    if create_user:
                        if username is None:
                            username = ask_text("Nome do usuário dedicado", default=DEFAULT_USERNAME)
                        if public_key is None:
                            public_key = ask_text(
                                "Chave pública autorizada", default=DEFAULT_PUBLIC_KEY
                            )
                        if allow_password is None:
                            allow_password = ask_confirm(
                                "Permitir login por senha pra esse usuário (além da chave)?",
                                default=False,
                            )

                    if change_port is None:
                        change_port = ask_confirm("Trocar a porta padrão do SSH?", default=True)
                    if change_port and port is None:
                        port = ask_text("Nova porta SSH", default=DEFAULT_PORT)

            lock_root = False if lock_root is None else lock_root
            create_user = False if create_user is None else create_user
            change_port = False if change_port is None else change_port
            allow_password = False if allow_password is None else allow_password

            try:
                plan = build_plan(
                    lock_root, root_password,
                    create_user, username, public_key, allow_password, user_password,
                    change_port, port,
                )
            except ValueError as e:
                logger.error(f"plano inválido: {e}")
                raise click.ClickException(str(e))

            if plan is None:
                click.echo("Nada a fazer.")
                if is_tty:
                    widgets.pause()
                return

            if not yes:
                if not is_tty:
                    click.echo("Sem terminal pra confirmar -- use --yes. Nenhuma ação foi tomada.")
                    return

                click.echo("Resumo do que vai mudar:")
                if plan["lock_root"]:
                    click.echo("- root: login via SSH bloqueado (fica só console/KVM)")
                if plan["create_user"]:
                    click.echo(f"- usuário dedicado: {plan['username']}")
                if plan["change_port"]:
                    click.echo(f"- porta SSH: {plan['port']}")

                confirmed = ask_confirm(
                    "Confirma a aplicação dessas mudanças? Nada entra em vigor até reiniciar "
                    "o sshd ou reiniciar a máquina.",
                    default=False,
                )
                if not confirmed:
                    widgets.message("nada foi alterado.")
                    widgets.pause()
                    return

            state_dir = str(config.modules_dir() / "ssh-hardening" / "state")
            result = apply_module.apply(plan, CONFIG_PATH, SUDOERS_DIR, state_dir)

            if not result["applied"]:
                outcome = "nada a fazer."
            elif not result["config_valid"]:
                outcome = (
                    "config resultante era inválida -- revertido pro backup automaticamente, "
                    "nada foi aplicado de verdade."
                )
            else:
                outcome = "ssh-hardening aplicado. reinicie o sshd (ou a máquina) pra entrar em vigor."
                if result["admin_group_added"] is False:
                    outcome += (
                        " aviso: nenhum grupo administrativo padrão (wheel/sudo) encontrado nessa "
                        "distro -- usuário criado sem grupo extra, mas o acesso via sudoers.d já "
                        "está garantido."
                    )
            logger.info(outcome)

            if is_tty:
                widgets.message(outcome)
                widgets.pause()
            else:
                click.echo(outcome)

        @group.command(name="check")
        def check_cmd():
            is_tty = _is_interactive()
            state_dir = str(config.modules_dir() / "ssh-hardening" / "state")
            record = apply_module.find_latest_record(state_dir)

            if record is None:
                widgets.state("ssh-hardening NÃO configurado -- rode `pvx ssh-hardening setup` primeiro.", ok=False)
                if is_tty:
                    widgets.pause()
                return

            plan = record["plan"]
            widgets.state("ssh-hardening configurado:", ok=True)
            if plan.get("lock_root"):
                click.echo("  root: login via SSH bloqueado")
            if plan.get("create_user"):
                username = plan["username"]
                exists = user_setup.user_exists(username)
                click.echo(f"  usuário dedicado: {username} ({'existe' if exists else 'NÃO existe mais'})")
            if plan.get("change_port"):
                click.echo(f"  porta SSH: {plan['port']}")
            click.echo(f"  última aplicação válida: {'sim' if record.get('config_valid') else 'não'}")

            if is_tty:
                widgets.pause()

        @group.command(name="revert")
        @click.option("--yes", is_flag=True)
        def revert_cmd(yes):
            if os.geteuid() != 0:
                raise click.ClickException("ssh-hardening precisa rodar como root (sudo).")

            logger = self.get_logger()
            is_tty = _is_interactive()
            state_dir = str(config.modules_dir() / "ssh-hardening" / "state")
            record = apply_module.find_latest_record(state_dir)

            if record is None:
                click.echo("nada aplicado pelo pvx -- nada a reverter.")
                if is_tty:
                    widgets.pause()
                return

            plan = record["plan"]
            click.echo("Isso vai desfazer só o que o pvx ssh-hardening aplicou:")
            if record.get("backup_path"):
                click.echo("  - restaura o sshd_config de antes da aplicação")
            if plan.get("create_user"):
                click.echo(f"  - remove o usuário '{plan['username']}' e sua regra de sudoers")
            if plan.get("lock_root"):
                click.echo("  aviso: a senha do root NÃO será revertida (não temos o hash anterior).")

            if not yes and not ask_confirm("Confirma a reversão?", default=False):
                widgets.message("nada foi alterado.")
                if is_tty:
                    widgets.pause()
                return

            result = apply_module.revert(record, CONFIG_PATH, SUDOERS_DIR)
            if result["reverted"]:
                for item in result["reverted"]:
                    widgets.success(item)
                logger.info(f"ssh-hardening revertido: {'; '.join(result['reverted'])}")
                click.echo("reinicie o sshd (ou a máquina) pra as mudanças revertidas entrarem em vigor.")
            else:
                click.echo("nada encontrado pra reverter (backup ausente e nenhum usuário criado).")

            if is_tty:
                widgets.pause()

        return group


cli = SSHHardeningModule()
