import click

from pvx.modules.base import PvxModule


class DummyModule(PvxModule):
    name = "dummy"
    version = "0.1.1"

    def cli_group(self):
        logger = self.get_logger()

        @click.group()
        def group():
            pass

        @group.command()
        def hello():
            logger.info("hello invocado.")
            click.echo("hello from dummy")

        return group


cli = DummyModule()
