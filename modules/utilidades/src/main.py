import os
import subprocess
import sys

import click

from pvx.interactive import widgets
from pvx.modules.base import PvxModule

import audit_ops
import checklist_phonevox
import issabel_detect
import sngrep_ops

_AUDIT_STATUS = {
    0: "limpo/suspeito",
    1: "comprometido",
    2: "sistema não suportado",
    3: "indefinido (rodou degradado, sem achado)",
}


def _is_interactive():
    return sys.stdin.isatty()


def _require_root():
    if os.geteuid() != 0:
        raise click.ClickException("audit precisa rodar como root (sudo).")


def _print_checklist(results):
    # pedido ao vivo: "Detalhe" misturava descrição (o que o item significa)
    # e valor dinâmico no mesmo texto -- agora são colunas separadas.
    rows = [
        [result["rule"], result["description"], result["value"], widgets.status_cell(result["level"])]
        for result in results
    ]
    widgets.table(["Regra", "Descrição", "Valor", "Resumo"], rows)


class UtilidadesModule(PvxModule):
    name = "utilidades"
    version = "0.1.12"

    def cli_group(self):
        @click.group(name="utilidades")
        def group():
            pass

        @group.command(
            name="checks-phonevox", help="roda o checklist padrão Phonevox (só em servidor Issabel).",
        )
        def checks_phonevox_cmd():
            if not issabel_detect.is_issabel():
                raise click.ClickException("checks-phonevox só roda em servidor Issabel.")

            widgets.title("pvx > utilidades > checks-phonevox")
            _print_checklist(checklist_phonevox.run_all())

            if _is_interactive():
                widgets.pause()

        @group.command(
            name="install-sngrep", help="instala o sngrep (sniffer SIP), idempotente.",
        )
        def install_sngrep_cmd():
            widgets.title("pvx > utilidades > install-sngrep")

            if sngrep_ops.is_installed():
                widgets.message("sngrep já está instalado -- nada a fazer.")
            else:
                distro = sngrep_ops.detect_distro()
                logger = self.get_logger()
                try:
                    sngrep_ops.install(distro)
                except sngrep_ops.SngrepError as e:
                    logger.error(f"install-sngrep: {e}")
                    raise click.ClickException("falha ao instalar sngrep -- veja `pvx logs utilidades`.")
                widgets.success("sngrep instalado.")
                logger.info("sngrep instalado.")

            if _is_interactive():
                widgets.pause()

        @group.command(
            name="audit", help="roda a auditoria de comprometimento (mineração, persistência, webshell, abuso de PBX...).",
        )
        def audit_cmd():
            _require_root()
            logger = self.get_logger()
            widgets.title("pvx > utilidades > audit")

            path = audit_ops.deploy(audit_ops.default_dest_dir())
            result = subprocess.run([path, "--text"])
            status = _AUDIT_STATUS.get(result.returncode, f"código {result.returncode}")
            logger.info(f"utilidades audit concluído: {status}.")

            if _is_interactive():
                widgets.pause()
            sys.exit(result.returncode)

        return group


cli = UtilidadesModule()
