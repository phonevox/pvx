import click

from pvx import config
from pvx.logging_ import viewer
from pvx.modules import installer, loader
from pvx.version import __version__


def discover_installed_modules():
    return loader.discover(config.modules_dir())


def build_module_group():
    @click.group(name="module")
    def module_group():
        pass

    @module_group.command(name="install")
    @click.argument("name")
    @click.option("--version", "version_", default=None)
    def module_install(name, version_):
        installer.install(name, config.registry_index_url(), version=version_)
        click.echo(f"{name} instalado.")

    @module_group.command(name="update")
    @click.argument("name", required=False)
    @click.option("--all", "update_all", is_flag=True)
    def module_update(name, update_all):
        if update_all:
            for installed_name in discover_installed_modules():
                installer.install(installed_name, config.registry_index_url())
        elif name:
            installer.install(name, config.registry_index_url())
        else:
            raise click.UsageError("informe um nome de módulo ou use --all")
        click.echo("atualizado.")

    @module_group.command(name="uninstall")
    @click.argument("name")
    @click.option("--yes", is_flag=True)
    def module_uninstall(name, yes):
        if not yes:
            click.confirm(f"Remover o módulo '{name}'?", abort=True)
        installer.uninstall(name)
        click.echo(f"{name} removido.")

    return module_group


def build_cli():
    @click.group()
    @click.version_option(version=__version__, prog_name="pvx")
    def cli():
        pass

    module_group = build_module_group()
    cli.add_command(module_group)
    # aliases no root -- mesma instância de Command, sem duplicar lógica.
    # uninstall NÃO tem alias: ação destrutiva, sempre `pvx module uninstall`.
    cli.add_command(module_group.commands["install"], name="install")
    cli.add_command(module_group.commands["update"], name="update")

    @cli.command(name="logs")
    @click.argument("name")
    @click.option("--lines", type=int, default=None)
    def logs_command(name, lines):
        click.echo(viewer.read_log(name, lines=lines))

    for name, module in discover_installed_modules().items():
        cli.add_command(module.cli_group(), name=name)

    return cli


cli = build_cli()
