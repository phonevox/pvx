import sys
import tempfile

import click

from pvx.interactive import widgets
from pvx.interactive.inputs import ask_confirm, ask_password, ask_text
from pvx.modules.base import PvxModule

import magnus_ops

_INSTALL_HELP = (
    "Baixa e executa o instalador OFICIAL do MagnusBilling "
    "(magnussolution/magnusbilling7) -- não é um script do pvx."
)


def _is_interactive():
    return sys.stdin.isatty()


def _read_password_file(path):
    # nunca senha em argumento de linha de comando (fica em ~/.bash_history,
    # ps aux, etc.) -- mesma convenção de scripts/publish.sh e uoe.
    if path is None:
        return None
    return open(path).read().strip()


def _resolve_db_credentials(db_user, db_password_file, interactive):
    if db_user is None:
        if not interactive:
            raise click.ClickException("informe --db-user.")
        db_user = ask_text("Usuário do banco de dados:")
        if db_user is None:
            return None, None

    password = _read_password_file(db_password_file)
    if password is None:
        if not interactive:
            raise click.ClickException("informe --db-password-file.")
        password = ask_password("Senha do banco de dados:")
        if password is None:
            return None, None

    return db_user, password


def _run_export(logger, db_user, db_password_file, output_path, interactive):
    db_user, db_password = _resolve_db_credentials(db_user, db_password_file, interactive)
    if db_user is None:
        return

    try:
        with widgets.spinner("Gerando backup..."):
            result_path, warnings = magnus_ops.export_backup(db_user, db_password, output_path=output_path)
    except magnus_ops.MagnusError as e:
        raise click.ClickException(f"falha ao gerar o backup: {e}")

    for warning in warnings:
        logger.warning(warning)
        widgets.state(warning, ok=False)

    logger.info(f"backup exportado em {result_path}.")
    widgets.success(f"backup gerado em {result_path}.")


def _run_import(logger, backup_file, db_user, db_password_file, yes, interactive):
    if backup_file is None:
        if not interactive:
            raise click.ClickException("informe o arquivo de backup.")
        backup_file = ask_text("Caminho absoluto do arquivo de backup:")
        if backup_file is None:
            return

    if not magnus_ops.is_valid_archive(backup_file):
        raise click.ClickException(f"'{backup_file}' não é um arquivo .tar.gz válido ou está corrompido.")

    db_user, db_password = _resolve_db_credentials(db_user, db_password_file, interactive)
    if db_user is None:
        return

    with tempfile.TemporaryDirectory() as tmp_dir:
        magnus_ops.extract_archive(backup_file, tmp_dir)

        errors = magnus_ops.validate_extracted(tmp_dir)
        if errors:
            raise click.ClickException("\n".join(errors))

        if not yes:
            if not interactive:
                raise click.ClickException("ação destrutiva -- confirme com --yes.")
            warning = (
                f"Tem certeza que quer importar o backup '{backup_file}'? "
                "Isso sobrescreve o banco de dados, as configurações do Asterisk "
                "e os áudios da URA atuais."
            )
            if not ask_confirm(warning, default=False):
                widgets.message("nada foi alterado.")
                return

        try:
            with widgets.spinner("Restaurando backup..."):
                magnus_ops.restore(tmp_dir, db_user, db_password)
        except magnus_ops.MagnusError as e:
            raise click.ClickException(f"falha ao importar o backup: {e}")

    logger.info(f"backup '{backup_file}' importado.")
    widgets.success("backup importado com sucesso.")


def _run_install(logger, yes, interactive):
    already = magnus_ops.is_already_installed()
    if already:
        widgets.state("MagnusBilling já parece estar instalado nesse servidor.", ok=False)

    if not yes:
        if not interactive:
            raise click.ClickException(
                "informe --yes pra confirmar (roda o instalador oficial do MagnusBilling, de terceiro)."
            )
        warning = _INSTALL_HELP
        if already:
            warning += " Vai rodar por cima de uma instalação já existente."
        warning += " Continuar?"
        if not ask_confirm(warning, default=False):
            widgets.message("nada foi alterado.")
            return

    # a partir daqui é handoff completo pro instalador oficial -- ele é
    # interativo (prompts próprios, ex.: "Type I UNDERSTAND..."), então roda
    # sem spinner/captura por cima (um Live do rich por cima do terminal já
    # quebrou a leitura de stdin do instalador, achado ao vivo) e sem
    # sucesso/falha nosso depois -- resultado não é mais responsabilidade do
    # pvx a partir do momento que o instalador assume o terminal.
    logger.info("magnus install -- delegando ao instalador oficial do MagnusBilling.")
    magnus_ops.run_installer()


class MagnusModule(PvxModule):
    name = "magnus"
    version = "0.1.5"

    def cli_group(self):
        @click.group(name="magnus")
        def group():
            pass

        @group.group(name="backup")
        def backup_group():
            pass

        @backup_group.command(name="export")
        @click.option("--db-user", default=None)
        @click.option("--db-password-file", default=None, help="arquivo com a senha do banco de dados.")
        @click.option(
            "-o", "--output", "output_path", default=None,
            help="path do .tgz gerado (default: backup-pxmagnus.<dd-mm-yyyy>.tgz).",
        )
        def export_cmd(db_user, db_password_file, output_path):
            logger = self.get_logger()
            interactive = _is_interactive()
            try:
                _run_export(logger, db_user, db_password_file, output_path, interactive)
            except click.ClickException:
                raise
            else:
                if interactive:
                    widgets.pause()

        @backup_group.command(name="import")
        @click.argument("backup_file", required=False, default=None)
        @click.option("--db-user", default=None)
        @click.option("--db-password-file", default=None, help="arquivo com a senha do banco de dados.")
        @click.option("--yes", is_flag=True, help="pula a confirmação.")
        def import_cmd(backup_file, db_user, db_password_file, yes):
            logger = self.get_logger()
            interactive = _is_interactive()
            try:
                _run_import(logger, backup_file, db_user, db_password_file, yes, interactive)
            except click.ClickException:
                raise
            else:
                if interactive:
                    widgets.pause()

        @group.command(name="install", help=_INSTALL_HELP)
        @click.option("--yes", is_flag=True, help="pula a confirmação.")
        def install_cmd(yes):
            logger = self.get_logger()
            interactive = _is_interactive()
            try:
                _run_install(logger, yes, interactive)
            except click.ClickException:
                raise
            else:
                if interactive:
                    widgets.pause()

        return group


cli = MagnusModule()
