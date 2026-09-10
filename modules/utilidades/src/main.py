import sys

import click

from pvx.interactive import widgets
from pvx.modules.base import PvxModule

import checklist_phonevox
import issabel_detect


def _is_interactive():
    return sys.stdin.isatty()


def _print_checklist(results):
    # célula de seção fica em branco quando repete a de cima -- itens
    # adjacentes da mesma seção (zabbix: config + script de auditoria) ficam
    # visualmente agrupados sem repetir o nome em toda linha.
    rows = []
    last_section = None
    for result in results:
        section_cell = result["section"] if result["section"] != last_section else ""
        last_section = result["section"]
        rows.append([section_cell, widgets.status_cell(result["level"]), result["text"]])
    widgets.table(["Seção", "Status", "Detalhe"], rows)


class UtilidadesModule(PvxModule):
    name = "utilidades"
    version = "0.1.2"

    def cli_group(self):
        @click.group(name="utilidades")
        def group():
            pass

        @group.group(name="checklist", help="checklists prontos de verificação.")
        def checklist_group():
            pass

        @checklist_group.command(
            name="phonevox", help="roda o checklist padrão Phonevox (só em servidor Issabel).",
        )
        def phonevox_cmd():
            if not issabel_detect.is_issabel():
                raise click.ClickException("checklist phonevox só roda em servidor Issabel.")

            widgets.title("pvx > utilidades > checklist phonevox")
            _print_checklist(checklist_phonevox.run_all())

            if _is_interactive():
                widgets.pause()

        return group


cli = UtilidadesModule()
