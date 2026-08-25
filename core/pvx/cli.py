import time

import click

from pvx import build_info, config, self_update
from pvx.interactive import widgets
from pvx.logging_ import viewer
from pvx.logging_.setup import get_module_logger
from pvx.modules import installer, listing, loader
from pvx.version import __version__


def discover_installed_modules():
    return loader.discover(config.modules_dir())


def _core_logger():
    # "core" é reservado -- get_module_logger() já garante um único handler por nome,
    # então nada de módulo instalado pode colidir com esse (nenhum nome de módulo real
    # é literalmente "core").
    return get_module_logger("core")


def build_module_group():
    @click.group(name="module")
    def module_group():
        pass

    @module_group.command(name="install")
    @click.argument("name")
    @click.option("--version", "version_", default=None)
    def module_install(name, version_):
        try:
            with widgets.spinner(f"Instalando {name}..."):
                installer.install(name, config.registry_index_url(), version=version_)
        except (RuntimeError, ValueError) as e:
            _core_logger().error(f"falha ao instalar módulo '{name}': {e}")
            raise click.ClickException(str(e))
        _core_logger().info(f"módulo '{name}' instalado (versão {version_ or 'latest'}).")
        click.echo(f"{name} instalado.")

    @module_group.command(name="update")
    @click.argument("name", required=False)
    @click.option("--all", "update_all", is_flag=True)
    def module_update(name, update_all):
        if update_all:
            names = list(discover_installed_modules())
        elif name:
            names = [name]
        else:
            raise click.UsageError("informe um nome de módulo ou use --all")

        try:
            for installed_name in names:
                with widgets.spinner(f"Atualizando {installed_name}..."):
                    installer.install(installed_name, config.registry_index_url())
                _core_logger().info(f"módulo '{installed_name}' atualizado.")
        except (RuntimeError, ValueError) as e:
            _core_logger().error(f"falha ao atualizar módulo: {e}")
            raise click.ClickException(str(e))
        click.echo("atualizado.")

    @module_group.command(name="list")
    def module_list():
        try:
            rows = listing.list_modules(discover_installed_modules(), config.registry_index_url())
        except RuntimeError as e:
            raise click.ClickException(str(e))
        widgets.print_modules_table(rows)

    @module_group.command(name="uninstall")
    @click.argument("name")
    @click.option("--yes", is_flag=True)
    def module_uninstall(name, yes):
        if not yes:
            click.confirm(f"Remover o módulo '{name}'?", abort=True)
        installer.uninstall(name)
        _core_logger().info(f"módulo '{name}' removido.")
        click.echo(f"{name} removido.")

    return module_group


def build_cli():
    channel = build_info.describe()
    version_string = f"{__version__} ({channel})" if channel else __version__

    @click.group()
    @click.version_option(version_string, "-V", "--version", prog_name="pvx")
    def cli():
        pass

    module_group = build_module_group()
    cli.add_command(module_group)
    # aliases no root -- mesma instância de Command, sem duplicar lógica.
    # uninstall NÃO tem alias: ação destrutiva, sempre `pvx module uninstall`.
    cli.add_command(module_group.commands["install"], name="install")
    cli.add_command(module_group.commands["update"], name="update")

    @cli.command(name="logs")
    @click.argument("name", required=False)
    @click.option("--tail", type=int, default=50)
    @click.option("-f", "--follow", is_flag=True)
    @click.option("-a", "--all", "show_all", is_flag=True)
    def logs_command(name, tail, follow, show_all):
        if show_all:
            names = viewer.list_log_names()
        elif name:
            names = [name]
        else:
            raise click.UsageError("informe um módulo ou use --all")

        click.echo(viewer.read_combined_logs(names, lines=tail))
        if follow:
            follower = viewer.LogFollower(names)
            try:
                while True:
                    for line in follower.poll():
                        click.echo(line)
                    time.sleep(0.5)
            except KeyboardInterrupt:
                pass

    @cli.command(name="self-update")
    def self_update_command():
        current_channel = build_info.describe()
        if current_channel is not None:
            click.confirm(
                f"Você está rodando um build {current_channel} — atualizar vai "
                "substituir pela versão oficial mais recente. Continuar?",
                abort=True,
            )
        try:
            with widgets.spinner("Baixando atualização..."):
                version = self_update.self_update()
        except PermissionError:
            _core_logger().error("self-update falhou: sem privilégios de root.")
            raise click.ClickException(
                "self-update precisa de privilégios de root (rode com sudo)."
            )
        _core_logger().info(f"pvx atualizado pra versão {version}.")
        click.echo(f"pvx atualizado pra versão {version}.")

    @cli.command(name="self-uninstall")
    @click.option("--yes", is_flag=True)
    @click.option("--purge", is_flag=True)
    def self_uninstall_command(yes, purge):
        if not yes:
            click.confirm("Remover o pvx do sistema?", abort=True)
        self_update.uninstall(purge=purge)
        _core_logger().info(f"pvx removido (purge={purge}).")
        click.echo("pvx removido.")

    for name, module in discover_installed_modules().items():
        cli.add_command(module.cli_group(), name=name)

    return cli


cli = build_cli()
