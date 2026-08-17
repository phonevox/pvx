import os
import sys

import click

from pvx import config as pvx_config
from pvx.interactive import widgets
from pvx.interactive.inputs import ask_confirm, ask_select, ask_text
from pvx.modules.base import PvxModule

import apply as apply_module
import defaults
import deploy
import destinations
import local_ip
import reachability
import staged_config
import validators

CONFIG_FILENAME = "qint.conf"
CSV4_SUFFIXES = ("geral", "comercial", "suporte", "financeiro")
CSV4_LABELS = ("Geral", "Comercial", "Suporte", "Financeiro")
TYPE_ALIASES = {"ixc": "ixcsoft"}
TYPE_LABELS = {"IXCSoft": "ixcsoft", "SGP": "sgp"}


def _config_path():
    return str(pvx_config.modules_dir() / "qint" / "state" / CONFIG_FILENAME)


def _is_interactive():
    # mesma seam de ssh-hardening: CliRunner troca sys.stdin inteiro durante
    # o invoke(), então mockar sys.stdin.isatty direto não pega.
    return sys.stdin.isatty()


def _ask_csv4_group(base, prefix, label):
    for suffix, sub_label in zip(CSV4_SUFFIXES, CSV4_LABELS):
        key = f"{prefix}_{suffix}"
        value = ask_text(f"ID do {label} ({sub_label}):", default=base.get(key))
        if value is None:
            return False
        base[key] = value
    return True


def _apply_csv4(base, value, prefix):
    if value is None:
        return
    existing = tuple(base.get(f"{prefix}_{suffix}", "") for suffix in CSV4_SUFFIXES)
    for suffix, resolved in zip(CSV4_SUFFIXES, validators.parse_csv4(value, existing)):
        base[f"{prefix}_{suffix}"] = resolved


class QintModule(PvxModule):
    name = "qint"
    version = "0.1.0"

    def cli_group(self):
        @click.group(name="qint")
        def group():
            pass

        @group.command(name="prepare")
        @click.argument("tipo")
        @click.option("--sftp", default=None)
        @click.option("--url", default=None)
        @click.option("--token", default=None)
        @click.option("--timecondition-out", default=None)
        @click.option("--filas", default=None)
        @click.option("--asterisk-ip", default=None)
        @click.option("--versao", default=None)
        @click.option("--filial", default=None)
        @click.option("--departamentos", default=None)
        @click.option("--assuntos", default=None)
        @click.option("--app", default=None)
        @click.option("--setores", default=None)
        @click.option("--ocorrencias", default=None)
        @click.option("--motivo-os", default=None)
        def prepare_cmd(
            tipo, sftp, url, token, timecondition_out, filas, asterisk_ip, versao,
            filial, departamentos, assuntos, app, setores, ocorrencias, motivo_os,
        ):
            if os.geteuid() != 0:
                raise click.ClickException("qint precisa rodar como root (sudo).")

            tipo = TYPE_ALIASES.get(tipo, tipo)
            if tipo not in ("ixcsoft", "sgp"):
                raise click.ClickException(f"tipo inválido: {tipo} (use ixcsoft/ixc ou sgp)")

            existing = staged_config.load(_config_path())
            base = dict(existing) if existing and existing.get("type") == tipo else {"type": tipo}

            if sftp is not None:
                try:
                    parsed = validators.parse_sftp(sftp)
                except ValueError as e:
                    raise click.ClickException(str(e))
                base["sftp_user"], base["sftp_host"], base["sftp_port"] = (
                    parsed["user"], parsed["host"], parsed["port"],
                )

            if url is not None:
                if not validators.validate_url(url):
                    raise click.ClickException(f"URL inválida: {url}")
                base["erp_url"] = url

            if token is not None:
                base["token"] = token
            if timecondition_out is not None:
                base["id_timecondition_exitpoint"] = timecondition_out
            if asterisk_ip is not None:
                base["asterisk_ip"] = asterisk_ip
            if versao is not None:
                base["sftp_versao"] = versao

            _apply_csv4(base, filas, "fila")
            if tipo == "ixcsoft":
                if filial is not None:
                    base["id_filial"] = filial
                _apply_csv4(base, departamentos, "id_departamento")
                _apply_csv4(base, assuntos, "id_assunto")
            else:
                if app is not None:
                    base["app"] = app
                _apply_csv4(base, setores, "id_setor")
                _apply_csv4(base, ocorrencias, "id_ocorrencia")
                _apply_csv4(base, motivo_os, "id_motivo_os")

            staged_config.save(_config_path(), defaults.apply_defaults(base))
            click.echo(f"config do qint ({tipo}) atualizada.")

        @group.command(name="setup")
        @click.argument("tipo", required=False, default=None)
        def setup_cmd(tipo):
            if os.geteuid() != 0:
                raise click.ClickException("qint precisa rodar como root (sudo).")
            if not _is_interactive():
                raise click.ClickException(
                    "setup precisa de terminal -- use `pvx qint prepare <tipo> [flags]`."
                )

            if tipo is None:
                label = ask_select("Tipo de integração:", ["IXCSoft", "SGP"])
                if label is None:
                    return
                tipo = TYPE_LABELS[label]
            else:
                tipo = TYPE_ALIASES.get(tipo, tipo)
                if tipo not in ("ixcsoft", "sgp"):
                    raise click.ClickException(f"tipo inválido: {tipo} (use ixcsoft/ixc ou sgp)")

            existing = staged_config.load(_config_path())
            base = dict(existing) if existing and existing.get("type") == tipo else {"type": tipo}

            sftp_default = None
            if base.get("sftp_user"):
                sftp_default = f"{base['sftp_user']}@{base['sftp_host']}"
            while True:
                sftp_value = ask_text("SFTP (user@host[:port]):", default=sftp_default)
                if sftp_value is None:
                    return
                try:
                    parsed = validators.parse_sftp(sftp_value)
                except ValueError as e:
                    click.echo(str(e))
                    continue

                with widgets.spinner(f"Testando conexão com {parsed['host']}:{parsed['port']}..."):
                    reachable = reachability.is_reachable(parsed["host"], parsed["port"])
                if reachable or sftp_value == sftp_default:
                    base["sftp_user"], base["sftp_host"], base["sftp_port"] = (
                        parsed["user"], parsed["host"], parsed["port"],
                    )
                    break
                click.echo(
                    f"não consegui alcançar {parsed['host']}:{parsed['port']} -- "
                    "digite de novo pra confirmar mesmo assim, ou corrija."
                )
                sftp_default = sftp_value

            for suffix, label in zip(CSV4_SUFFIXES, CSV4_LABELS):
                key = f"fila_{suffix}"
                value = ask_text(f"Fila {label}:", default=base.get(key))
                if value is None:
                    return
                base[key] = value

            value = ask_text(
                "ID da Time Condition de saída:", default=base.get("id_timecondition_exitpoint")
            )
            if value is None:
                return
            base["id_timecondition_exitpoint"] = value

            value = ask_text(
                "IP/host do Asterisk:", default=base.get("asterisk_ip") or local_ip.guess_local_ip()
            )
            if value is None:
                return
            base["asterisk_ip"] = value

            while True:
                value = ask_text("URL do ERP (http(s)://host[:porta]):", default=base.get("erp_url"))
                if value is None:
                    return
                if validators.validate_url(value):
                    base["erp_url"] = value
                    break
                click.echo("URL inválida -- precisa do protocolo, sem path/barra final.")

            hint = " (vazio mantém o atual)" if base.get("token") else ""
            value = ask_text(f"Token do ERP{hint}:", default="")
            if value is None:
                return
            if value:
                base["token"] = value

            if tipo == "ixcsoft":
                value = ask_text(
                    "ID da filial:", default=base.get("id_filial", defaults.TYPE_DEFAULTS["ixcsoft"]["id_filial"])
                )
                if value is None:
                    return
                base["id_filial"] = value
                if not _ask_csv4_group(base, "id_departamento", "Departamento"):
                    return
                if not _ask_csv4_group(base, "id_assunto", "Assunto"):
                    return
            else:
                value = ask_text("Nome do app:", default=base.get("app", defaults.TYPE_DEFAULTS["sgp"]["app"]))
                if value is None:
                    return
                base["app"] = value
                if not _ask_csv4_group(base, "id_setor", "Setor"):
                    return
                if not _ask_csv4_group(base, "id_ocorrencia", "Ocorrência"):
                    return
                if not _ask_csv4_group(base, "id_motivo_os", "Motivo de OS"):
                    return

            click.echo("Resumo:")
            for key in sorted(base):
                if key == "type":
                    continue
                display = "***" if key == "token" else base[key]
                click.echo(f"  {key}: {display}")

            if not ask_confirm("Salvar essa configuração?", default=True):
                click.echo("Descartado, nada foi salvo.")
                return

            staged_config.save(_config_path(), defaults.apply_defaults(base))
            click.echo(f"config do qint ({tipo}) salva. rode `pvx qint apply` quando quiser aplicar de verdade.")

        @group.command(name="apply")
        @click.option("--yes", is_flag=True)
        def apply_cmd(yes):
            if os.geteuid() != 0:
                raise click.ClickException("qint precisa rodar como root (sudo).")

            staged = staged_config.load(_config_path())
            if staged is None:
                raise click.ClickException(
                    "nenhuma config staged. rode `pvx qint prepare <tipo>` ou `pvx qint setup`."
                )

            missing = defaults.missing_fields(staged)
            if missing:
                raise click.ClickException(
                    "faltam campos obrigatórios: " + ", ".join(missing)
                    + " -- rode `pvx qint status` pra ver o que já está preenchido."
                )

            tipo = staged["type"]
            click.echo(f"tipo: {tipo}")
            for key in sorted(staged):
                if key == "type":
                    continue
                value = "***" if key == "token" else staged[key]
                click.echo(f"  {key}: {value}")
            click.echo(
                "Isso vai buscar via SFTP, sobrescrever arquivos reais no Asterisk/Issabel "
                "e recarregar o dialplan. Não há reversão automática."
            )

            if not yes and not ask_confirm("Confirma aplicar?", default=False):
                click.echo("Operação cancelada.")
                return

            for category in deploy.compute_conflicts(defaults.DESTINATION_BASE_DIRS):
                if not (yes or ask_confirm(f"O destino de '{category}' já existe. Sobrescrever?", default=False)):
                    click.echo("Operação abortada -- nada foi alterado.")
                    return

            state_dir = pvx_config.modules_dir() / "qint" / "state"
            with widgets.spinner("Aplicando integração..."):
                result = apply_module.apply(
                    staged,
                    staged.get("sftp_remote_path", "/sfiles/qint/integracoes"),
                    str(state_dir / "versions"),
                    defaults.DESTINATION_BASE_DIRS,
                    str(state_dir / "history.log"),
                )

            if result["reloaded"]:
                click.echo("Aplicado com sucesso.")
            else:
                click.echo(
                    "Aplicado, mas o dialplan não foi recarregado (asterisk não encontrado) "
                    "-- rode `asterisk -rx \"dialplan reload\"` manualmente."
                )

            click.echo("Crie manualmente no Issabel as seguintes destinations:")
            for name, context, label in destinations.destination_specs(tipo):
                click.echo(f"  {name} ({context}): {label}")
            click.echo(f"Aponte a URA de saída pra Time Condition ID {staged['id_timecondition_exitpoint']}.")

        @group.command(name="status")
        def status_cmd():
            existing = staged_config.load(_config_path())
            if existing is None:
                click.echo("nenhuma config staged. use `pvx qint prepare <tipo>` ou `pvx qint setup`.")
                return

            click.echo(f"tipo: {existing['type']}")
            for key in sorted(existing):
                if key == "type":
                    continue
                value = "***" if key == "token" else existing[key]
                click.echo(f"  {key}: {value}")

        return group


cli = QintModule()
