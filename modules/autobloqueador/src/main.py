import os
import sys

import click

from pvx.interactive import widgets
from pvx.interactive.inputs import ask_confirm, ask_password, ask_select, ask_text
from pvx.modules.base import PvxModule

import autobloqueador_ops

_TYPE_LABELS = {"OPA (PM2)": "opa", "PABX (Asterisk)": "pabx"}

_NETWORK_WARNING = (
    "⚠️  IMPORTANTE: o comando curl abaixo DEVE ser executado APENAS numa máquina "
    "de rede permitida (VPN/interna) -- nunca em rede pública ou sem autorização."
)


def _is_interactive():
    return sys.stdin.isatty()


def _require_root():
    if os.geteuid() != 0:
        raise click.ClickException("autobloqueador precisa rodar como root (sudo).")


def _read_password_file(path):
    # nunca segredo em argumento de linha de comando (fica em
    # ~/.bash_history, ps aux, etc.) -- mesma convenção do resto do pvx.
    if path is None:
        return None
    return open(path).read().strip()


def _resolve_url_base(url_base):
    # sempre auto-preenchido pelo default da própria opção --url-base (é o
    # endpoint real, quase nunca muda) -- nunca pergunta.
    try:
        return autobloqueador_ops.normalize_url_base(url_base)
    except autobloqueador_ops.AutobloqueadorError as e:
        raise click.ClickException(str(e))


def _resolve_type(type_, interactive):
    # valores inválidos já são barrados pelo click.Choice na própria opção
    # -- aqui só resolve o caso "não informado".
    if type_ is not None:
        return type_
    if not interactive:
        raise click.ClickException("informe --type (opa|pabx).")
    label = ask_select("Type:", list(_TYPE_LABELS))
    if label is None:
        return None
    return _TYPE_LABELS[label]


def _resolve_code(code, interactive):
    if code is None:
        if not interactive:
            raise click.ClickException("informe --code.")
        code = ask_text("Code (máx 255 caracteres):")
        if code is None:
            return None
    if not autobloqueador_ops.validate_code(code):
        raise click.ClickException("code inválido (vazio ou maior que 255 caracteres).")
    return code


def _prompt_for_crypted_key(url_base, type_, code, interactive):
    linux, windows = autobloqueador_ops.register_curl_commands(url_base, type_, code)
    click.echo()
    click.echo(_NETWORK_WARNING)
    click.echo()
    click.echo("Linux/macOS:")
    click.echo(linux)
    click.echo()
    click.echo("Windows (CMD):")
    click.echo(windows)
    click.echo()

    if not interactive:
        raise click.ClickException(
            "rode o comando curl acima numa máquina de rede permitida, pegue o crypted_key, "
            "e informe --crypted-key-file (sem terminal pra colar aqui)."
        )
    return ask_password("Cole aqui o crypted_key recebido:")


def _run_initial_check(url_base, type_, crypted_key):
    try:
        with autobloqueador_ops.lock():
            result = autobloqueador_ops.check_and_apply(url_base, type_, crypted_key)
    except autobloqueador_ops.AutobloqueadorError as e:
        raise click.ClickException(str(e))
    _report_check_result(result, dry_run=False)


def _report_check_result(result, dry_run):
    http_code = result["http_code"]
    action = result["action"]
    suffix = " (dry-run)" if dry_run else ""

    if action is None:
        widgets.state(f"status {http_code} -- nenhuma ação necessária.", ok=True)
    elif action == "restart":
        widgets.success(f"status {http_code} -- restart executado{suffix}.")
    else:
        widgets.state(f"status {http_code} -- serviço bloqueado, stop executado{suffix}.", ok=False)

    if result["warning"]:
        widgets.state(result["warning"], ok=False)


def _run_install(logger, url_base, type_, code, crypted_key_file, pvx_bin, interactive):
    if autobloqueador_ops.configs_exist():
        widgets.state("configuração existente encontrada -- reutilizando (sem novo registro).", ok=True)
        config = autobloqueador_ops.load_config()
    else:
        url_base = _resolve_url_base(url_base)
        type_ = _resolve_type(type_, interactive)
        if type_ is None:
            return
        code = _resolve_code(code, interactive)
        if code is None:
            return

        crypted_key = _read_password_file(crypted_key_file)
        if crypted_key is None:
            crypted_key = _prompt_for_crypted_key(url_base, type_, code, interactive)
            if crypted_key is None:
                return

        autobloqueador_ops.save_config(url_base, type_, code, crypted_key)
        config = autobloqueador_ops.load_config()
        widgets.success("configuração salva.")

    try:
        with widgets.spinner("Instalando service + timer..."):
            autobloqueador_ops.install_timer(pvx_bin=pvx_bin)
    except autobloqueador_ops.AutobloqueadorError as e:
        raise click.ClickException(f"falha ao instalar o timer: {e}")
    widgets.success("service + timer instalados.")
    logger.info(f"autobloqueador instalado (type={config['type']}).")

    click.echo()
    click.echo("Executando verificação inicial de status...")
    _run_initial_check(config["url_base"], config["type"], config["crypted_key"])


def _run_reconfig(logger, type_, code, crypted_key_file, interactive):
    existing = autobloqueador_ops.load_config()
    if existing is None:
        raise click.ClickException("nada configurado ainda -- rode `pvx autobloqueador install` primeiro.")

    type_ = _resolve_type(type_, interactive)
    if type_ is None:
        return
    code = _resolve_code(code, interactive)
    if code is None:
        return

    crypted_key = _read_password_file(crypted_key_file)
    if crypted_key is None:
        crypted_key = _prompt_for_crypted_key(existing["url_base"], type_, code, interactive)
        if crypted_key is None:
            return

    autobloqueador_ops.save_config(existing["url_base"], type_, code, crypted_key)
    widgets.success("configuração atualizada.")
    logger.info(f"autobloqueador reconfigurado (type={type_}).")

    click.echo()
    click.echo("Executando verificação de status...")
    _run_initial_check(existing["url_base"], type_, crypted_key)


def _run_check(logger, dry_run):
    config = autobloqueador_ops.load_config()
    if config is None:
        raise click.ClickException("nada configurado -- rode `pvx autobloqueador install` primeiro.")

    autobloqueador_ops.log(f"Consultando status (type={config['type']}, dry_run={dry_run})...")
    try:
        with autobloqueador_ops.lock():
            result = autobloqueador_ops.check_and_apply(
                config["url_base"], config["type"], config["crypted_key"], dry_run=dry_run,
            )
    except autobloqueador_ops.AutobloqueadorError as e:
        autobloqueador_ops.log(f"ERRO: {e}")
        raise click.ClickException(str(e))

    autobloqueador_ops.log(f"HTTP Status: {result['http_code']}")
    if result["action"]:
        prefix = "[DRY-RUN] seria executado" if dry_run else "executado"
        autobloqueador_ops.log(f"Ação: {result['action']} ({prefix})")
    else:
        autobloqueador_ops.log("Nenhuma ação necessária.")
    if result["warning"]:
        autobloqueador_ops.log(f"AVISO: {result['warning']}")
        logger.warning(result["warning"])

    logger.info(f"autobloqueador run -- http_code={result['http_code']} action={result['action']}.")
    _report_check_result(result, dry_run)


def _run_status():
    config = autobloqueador_ops.load_config()
    if config is None:
        widgets.state("autobloqueador NÃO configurado -- rode `pvx autobloqueador install` primeiro.", ok=False)
        return

    widgets.state(f"autobloqueador configurado (type={config['type']})", ok=True)
    click.echo(f"  url_base: {config['url_base']}")
    click.echo(f"  code: {config['code']}")
    click.echo(f"  crypted_key: {config['crypted_key'][:20]}...")

    last = autobloqueador_ops.last_response()
    if last:
        click.echo(f"  último status: {last['http_code']} ({last.get('timestamp', '?')})")
    else:
        click.echo("  último status: nenhum ainda")

    click.echo()
    timer = autobloqueador_ops.timer_status()
    click.echo(timer if timer else "timer não instalado")


def _run_remove(logger, delete_config, interactive):
    try:
        with widgets.spinner("Removendo service + timer..."):
            autobloqueador_ops.remove_timer()
    except autobloqueador_ops.AutobloqueadorError as e:
        raise click.ClickException(str(e))
    widgets.success("service + timer removidos.")

    if autobloqueador_ops.configs_exist():
        should_delete = delete_config or (
            interactive and ask_confirm(
                "Também remover a configuração salva (url/type/code/crypted_key)? "
                "Sem isso, um novo `install` reaproveita sem pedir de novo.",
                default=False,
            )
        )
        if should_delete:
            autobloqueador_ops.remove_config()
            widgets.success("configuração removida.")

    logger.info("autobloqueador removido.")


class AutobloqueadorModule(PvxModule):
    name = "autobloqueador"
    version = "0.1.1"

    def cli_group(self):
        @click.group(name="autobloqueador")
        def group():
            pass

        @group.command(name="install")
        @click.option("--url-base", default="auto-blocker.falevox.com.br")
        @click.option("--type", "type_", type=click.Choice(autobloqueador_ops.TYPES), default=None)
        @click.option("--code", default=None, help="código único da instalação (máx 255 caracteres).")
        @click.option("--crypted-key-file", default=None, help="arquivo com o crypted_key recebido do /register.")
        @click.option("--pvx-bin", default="/usr/local/bin/pvx")
        def install_cmd(url_base, type_, code, crypted_key_file, pvx_bin):
            _require_root()
            logger = self.get_logger()
            interactive = _is_interactive()
            try:
                _run_install(logger, url_base, type_, code, crypted_key_file, pvx_bin, interactive)
            except click.ClickException:
                raise
            else:
                if interactive:
                    widgets.pause()

        @group.command(name="reconfig")
        @click.option("--type", "type_", type=click.Choice(autobloqueador_ops.TYPES), default=None)
        @click.option("--code", default=None, help="código único da instalação (máx 255 caracteres).")
        @click.option("--crypted-key-file", default=None, help="arquivo com o crypted_key recebido do /register.")
        def reconfig_cmd(type_, code, crypted_key_file):
            _require_root()
            logger = self.get_logger()
            interactive = _is_interactive()
            try:
                _run_reconfig(logger, type_, code, crypted_key_file, interactive)
            except click.ClickException:
                raise
            else:
                if interactive:
                    widgets.pause()

        @group.command(name="run")
        @click.option("--dry-run", is_flag=True, help="testa sem executar pm2/asterisk.")
        def run_cmd(dry_run):
            _require_root()
            logger = self.get_logger()
            _run_check(logger, dry_run)

        @group.command(name="status")
        def status_cmd():
            _run_status()
            if _is_interactive():
                widgets.pause()

        @group.command(name="logs")
        @click.option("--lines", type=int, default=100)
        def logs_cmd(lines):
            content = autobloqueador_ops.tail_log(lines=lines)
            click.echo(content if content else "log vazio ou não encontrado.")
            if _is_interactive():
                widgets.pause()

        @group.command(name="start")
        def start_cmd():
            _require_root()
            logger = self.get_logger()
            try:
                with widgets.spinner("Iniciando timer..."):
                    autobloqueador_ops.start_timer()
            except autobloqueador_ops.AutobloqueadorError as e:
                raise click.ClickException(str(e))
            widgets.success("timer iniciado.")
            logger.info("autobloqueador start.")
            if _is_interactive():
                widgets.pause()

        @group.command(name="stop")
        def stop_cmd():
            _require_root()
            logger = self.get_logger()
            try:
                with widgets.spinner("Parando timer..."):
                    autobloqueador_ops.stop_timer()
            except autobloqueador_ops.AutobloqueadorError as e:
                raise click.ClickException(str(e))
            widgets.success("timer parado.")
            logger.info("autobloqueador stop.")
            if _is_interactive():
                widgets.pause()

        @group.command(name="remove")
        @click.option(
            "--delete-config", is_flag=True,
            help="também remove a configuração salva -- --yes sozinho (de outros comandos) nunca implica isso.",
        )
        def remove_cmd(delete_config):
            _require_root()
            logger = self.get_logger()
            interactive = _is_interactive()
            try:
                _run_remove(logger, delete_config, interactive)
            except click.ClickException:
                raise
            else:
                if interactive:
                    widgets.pause()

        return group


cli = AutobloqueadorModule()
