import sys

import click

from pvx.interactive import widgets
from pvx.modules.base import PvxModule

import checklist_phonevox
import issabel_detect


def _is_interactive():
    return sys.stdin.isatty()


def _print_checklist(results):
    # section() só imprime quando o nome muda -- checks adjacentes da mesma
    # seção (zabbix: config + script de auditoria) ficam agrupados sob um
    # único header, em vez de repetir o nome pra cada item.
    last_section = None
    for result in results:
        if result["section"] != last_section:
            widgets.section(result["section"])
            last_section = result["section"]
        widgets.check_result(result["text"], result["level"])


class UtilidadesModule(PvxModule):
    name = "utilidades"
    version = "0.1.1"

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
