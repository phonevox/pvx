import click

from pvx import config
from pvx.cli import discover_installed_modules
from pvx.interactive import widgets
from pvx.modules import listing


class ModuleListScreen:
    def render(self):
        try:
            with widgets.spinner("Carregando módulos..."):
                rows = listing.list_modules(discover_installed_modules(), config.registry_index_url())
        except RuntimeError as e:
            # print_module_list() (chamado só no caminho feliz) já cobre o
            # header -- na falha, nada foi carregado, então o breadcrumb aqui
            # é o único jeito de saber onde isso aconteceu.
            widgets.breadcrumb("pvx > módulos > listar")
            widgets.message(str(e))
            widgets.pause()
            return "BACK"

        widgets.print_module_list(rows)
        click.echo()
        widgets.pause()
        return "BACK"
