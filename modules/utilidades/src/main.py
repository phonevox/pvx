import sys

import click

from pvx.interactive import widgets
from pvx.modules.base import PvxModule

import checklist_phonevox
import issabel_detect


def _is_interactive():
    return sys.stdin.isatty()


class UtilidadesModule(PvxModule):
    name = "utilidades"
    version = "0.1.0"

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
            widgets.section("Checklist")
            for result in checklist_phonevox.run_all():
                text = result["label"]
                if result["detail"]:
                    text += f": {result['detail']}"
                widgets.check_result(text, result["level"])

            if _is_interactive():
                widgets.pause()

        return group


cli = UtilidadesModule()
