import sys

import click

from pvx.interactive import widgets
from pvx.modules.base import PvxModule

import checklist_phonevox
import issabel_detect


def _is_interactive():
    return sys.stdin.isatty()


def _print_checklist(results):
    rows = [
        [result["section"], result["text"], widgets.status_cell(result["level"])]
        for result in results
    ]
    widgets.table(["Seção", "Detalhe", "Status"], rows)


class UtilidadesModule(PvxModule):
    name = "utilidades"
    version = "0.1.5"

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

        return group


cli = UtilidadesModule()
