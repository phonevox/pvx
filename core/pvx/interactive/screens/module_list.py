import click

from pvx import config
from pvx.cli import discover_installed_modules
from pvx.interactive import widgets
from pvx.modules import listing


class ModuleListScreen:
    def render(self):
        widgets.breadcrumb("pvx > módulos > listar >")

        try:
            with widgets.spinner("Carregando módulos..."):
                rows = listing.list_modules(discover_installed_modules(), config.registry_index_url())
        except RuntimeError as e:
            click.echo(str(e))
            widgets.pause("pressione enter pra continuar...")
            return "BACK"

        widgets.print_modules_table(rows)
        widgets.pause("pressione enter pra continuar...")
        return "BACK"
