import click

from pvx.cli import discover_installed_modules
from pvx.interactive.inputs import ask_select
from pvx.logging_ import viewer


class LogsScreen:
    def render(self):
        modules = discover_installed_modules()
        selected = ask_select("pvx > logs >", list(modules.keys()))
        if selected is None:
            return "BACK"
        click.echo(viewer.read_log(selected, lines=None))
        return "BACK"
