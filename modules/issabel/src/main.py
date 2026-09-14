import sys

import click

from pvx.interactive import widgets
from pvx.interactive.inputs import ask_checkbox, ask_confirm, ask_text, checkbox_choice
from pvx.modules.base import PvxModule

import backup_ops

_TUDO = "Todos os componentes (tudo)"
# grandes o bastante pra valer a pena não vir marcado por padrão (gravações e
# correio de voz podem ser vários GB numa central com histórico longo) --
# ainda aparecem no checklist, só não pré-selecionados.
_HEAVY_COMPONENTS = {"as_monitor", "as_voicemail"}


def _is_interactive():
    return sys.stdin.isatty()


def _export_choices(available):
    return [
        checkbox_choice(key, description=desc, checked=key not in _HEAVY_COMPONENTS)
        for key, desc in available.items()
    ]


def _import_choices(components_in_backup, available):
    return [checkbox_choice(_TUDO, checked=True)] + [
        checkbox_choice(key, description=available.get(key), checked=False)
        for key in components_in_backup
    ]


def _version_mismatch_warning(backup_version, installed_version):
    if not backup_version or not installed_version:
        return None
    backup_major = backup_version.split(".")[0]
    installed_major = installed_version.split(".")[0]
    if backup_major == installed_major:
        return None
    return (
        f"esse backup foi gerado no Issabel {backup_version} -- a central atual está no "
        f"Issabel {installed_version}. Restaurar pode causar problemas de compatibilidade."
    )


def _export_backup(logger, filename, components):
    interactive = _is_interactive()
    available = backup_ops.available_components()

    if filename is None:
        filename = backup_ops.default_filename()
        if interactive:
            filename = ask_text("Como deseja o nome do arquivo?", default=filename)
            if filename is None:
                return

    if components:
        unknown = [c for c in components if c not in available]
        if unknown:
            raise click.ClickException(f"componente(s) desconhecido(s): {', '.join(unknown)}")
        selected = list(components)
    elif interactive:
        selected = ask_checkbox("O que deseja salvar?", _export_choices(available))
        if selected is None:
            return
    else:
        selected = list(available)

    try:
        with widgets.step("Gerando backup..."):
            path = backup_ops.export_backup(filename, selected)
    except backup_ops.IssabelBackupError as e:
        logger.error(f"export falhou: {e}")
        raise click.ClickException(str(e))
    logger.info(f"backup exportado em {path}.")
    widgets.success(f"backup gerado em {path}.")


def _import_backup(logger, file, components, yes):
    interactive = _is_interactive()

    path = file
    if path is None:
        if not interactive:
            raise click.ClickException("informe o arquivo (--file).")
        path = ask_text("Onde está o arquivo?")
        if not path:
            return

    try:
        info = backup_ops.inspect_backup(path)
    except backup_ops.IssabelBackupError as e:
        logger.error(f"import falhou ao inspecionar o backup: {e}")
        raise click.ClickException(str(e))

    warning = _version_mismatch_warning(
        info["versions"].get("issabel"), backup_ops.installed_issabel_version(),
    )
    if warning:
        widgets.warning(warning)

    if components:
        selected = list(components)
    elif interactive:
        available = backup_ops.available_components()
        chosen = ask_checkbox("O que deseja importar?", _import_choices(info["components"], available))
        if chosen is None:
            return
        selected = info["components"] if _TUDO in chosen else [c for c in chosen if c != _TUDO]
    else:
        selected = info["components"]

    if interactive:
        if not ask_confirm(
            "Restaurar esse backup por cima da central atual? Isso sobrescreve dados existentes.",
            default=False,
        ):
            return
    elif not yes:
        raise click.ClickException("restaurar é destrutivo -- confirme com --yes.")

    try:
        with widgets.step("Restaurando backup..."):
            backup_ops.import_backup(path, selected)
    except backup_ops.IssabelBackupError as e:
        logger.error(f"import falhou: {e}")
        raise click.ClickException(str(e))
    logger.info(f"backup restaurado a partir de {path}.")
    widgets.success("backup restaurado.")


def _inspect_backup(file):
    interactive = _is_interactive()
    if file is None:
        if not interactive:
            raise click.ClickException("informe o arquivo.")
        file = ask_text("Onde está o arquivo?")
        if not file:
            return

    try:
        info = backup_ops.inspect_backup(file)
    except backup_ops.IssabelBackupError as e:
        raise click.ClickException(str(e))

    widgets.section("Backup")
    widgets.item(f"Issabel: {info['versions'].get('issabel', 'desconhecido')}")
    widgets.section("Componentes")
    available = backup_ops.available_components()
    for key in info["components"]:
        widgets.item(key, comment=available.get(key))


class IssabelModule(PvxModule):
    name = "issabel"
    version = "0.1.1"

    def cli_group(self):
        @click.group(name="issabel")
        def group():
            pass

        @group.group(name="backups")
        def backups_group():
            pass

        @backups_group.command(name="export", help="gera um backup local do Issabel (issabel-helper).")
        @click.option("--filename", default=None)
        @click.option("--components", multiple=True)
        def export_cmd(filename, components):
            _export_backup(self.get_logger(), filename, components)
            if _is_interactive():
                widgets.pause()

        @backups_group.command(name="import", help="restaura um backup local do Issabel (issabel-helper).")
        @click.option("--file", default=None)
        @click.option("--components", multiple=True)
        @click.option("--yes", is_flag=True)
        def import_cmd(file, components, yes):
            _import_backup(self.get_logger(), file, components, yes)
            if _is_interactive():
                widgets.pause()

        @backups_group.command(name="inspect", help="mostra o que tem dentro de um backup local do Issabel.")
        @click.argument("file", required=False)
        def inspect_cmd(file):
            _inspect_backup(file)
            if _is_interactive():
                widgets.pause()

        return group


cli = IssabelModule()
