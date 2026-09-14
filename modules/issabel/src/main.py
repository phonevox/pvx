import sys

import click

from pvx.interactive import widgets
from pvx.interactive.inputs import ask_checkbox, ask_confirm, ask_select, ask_text, checkbox_choice
from pvx.modules.base import PvxModule

import backup_ops
import security_scan

_TUDO = "Todos os componentes (tudo)"
_ABORTAR = "Abortar"
_PROSSEGUIR = "Prosseguir mesmo assim"
_PROSSEGUIR_REMOVENDO = "Prosseguir removendo os arquivos suspeitos"
_PROSSEGUIR_SELECIONANDO = "Prosseguir selecionando o que remover"
_SUSPICIOUS_CHOICES = [_ABORTAR, _PROSSEGUIR, _PROSSEGUIR_REMOVENDO, _PROSSEGUIR_SELECIONANDO]
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


def _print_audit(scan_result):
    for finding in scan_result["findings"]:
        widgets.check_result(str(finding), "ok" if finding.level == "ok" else "error")
    level, text = security_scan.verdict(scan_result)
    widgets.check_result(text, level)
    return level


def _run_audit(path):
    try:
        return security_scan.scan_backup(path)
    except security_scan.SecurityScanError as e:
        raise click.ClickException(str(e))


# achado de dialplan aponta uma LINHA dentro de um .conf que também carrega
# dialplan legítimo -- apagar o arquivo inteiro (o único jeito de "podar")
# destruiria configuração real junto, então nunca entra na lista de pruning.
def _is_prunable(finding):
    return " (linha " not in finding.path


def _finding_key(finding):
    return f"{finding.label}::{finding.path}"


def _prunable_findings(scan_result):
    return [f for f in scan_result["findings"] if f.level == "suspeito" and _is_prunable(f)]


def _prune_all(logger, path, findings):
    removed = security_scan.prune_backup(path, findings)
    logger.info(f"pruning removeu {removed} arquivo(s) de {path}.")
    widgets.success(f"{removed} arquivo(s) suspeito(s) removido(s) do backup.")


def _prompt_and_prune(logger, path, findings, message):
    items = [checkbox_choice(_finding_key(f), description=f.reason, checked=True) for f in findings]
    chosen = ask_checkbox(message, items)
    to_remove = [f for f in findings if _finding_key(f) in (chosen or [])]
    if to_remove:
        _prune_all(logger, path, to_remove)


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
            path, warning = backup_ops.export_backup(
                filename, selected, generated_by=f"pvx issabel v{cli.version}",
            )
    except backup_ops.IssabelBackupError as e:
        logger.error(f"export falhou: {e}")
        raise click.ClickException(str(e))
    if warning:
        # não fatal -- issabel-helper retorna código de erro sempre que um
        # componente individual falha (banco ausente etc.), igual a própria
        # interface web nativa, mesmo com o backup gerado com sucesso.
        logger.warning(f"issabel-helper reportou avisos durante o export: {warning}")
        widgets.warning("issabel-helper reportou avisos (alguns componentes podem não existir nessa central) -- veja `pvx logs issabel`.")
    logger.info(f"backup exportado em {path}.")
    widgets.success(f"backup gerado em {path}.")

    if interactive and ask_confirm("Quer conferir esse backup antes de finalizar?", default=False):
        widgets.section("Auditoria de segurança (heurística, não é antivírus)")
        scan_result = _run_audit(path)
        _print_audit(scan_result)

        prunable = _prunable_findings(scan_result)
        if prunable:
            _prompt_and_prune(
                logger, path, prunable, "Quais arquivos suspeitos remover do backup? (pruning seletivo)",
            )


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

    security_override = False
    if interactive and not ask_confirm("Você confia nesse backup?", default=True):
        widgets.section("Auditoria de segurança (heurística, não é antivírus)")
        scan_result = _run_audit(path)
        level = _print_audit(scan_result)
        if level == "error":
            choice = ask_select(
                "Foram encontrados achados suspeitos na auditoria. O que deseja fazer?",
                _SUSPICIOUS_CHOICES, default=_ABORTAR,
            )
            if choice is None or choice == _ABORTAR:
                return
            security_override = True
            if choice != _PROSSEGUIR:
                prunable = _prunable_findings(scan_result)
                if prunable:
                    if choice == _PROSSEGUIR_REMOVENDO:
                        _prune_all(logger, path, prunable)
                    else:
                        _prompt_and_prune(
                            logger, path, prunable, "Quais arquivos suspeitos remover antes de restaurar?",
                        )

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
        # já confirmou explicitamente "restaurar mesmo assim" depois de ver
        # os achados suspeitos -- perguntar nas mesmas palavras de novo aqui
        # é só fricção repetida.
        if not security_override and not ask_confirm(
            "Restaurar esse backup por cima da central atual? Isso sobrescreve dados existentes.",
            default=False,
        ):
            return
    elif not yes:
        raise click.ClickException("restaurar é destrutivo -- confirme com --yes.")

    try:
        with widgets.step("Restaurando backup..."):
            warning = backup_ops.import_backup(path, selected)
    except backup_ops.IssabelBackupError as e:
        logger.error(f"import falhou: {e}")
        raise click.ClickException(str(e))
    if warning:
        logger.warning(f"issabel-helper reportou avisos durante o import: {warning}")
        widgets.warning("issabel-helper reportou avisos durante a restauração -- veja `pvx logs issabel`.")
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
    generated_by = info["manifest"].get("gerado_por")
    if generated_by:
        widgets.item(f"Gerado por: {generated_by} em {info['manifest'].get('gerado_em', '?')}")
    widgets.section("Componentes")
    available = backup_ops.available_components()
    for key in info["components"]:
        widgets.item(key, comment=available.get(key))

    widgets.section("Auditoria de segurança (heurística, não é antivírus)")
    _print_audit(_run_audit(file))


class IssabelModule(PvxModule):
    name = "issabel"
    version = "0.1.5"

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
