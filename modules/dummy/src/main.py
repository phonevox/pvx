import sys

import click

from pvx.interactive import widgets
from pvx.modules.base import PvxModule


def _is_interactive():
    return sys.stdin.isatty()


class DummyModule(PvxModule):
    name = "dummy"
    version = "0.1.4"

    def cli_group(self):
        @click.group()
        def group():
            pass

        @group.command(help="ecoa uma mensagem de teste.")
        def hello():
            self.get_logger().info("hello invocado.")
            click.echo("hello from dummy")
            if _is_interactive():
                widgets.pause()

        return group


cli = DummyModule()
