import click

from pvx.modules.base import PvxModule


class DummyModule(PvxModule):
    name = "dummy"
    version = "0.1.2"

    def cli_group(self):
        @click.group()
        def group():
            pass

        @group.command()
        def hello():
            self.get_logger().info("hello invocado.")
            click.echo("hello from dummy")

        return group


cli = DummyModule()
