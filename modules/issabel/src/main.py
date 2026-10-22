import json
import os
import re
import socket
import subprocess
import sys
from pathlib import Path

import click

from pvx.interactive import widgets
from pvx.interactive.inputs import ask_checkbox, ask_confirm, ask_password, ask_select, ask_text, checkbox_choice
from pvx.modules.base import PvxModule

import audit_ops
import backup_ops
import health_checks
import security_scan
import trust_ops

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
    # extras da Phonevox (int_ixcsoft etc.) sempre têm descrição, mesmo sem
    # suporte local -- import_backup restaura eles na mão nesse caso.
    descriptions = {**backup_ops.EXTRA_COMPONENTS, **available}
    return [checkbox_choice(_TUDO, checked=True)] + [
        checkbox_choice(key, description=descriptions.get(key), checked=False)
        for key in components_in_backup
    ]


def _split_selected_components(selected, available):
    helper = [c for c in selected if c in available]
    manual = [c for c in selected if c not in available and c in backup_ops.MANUAL_COMPONENTS]
    unknown = [c for c in selected if c not in available and c not in backup_ops.MANUAL_COMPONENTS]
    return helper, manual, unknown


def _issabel_version(versions):
    # mesma prioridade de backup_ops.installed_issabel_version() -- ver
    # comentário lá (achado ao vivo: "issabelpbx" sem hífen pode ser a
    # versão de um framework interno bem diferente da versão de produto real
    # em "issabel-pbx" com hífen, mesmo dentro do mesmo versions.xml).
    return versions.get("issabel-pbx") or versions.get("issabelpbx") or versions.get("issabel")


def _major_version_differs(backup_version, installed_version):
    if not backup_version or not installed_version:
        return False
    return backup_version.split(".")[0] != installed_version.split(".")[0]


def _version_mismatch_warning(backup_version, installed_version):
    if not _major_version_differs(backup_version, installed_version):
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
    # mesma trust DB centralizada que `pvx issabel audit run` já consulta --
    # best-effort (merged_trusted_items nunca bloqueia por rede fora).
    trusted = trust_ops.merged_trusted_items()
    try:
        return security_scan.scan_backup(path, trusted_by_path=trusted)
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


def _autodetected_export_components(available):
    # sem o backupengine parcheado (marker ausente), os extras Phonevox não
    # entram em available_components() -- mas o diretório da integração pode
    # existir mesmo assim (instalada por fora do engine). Detecta pela
    # presença dos diretórios e oferece na lista, sinalizado, em vez de
    # simplesmente sumir do checklist de export.
    return {
        key: desc for key, desc in backup_ops.EXTRA_COMPONENTS.items()
        if key not in available and key in backup_ops.autodetect_components()
    }


def _export_backup(logger, filename, components):
    interactive = _is_interactive()
    available = backup_ops.available_components()
    autodetected = _autodetected_export_components(available)
    offered = {**available, **{k: f"{v} (autodetectado)" for k, v in autodetected.items()}}

    if filename is None:
        filename = backup_ops.default_filename()
        if interactive:
            filename = ask_text("Como deseja o nome do arquivo?", default=filename)
            if filename is None:
                return

    if not backup_ops.matches_native_naming(filename):
        widgets.warning(
            "esse nome não segue o padrão nativo do Issabel (issabelbackup-<14 dígitos>-XX.tar) -- "
            "esse backup só vai funcionar aqui no pvx, não vai aparecer nem poder ser importado "
            "pela tela \"Sistema > Backup and Restore\" do Issabel."
        )

    if components:
        unknown = [c for c in components if c not in offered]
        if unknown:
            raise click.ClickException(f"componente(s) desconhecido(s): {', '.join(unknown)}")
        selected = list(components)
    elif interactive:
        selected = ask_checkbox("O que deseja salvar?", _export_choices(offered))
        if selected is None:
            return
    else:
        selected = list(offered)

    helper_selected = [c for c in selected if c in available]
    manual_selected = [c for c in selected if c in autodetected]

    try:
        with widgets.step("Gerando backup..."):
            generated_by = f"pvx issabel v{cli.version}"
            if helper_selected:
                path, warning = backup_ops.export_backup(
                    filename, helper_selected, generated_by=generated_by,
                )
                if manual_selected:
                    # export_backup pode ter recusado e removido, sozinho,
                    # componente(s) não implementados nessa central (ver
                    # warning) -- lê de volta o que REALMENTE foi exportado
                    # em vez de confiar no que foi pedido.
                    actually_exported = backup_ops.inspect_backup(path)["components"]
                    backup_ops.record_components(path, actually_exported + manual_selected)
                    backup_ops.write_manifest(path, generated_by, manual_components=manual_selected)
            else:
                path = backup_ops.create_manual_backup_shell(
                    filename, manual_selected, generated_by=generated_by,
                )
                warning = None
            for key in manual_selected:
                backup_ops.export_manual_component(path, key)
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

    installed_version = backup_ops.installed_issabel_version()
    backup_version = _issabel_version(info["versions"])
    version_mismatch = _major_version_differs(backup_version, installed_version)
    warning = _version_mismatch_warning(backup_version, installed_version)
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

    available = backup_ops.available_components()
    if components:
        selected = list(components)
    elif interactive:
        chosen = ask_checkbox("O que deseja importar?", _import_choices(info["components"], available))
        if chosen is None:
            return
        selected = info["components"] if _TUDO in chosen else [c for c in chosen if c != _TUDO]
    else:
        selected = info["components"]

    helper_selected, manual_selected, unknown_selected = _split_selected_components(selected, available)
    if unknown_selected:
        raise click.ClickException(f"componente(s) desconhecido(s): {', '.join(unknown_selected)}")

    if interactive:
        # já confirmou explicitamente "restaurar mesmo assim" depois de ver
        # os achados suspeitos -- perguntar nas mesmas palavras de novo aqui
        # é só fricção repetida.
        if not security_override and not ask_confirm(
            "Restaurar esse backup por cima da central atual? Isso sobrescreve dados existentes "
            "e reinicia o Asterisk no final (derruba chamadas em andamento).",
            default=False,
        ):
            return
    elif not yes:
        raise click.ClickException("restaurar é destrutivo -- confirme com --yes.")

    try:
        with widgets.step("Restaurando backup..."):
            if version_mismatch:
                # versão diferente: usa o migrador nativo do Issabel (mesma
                # coisa que o botão "Migrate from Issabel 4" da web faz) em
                # vez do backupengine --restore -- ele cuida de menu.db,
                # senha de admin e upgrade dos módulos PBX sozinho. Já
                # reinicia o Asterisk sozinho no fim.
                warning = backup_ops.run_native_migration(path)
            else:
                warning = backup_ops.import_backup(path, helper_selected) if helper_selected else None
            manual_done = {key: backup_ops.restore_manual_component(path, key) for key in manual_selected}
            # achado ao vivo: um restore pode trocar arquivo que o Asterisk
            # já tem aberto (ex.: astdb.sqlite3) -- sem reiniciar, a conexão
            # antiga fica presa apontando pro estado de antes do restore
            # (db.c ast_db_put: SQL logic error) mesmo com o arquivo no
            # disco já correto. Reinicia sempre, mesmo quando o caminho de
            # migração acima já reinicia sozinho (custo extra de alguns
            # segundos, nunca prejudicial).
            restart_warning = backup_ops.restart_asterisk()
    except backup_ops.IssabelBackupError as e:
        logger.error(f"import falhou: {e}")
        raise click.ClickException(str(e))
    if warning:
        logger.warning(f"issabel-helper reportou avisos durante o import: {warning}")
        widgets.warning("issabel-helper reportou avisos durante a restauração -- veja `pvx logs issabel`.")
    if restart_warning:
        logger.warning(f"reinício do Asterisk pós-restore reportou avisos: {restart_warning}")
    logger.info(f"backup restaurado a partir de {path}.")
    widgets.success("backup restaurado.")
    for key, dirs in manual_done.items():
        logger.info(f"{key} restaurado manualmente (sem backupengine customizada): {', '.join(dirs)}")
        widgets.item(key, comment="restaurado manualmente pelo pvx (central sem backupengine customizada)")


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
    widgets.item(f"Issabel: {_issabel_version(info['versions']) or 'desconhecido'}")
    generated_by = info["manifest"].get("gerado_por")
    if generated_by:
        widgets.item(f"Gerado por: {generated_by} em {info['manifest'].get('gerado_em', '?')}")
    widgets.section("Componentes")
    available = backup_ops.available_components()
    for key in info["components"]:
        widgets.item(key, comment=available.get(key))

    widgets.section("Auditoria de segurança (heurística, não é antivírus)")
    _print_audit(_run_audit(file))


# saída deliberadamente crua (PASS/FAIL), não os widgets temáveis do menu --
# isso é pensado pra ser lido por script/cron/monitoramento, não pra tela
# interativa (ver NAV_HINT: ainda roda de dentro do menu via auto_menu, só
# sem o tema aplicado).
def _run_health_checks(checks):
    results = health_checks.run_checks(checks)
    failed = False
    for result in results:
        if result.passed:
            click.echo(f"{click.style('PASS', fg='green')} {result.name}")
        else:
            click.echo(f"{click.style('FAIL', fg='red')} {result.name} {result.detail}")
            failed = True
    return failed


# clone deliberado do status map de modules/utilidades/src/main.py -- mesmo
# script (audit.sh), mesmos exit codes.
_AUDIT_STATUS = {
    0: "limpo/suspeito",
    1: "comprometido",
    2: "sistema não suportado",
    3: "indefinido (rodou degradado, sem achado)",
}
_AUDIT_SEV_LEVEL = {"CRIT": "error", "HIGH": "error", "MED": "warn", "LOW": "warn"}
_AUDIT_LEVEL_TO_CHECK_RESULT = {
    "clean": "ok", "suspect": "warn", "compromised": "error", "unsupported": "warn", "unknown": "warn",
}
_AUDIT_TRUST_URL_ENV = "PVX_AUDIT_TRUST_URL"


def _require_root():
    if os.geteuid() != 0:
        raise click.ClickException("audit precisa rodar como root (sudo).")


def _trust_url(url):
    # sempre resolve pra algo -- trust_ops.DEFAULT_URL é o mesmo servidor do
    # registry de módulos, não existe mais "não configurado".
    return url or os.environ.get(_AUDIT_TRUST_URL_ENV) or trust_ops.DEFAULT_URL


def _run_audit_scan(logger, url):
    _require_root()
    path = audit_ops.deploy(audit_ops.default_dest_dir())
    result = subprocess.run([path], capture_output=True, text=True)
    try:
        report = json.loads(result.stdout)
    except ValueError:
        detail = (result.stderr or result.stdout or "saída vazia").strip()
        logger.error(f"issabel audit run: saída não é JSON válido -- {detail}")
        raise click.ClickException(f"audit.sh não retornou JSON válido: {detail}")

    trusted = trust_ops.merged_trusted_items(_trust_url(url))
    annotated = trust_ops.annotate_findings(report.get("findings", []), trusted)
    suppressed_count = sum(1 for _, matched in annotated if matched)

    level = report.get("level", "unknown")
    pbx = report.get("pbx")
    header = report.get("os", "?") + (f" / {pbx}" if pbx and pbx != "none" else "")
    widgets.section(header)
    widgets.item(f"audit.sh v{report.get('version', '?')}", comment=socket.gethostname())
    widgets.check_result(
        f"status: {level} (score {report.get('score', '?')}/100)",
        _AUDIT_LEVEL_TO_CHECK_RESULT.get(level, "warn"),
    )
    if report.get("classes"):
        widgets.item("classes: " + ", ".join(report["classes"]))
    if report.get("degraded"):
        widgets.warning("rodou sem root -- cobertura reduzida.")
    if report.get("reason"):
        widgets.description(f"motivo: {report['reason']}")

    if not annotated:
        widgets.success("nenhum achado.")
    for finding, matched in annotated:
        line = f"[{finding['sev']}] {finding['class']}: {finding['msg']}"
        if matched:
            # achado ainda EXISTE (nunca escondido) -- só marcado em cinza,
            # com a seta explicando por que não precisa de atenção agora. A
            # ORIGEM importa de propósito: trust de rede (publicado, vale
            # pra toda central) é bem diferente de trust só local (pendente
            # nesta central, ainda não publicado) -- nunca unificar os dois
            # na mensagem.
            caminho, origem = matched
            origem_label = "rede" if origem == "remoto" else "local, não publicado"
            widgets.description(line)
            widgets.description(f"  ↳ confiado ({origem_label}): {caminho}")
        else:
            widgets.check_result(line, _AUDIT_SEV_LEVEL.get(finding["sev"], "warn"))

    for note in report.get("notes", []):
        widgets.description(f"nota: {note}")
    widgets.description(f"duração: {report.get('duration_s', '?')}s")

    status = _AUDIT_STATUS.get(result.returncode, f"código {result.returncode}")
    logger.info(
        f"issabel audit run concluído: {status} "
        f"({len(annotated) - suppressed_count} achado(s) ativo(s), {suppressed_count} ignorado(s) pelo trust)."
    )
    return result.returncode


def _audit_trust(action, files):
    explanation = {
        "trust": "Calcula o sha256 de cada arquivo e grava como pendente localmente -- "
                 "não publica nada ainda (rode 'publish-trust' pra isso).",
        "untrust": "Marca arquivo(s) pra deixarem de ser confiados -- grava pendência local, "
                   "não publica nada ainda (rode 'publish-trust' pra isso).",
    }[action]
    interactive = _is_interactive()

    if not files:
        if not interactive:
            raise click.ClickException("informe pelo menos um arquivo.")
        widgets.description(explanation)
        answer = ask_text("Arquivo(s) (separe por espaço ou vírgula):")
        if not answer:
            return
        files = [f for f in re.split(r"[,\s]+", answer.strip()) if f]
    elif interactive:
        widgets.description(explanation)

    for f in files:
        sha256 = trust_ops.stage(f, action)
        widgets.success(f"{f} -- {action} pendente ({sha256[:12]}...).")


def _check_trust(url, clear, files):
    if clear:
        explanation = (
            "Remove a pendência local " + (f"de {len(files)} arquivo(s)" if files else "inteira")
            + " -- não desfaz nada já publicado no servidor, só o que ainda não foi enviado."
        )
        if _is_interactive():
            widgets.description(explanation)
            if not ask_confirm("Confirma a remoção da pendência local?", default=False):
                return
        removed = trust_ops.remove_pending(files or None)
        widgets.success(f"{removed} item(ns) removido(s) da pendência local.")

    effective_url = _trust_url(url)
    remote_count = len(trust_ops.fetch_remote_trust(effective_url))
    pending_count = len(trust_ops.load_pending())

    widgets.section("Trust")
    widgets.item(f"Remoto ({effective_url}): {remote_count} item(ns)")
    widgets.item(f"Local (pendente, ainda não publicado): {pending_count} item(ns)")


def _publish_trust(logger, url, password_file):
    if _is_interactive():
        widgets.description(
            "Envia as pendências de trust/untrust (hash + caminho + IP de origem) pro "
            "servidor configurado, autenticando com uma senha compartilhada -- nunca publica "
            "sozinho, só quando você roda isso explicitamente."
        )

    pending = trust_ops.load_pending()
    if not pending:
        widgets.message("nada pendente pra publicar.")
        return

    effective_url = _trust_url(url)
    interactive = _is_interactive()
    if password_file:
        password = Path(password_file).read_text().strip()
    elif interactive:
        password = ask_password("Senha do servidor de trust:")
        if password is None:
            return
    else:
        raise click.ClickException("informe --password-file (senha nunca direto na CLI).")

    try:
        with widgets.step("Publicando trust..."):
            result = trust_ops.publish(password, url=effective_url, gerado_por=socket.gethostname())
    except trust_ops.TrustError as e:
        logger.error(f"publish-trust falhou: {e}")
        raise click.ClickException(str(e))

    logger.info(f"publish-trust concluído: {result}.")
    widgets.success(f"{result.get('aplicados', '?')} item(ns) aplicado(s), {result.get('total', '?')} no total.")


class IssabelModule(PvxModule):
    name = "issabel"
    version = "0.2.7"

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

        @group.command(
            name="tests",
            help="checagens de saúde ao vivo na central (astdb, odbc, permissões) -- PASS/FAIL por linha.",
        )
        @click.option(
            "--check", "checks", multiple=True, type=click.Choice(sorted(health_checks.CHECKS)),
            help="nome da checagem (repetível); por padrão roda todas.",
        )
        @click.pass_context
        def tests_cmd(ctx, checks):
            failed = _run_health_checks(checks)
            if _is_interactive():
                widgets.pause()
            if failed:
                ctx.exit(1)

        @group.group(name="audit")
        def audit_group():
            pass

        @audit_group.command(
            name="run", help="roda a auditoria de comprometimento (clone do utilidades, com filtro de trust).",
        )
        @click.option("--url", default=None, help=f"servidor de trust (ou env {_AUDIT_TRUST_URL_ENV}).")
        @click.pass_context
        def audit_run_cmd(ctx, url):
            logger = self.get_logger()
            widgets.title("pvx > issabel > audit > run")
            returncode = _run_audit_scan(logger, url)
            if _is_interactive():
                widgets.pause()
            if returncode == 1:
                ctx.exit(1)

        @audit_group.command(
            name="trust", help="marca arquivo(s) como confiável -- só grava pendência local, não publica sozinho.",
        )
        @click.argument("files", nargs=-1)
        def audit_trust_cmd(files):
            _audit_trust("trust", files)
            if _is_interactive():
                widgets.pause()

        @audit_group.command(
            name="untrust",
            help="remove a confiança de arquivo(s) -- só grava pendência local, não publica sozinho.",
        )
        @click.argument("files", nargs=-1)
        def audit_untrust_cmd(files):
            _audit_trust("untrust", files)
            if _is_interactive():
                widgets.pause()

        @audit_group.command(
            name="publish-trust", help="publica as pendências de trust/untrust pro servidor centralizado.",
        )
        @click.option("--url", default=None, help=f"servidor de trust (ou env {_AUDIT_TRUST_URL_ENV}).")
        @click.option(
            "--password-file", default=None, type=click.Path(exists=True, dir_okay=False),
            help="arquivo com a senha (nunca passe a senha direto na CLI).",
        )
        def audit_publish_trust_cmd(url, password_file):
            logger = self.get_logger()
            _publish_trust(logger, url, password_file)
            if _is_interactive():
                widgets.pause()

        @audit_group.command(
            name="check-trust", help="mostra quantos itens de trust existem no servidor e pendentes localmente.",
        )
        @click.option("--url", default=None, help=f"servidor de trust (ou env {_AUDIT_TRUST_URL_ENV}).")
        @click.option(
            "--clear", is_flag=True,
            help="remove a pendência local (tudo, ou só os arquivos passados como argumento).",
        )
        @click.argument("files", nargs=-1)
        def audit_check_trust_cmd(url, clear, files):
            _check_trust(url, clear, files)
            if _is_interactive():
                widgets.pause()

        return group


cli = IssabelModule()
