import time

import click

from pvx.cli import discover_installed_modules
from pvx.interactive import widgets
from pvx.interactive.inputs import ask_select
from pvx.logging_ import viewer

_ALL_LABEL = "tudo (core + módulos)"


class LogsScreen:
    def render(self):
        modules = discover_installed_modules()
        choices = [_ALL_LABEL, "core", *modules.keys(), "voltar"]
        selected = ask_select("pvx > logs >", choices)
        if selected is None or selected == "voltar":
            return "BACK"

        names = viewer.list_log_names() if selected == _ALL_LABEL else [selected]
        click.echo(viewer.read_combined_logs(names, lines=100))

        # auto-follow: acompanha ao vivo até o usuário voltar -- ctrl-c aqui é tratado
        # igual esc/seleção nula nos prompts (nunca crasha a sessão do menu inteira).
        widgets.message("acompanhando ao vivo -- ctrl-c pra voltar.")
        follower = viewer.LogFollower(names)
        try:
            while True:
                for line in follower.poll():
                    click.echo(line)
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        return "BACK"
