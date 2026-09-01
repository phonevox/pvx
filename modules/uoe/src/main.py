import sys

import click

from pvx import config as pvx_config
from pvx.interactive import widgets
from pvx.interactive.inputs import ask_checkbox, ask_confirm, ask_password, ask_select, ask_text
from pvx.modules.base import PvxModule

import backup_scripts
import crontab
import pbackup_ops
import state
import uoe_client

_STANDARD_ROOT_PATH_LABEL = "Convenção padrão (clientes/idcliente-idcontrato-empresa)"
_MANUAL_ROOT_PATH_LABEL = "Definir manualmente..."
_SCRIPT_LABELS = {
    "Issabel (config + gravações)": "issabel",
    "MagnusBilling": "magnus",
    "Comando customizado": "custom",
}


def _is_interactive():
    return sys.stdin.isatty()


def _read_password_file(path):
    # nunca senha em argumento de linha de comando (fica em ~/.bash_history, ps
    # aux, etc.) -- mesma convenção de scripts/publish.sh.
    if path is None:
        return None
    return open(path).read().strip()


def _state_path():
    path = pvx_config.modules_dir() / "uoe" / "state"
    path.mkdir(parents=True, exist_ok=True)
    return path / "state.json"


def _redact(command):
    # nunca mostra o token inteiro na tela -- só sinaliza que ele existe ali.
    if "--token " not in command:
        return command
    head, _, rest = command.partition("--token ")
    token, _, tail = rest.partition(" ")
    shown = token[:8] + "..." if len(token) > 8 else "..."
    return f"{head}--token {shown}{(' ' + tail) if tail else ''}"


def _pbackup_version_str(version):
    return ".".join(str(p) for p in version) if version else "?"


def _ensure_pbackup(logger):
    pbackup_root = pbackup_ops.find_install()
    version = pbackup_ops.installed_version(pbackup_root) if pbackup_root else None

    if pbackup_root is None:
        with widgets.spinner("pbackup não encontrado -- instalando..."):
            pbackup_root = pbackup_ops.fresh_install()
        logger.info(f"pbackup instalado em {pbackup_root}.")
        widgets.success(f"pbackup instalado em {pbackup_root}.")
    elif not pbackup_ops.is_supported(version):
        with widgets.spinner(f"pbackup {_pbackup_version_str(version)} desatualizado -- atualizando..."):
            pbackup_ops.update_in_place(pbackup_root)
        logger.info(f"pbackup atualizado em {pbackup_root}.")
        widgets.success("pbackup atualizado.")
    else:
        widgets.state(f"pbackup {_pbackup_version_str(version)} ok ({pbackup_root}).", ok=True)

    return pbackup_root


def _review_legacy_cron(interactive):
    lines = crontab.read_crontab()
    candidates = crontab.find_legacy_candidates(lines)
    if not candidates or not interactive:
        return

    selected = ask_checkbox(
        "Rotinas de backup antigas encontradas na cron -- selecione as que quer remover "
        "(nenhuma pré-marcada, nada é apagado sem escolha explícita):",
        candidates,
    )
    if not selected:
        return

    lines = [line for line in lines if line.strip() not in selected]
    crontab.write_crontab(lines)
    widgets.success(f"{len(selected)} rotina(s) antiga(s) removida(s).")


def _resolve_root_path(root_path, id_cliente, id_contrato, empresa, interactive):
    if root_path:
        return root_path
    if id_cliente and id_contrato and empresa:
        return f"clientes/{id_cliente}-{id_contrato}-{empresa}"
    if not interactive:
        raise click.ClickException(
            "informe --root-path, ou --id-cliente/--id-contrato/--empresa juntos."
        )

    choice = ask_select("root_path:", [_STANDARD_ROOT_PATH_LABEL, _MANUAL_ROOT_PATH_LABEL])
    if choice is None:
        return None
    if choice == _MANUAL_ROOT_PATH_LABEL:
        return ask_text("root_path completo:")

    id_cliente = id_cliente or ask_text("ID do cliente:")
    if id_cliente is None:
        return None
    id_contrato = id_contrato or ask_text("ID do contrato:")
    if id_contrato is None:
        return None
    empresa = empresa or ask_text("Nome da empresa (slug, sem espaço):")
    if empresa is None:
        return None
    return f"clientes/{id_cliente}-{id_contrato}-{empresa}"


def _resolve_script(script, custom_command, interactive):
    if script is None:
        if not interactive:
            raise click.ClickException(
                "informe --script issabel|magnus|custom (com --custom-command se for custom)."
            )
        label = ask_select("Script pra rodar na cron:", list(_SCRIPT_LABELS))
        if label is None:
            return None, None
        script = _SCRIPT_LABELS[label]

    if script not in backup_scripts.SCRIPTS:
        raise click.ClickException(f"script inválido: {script} (opções: {', '.join(backup_scripts.SCRIPTS)}).")

    if script == "custom" and custom_command is None:
        if not interactive:
            raise click.ClickException("--script custom exige --custom-command (com {TOKEN} literal).")
        custom_command = ask_text("Comando completo (use {TOKEN} onde o token deve entrar):")
        if custom_command is None:
            return None, None

    return script, custom_command


def _resolve_schedule(minute, hour, interactive):
    if minute is None:
        if not interactive:
            raise click.ClickException("informe --cron-minute e --cron-hour.")
        minute = ask_text("Minuto de execução (0-59):", default="0")
        if minute is None:
            return None, None
    if hour is None:
        if not interactive:
            raise click.ClickException("informe --cron-minute e --cron-hour.")
        hour = ask_text("Hora de execução (0-23):", default="2")
        if hour is None:
            return None, None
    return minute, hour


def _run_setup(logger, opts, interactive):
    pbackup_root = _ensure_pbackup(logger)
    _review_legacy_cron(interactive)

    root_path = _resolve_root_path(
        opts["root_path"], opts["id_cliente"], opts["id_contrato"], opts["empresa"], interactive,
    )
    if root_path is None:
        return

    username = opts["username"]
    if username is None:
        if not interactive:
            raise click.ClickException("informe --username.")
        username = ask_text("Defina o usuário do cliente no UOE:")
        if username is None:
            return

    # nunca deriva/hardcoda uma fórmula de senha -- repo é público, uma fórmula
    # fixa no fonte revelaria como adivinhar a senha de qualquer cliente sabendo
    # só o username (ver ADR 0001). o técnico sempre digita a senha de verdade.
    password = _read_password_file(opts["password_file"])
    if password is None:
        if not interactive:
            raise click.ClickException("informe --password-file (senha do cliente a ser criado).")
        password = ask_password(f"Defina a senha do usuário '{username}' no UOE:")
        if password is None:
            return

    admin_password = _read_password_file(opts["admin_password_file"])
    if admin_password is None:
        if not interactive:
            raise click.ClickException("informe --admin-password-file.")
        admin_password = ask_password(
            "⚠️  Senha do usuário ROOT (superadmin) do UOE -- NÃO é a senha do cliente:"
        )
        if admin_password is None:
            return

    with widgets.spinner("Autenticando como superadmin..."):
        try:
            admin_token = uoe_client.login("root", admin_password)
        except uoe_client.UOEError as e:
            raise click.ClickException(f"falha no login do superadmin: {e}")

    if not opts["skip_register"]:
        try:
            with widgets.spinner(f"Registrando '{username}' no UOE..."):
                uoe_client.register(admin_token, username, password, root_path)
            widgets.success(f"usuário '{username}' registrado (root_path={root_path}).")
        except uoe_client.UOEError as e:
            logger.error(f"register de '{username}' falhou: {e}")
            skip = interactive and ask_confirm(
                f"Falha ao registrar (HTTP {e.status}): {e.body}\n"
                "Isso pode ser porque o usuário já existe. Pular pro login e continuar?",
                default=False,
            )
            if not skip:
                raise click.ClickException(f"falha ao registrar '{username}' no UOE: {e}")

    with widgets.spinner(f"Autenticando '{username}'..."):
        try:
            token = uoe_client.login(username, password)
        except uoe_client.UOEError as e:
            raise click.ClickException(f"falha no login de '{username}': {e}")
    widgets.success("token obtido.")

    script, custom_command = _resolve_script(opts["script"], opts["custom_command"], interactive)
    if script is None:
        return

    minute, hour = _resolve_schedule(opts["cron_minute"], opts["cron_hour"], interactive)
    if minute is None:
        return

    command = backup_scripts.build_command(
        script, token, pbackup_root=pbackup_root, custom_template=custom_command,
    )
    cron_line = f"{minute} {hour} * * * {command}"
    crontab.write_crontab(crontab.upsert_managed_entry(crontab.read_crontab(), cron_line))
    widgets.success("cron atualizada.")

    state.save(_state_path(), {
        "username": username, "token": token, "root_path": root_path,
        "script": script, "custom_command": custom_command,
        "pbackup_root": pbackup_root, "cron_minute": minute, "cron_hour": hour,
    })
    logger.info(f"uoe setup concluído -- username={username} script={script}")


def _run_relogin(logger, password_file, interactive):
    saved = state.load(_state_path())
    if saved is None:
        raise click.ClickException("nada configurado ainda -- rode `pvx uoe setup` primeiro.")

    password = _read_password_file(password_file)
    if password is None:
        if not interactive:
            raise click.ClickException("informe --password-file.")
        password = ask_password(f"Senha atual de '{saved['username']}':")
        if password is None:
            return

    with widgets.spinner(f"Autenticando '{saved['username']}'..."):
        try:
            token = uoe_client.login(saved["username"], password)
        except uoe_client.UOEError as e:
            raise click.ClickException(f"falha no login de '{saved['username']}': {e}")

    command = backup_scripts.build_command(
        saved["script"], token,
        pbackup_root=saved.get("pbackup_root"), custom_template=saved.get("custom_command"),
    )
    cron_line = f"{saved['cron_minute']} {saved['cron_hour']} * * * {command}"
    crontab.write_crontab(crontab.upsert_managed_entry(crontab.read_crontab(), cron_line))

    saved["token"] = token
    state.save(_state_path(), saved)
    logger.info(f"uoe relogin concluído -- username={saved['username']}.")
    widgets.success("token renovado e cron atualizada.")


def _run_remove(logger, yes, delete_remote_user, admin_password_file, interactive):
    lines = crontab.read_crontab()
    managed = crontab.find_managed_entry(lines)
    saved = state.load(_state_path())

    if managed is None and saved is None:
        click.echo("nada gerenciado pelo pvx uoe encontrado nessa central.")
        return

    if managed is not None:
        click.echo(f"entrada de cron gerenciada encontrada: {_redact(managed[1])}")
    if not yes and not ask_confirm("Remover a entrada de cron e o estado local?", default=False):
        click.echo("nada foi alterado.")
        return

    if managed is not None:
        new_lines, _ = crontab.remove_managed_entry(lines)
        crontab.write_crontab(new_lines)

    # ação separada e mais destrutiva -- --yes (da remoção da cron) nunca implica
    # isso sozinho, precisa do próprio flag ou confirmação explícita dessa pergunta.
    if saved and (delete_remote_user or (interactive and ask_confirm(
        "Também apagar o usuário no UOE (ação remota, mais destrutiva)?", default=False,
    ))):
        admin_password = _read_password_file(admin_password_file)
        if admin_password is None:
            admin_password = ask_password(
                "⚠️  Senha do usuário ROOT (superadmin) do UOE -- NÃO é a senha do cliente:"
            ) if interactive else None
        if admin_password is None:
            raise click.ClickException("informe --admin-password-file pra apagar o usuário remoto.")
        with widgets.spinner("Autenticando como superadmin..."):
            try:
                admin_token = uoe_client.login("root", admin_password)
            except uoe_client.UOEError as e:
                raise click.ClickException(f"falha no login do superadmin: {e}")
        with widgets.spinner(f"Apagando '{saved['username']}' no UOE..."):
            try:
                uoe_client.delete_user(admin_token, saved["username"])
            except uoe_client.UOEError as e:
                raise click.ClickException(f"falha ao apagar '{saved['username']}': {e}")
        widgets.success(f"usuário '{saved['username']}' apagado no UOE.")

    state.remove(_state_path())
    logger.info("uoe remove concluído.")
    widgets.success("removido.")


class UOEModule(PvxModule):
    name = "uoe"
    version = "0.1.0"

    def cli_group(self):
        @click.group(name="uoe")
        def group():
            pass

        @group.command(name="setup")
        @click.option("--root-path", default=None)
        @click.option("--id-cliente", default=None)
        @click.option("--id-contrato", default=None)
        @click.option("--empresa", default=None)
        @click.option("--username", default=None)
        @click.option("--password-file", default=None, help="arquivo com a senha a definir pro cliente (sem terminal pra digitar).")
        @click.option("--admin-password-file", default=None, help="arquivo com a senha do root/superadmin do UOE.")
        @click.option("--skip-register", is_flag=True, help="pula o registro, só loga (cliente já existe).")
        @click.option("--script", type=click.Choice(backup_scripts.SCRIPTS), default=None)
        @click.option("--custom-command", default=None, help="comando completo com {TOKEN} literal.")
        @click.option("--cron-minute", default=None)
        @click.option("--cron-hour", default=None)
        def setup_cmd(**opts):
            logger = self.get_logger()
            interactive = _is_interactive()
            try:
                _run_setup(logger, opts, interactive)
            except click.ClickException:
                raise
            else:
                if interactive:
                    widgets.pause()

        @group.command(name="relogin")
        @click.option("--password-file", default=None, help="arquivo com a senha atual do client user.")
        def relogin_cmd(password_file):
            logger = self.get_logger()
            interactive = _is_interactive()
            try:
                _run_relogin(logger, password_file, interactive)
            except click.ClickException:
                raise
            else:
                if interactive:
                    widgets.pause()

        @group.command(name="remove")
        @click.option("--yes", is_flag=True, help="pula a confirmação de remover a cron/estado local.")
        @click.option(
            "--delete-remote-user", is_flag=True,
            help="também apaga o usuário no UOE (ação separada e mais destrutiva -- --yes sozinho não cobre isso).",
        )
        @click.option("--admin-password-file", default=None, help="arquivo com a senha do root/superadmin do UOE.")
        def remove_cmd(yes, delete_remote_user, admin_password_file):
            logger = self.get_logger()
            interactive = _is_interactive()
            try:
                _run_remove(logger, yes, delete_remote_user, admin_password_file, interactive)
            except click.ClickException:
                raise
            else:
                if interactive:
                    widgets.pause()

        @group.command(name="check")
        def check_cmd():
            saved = state.load(_state_path())
            if saved is None:
                widgets.state("uoe NÃO configurado -- rode `pvx uoe setup` primeiro.", ok=False)
                if _is_interactive():
                    widgets.pause()
                return

            widgets.state(f"uoe configurado (username={saved['username']})", ok=True)
            click.echo(f"  root_path: {saved.get('root_path', '-')}")
            click.echo(f"  script: {saved.get('script', '-')}")
            click.echo(f"  cron: {saved.get('cron_minute', '?')} {saved.get('cron_hour', '?')} * * *")

            lines = crontab.read_crontab()
            managed = crontab.find_managed_entry(lines)
            if managed is None:
                widgets.state("aviso: entrada de cron gerenciada NÃO encontrada -- rode `setup` de novo.", ok=False)
            else:
                click.echo(f"  cron atual: {_redact(managed[1])}")

            if _is_interactive():
                widgets.pause()

        return group


cli = UOEModule()
