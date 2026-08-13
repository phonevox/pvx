import click

from pvx import config
from pvx.modules import loader
from pvx.version import __version__


def discover_installed_modules():
    return loader.discover(config.modules_dir())


def build_cli():
    @click.group()
    @click.version_option(version=__version__, prog_name="pvx")
    def cli():
        pass

    for name, module in discover_installed_modules().items():
        cli.add_command(module.cli_group(), name=name)

    return cli


cli = build_cli()
