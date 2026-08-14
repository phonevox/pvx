import click

from pvx import config
from pvx.cli import discover_installed_modules
from pvx.interactive import widgets
from pvx.interactive.inputs import ask_select
from pvx.modules import installer


class ModuleUpdateScreen:
    def render(self):
        modules = discover_installed_modules()
        selected = ask_select(
            "pvx > módulos > atualizar >", list(modules.keys()) + ["Todos", "Voltar"]
        )
        if selected is None or selected == "Voltar":
            return "BACK"

        names = list(modules) if selected == "Todos" else [selected]
        for name in names:
            try:
                with widgets.spinner(f"Atualizando {name}..."):
                    installer.install(name, config.registry_index_url())
            except (RuntimeError, ValueError) as e:
                click.echo(str(e))

        return "BACK"
