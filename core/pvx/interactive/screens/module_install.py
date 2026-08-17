import click

from pvx import config
from pvx.cli import discover_installed_modules
from pvx.interactive import widgets
from pvx.interactive.inputs import ask_checkbox, ask_select, ask_text
from pvx.modules import installer, listing

SOURCES = ["Registry oficial", "Outro repositório (URL)", "Voltar"]


class ModuleInstallScreen:
    def render(self):
        source = ask_select("pvx > módulos > instalar >", SOURCES)
        if source is None or source == "Voltar":
            return "BACK"

        if source == "Outro repositório (URL)":
            index_url = ask_text("URL do index.json:")
            if index_url is None:
                return "BACK"
        else:
            index_url = config.registry_index_url()

        try:
            rows = listing.list_modules(discover_installed_modules(), index_url)
        except RuntimeError as e:
            click.echo(str(e))
            return "BACK"

        names = [row["name"] for row in rows]
        if not names:
            click.echo("nenhum módulo disponível nesse registry.")
            return "BACK"

        selected_names = ask_checkbox("Selecione os módulos pra instalar:", names)
        if not selected_names:
            return "BACK"

        for name in selected_names:
            try:
                with widgets.spinner(f"Instalando {name}..."):
                    installer.install(name, index_url)
            except (RuntimeError, ValueError) as e:
                click.echo(str(e))

        return "BACK"
