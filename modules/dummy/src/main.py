import click

from pvx.modules.base import PvxModule


class DummyModule(PvxModule):
    name = "dummy"
    version = "0.1.0"

    def cli_group(self):
        @click.group()
        def group():
            pass

        @group.command()
        def hello():
            click.echo("hello from dummy")

        return group


cli = DummyModule()
