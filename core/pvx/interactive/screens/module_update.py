from pvx import config
from pvx.cli import discover_installed_modules
from pvx.interactive import widgets
from pvx.interactive.inputs import ask_select
from pvx.modules import installer


class ModuleUpdateScreen:
    def render(self):
        modules = discover_installed_modules()
        if not modules:
            widgets.breadcrumb("pvx > módulos > atualizar")
            widgets.message("nenhum módulo instalado.")
            widgets.pause()
            return "BACK"

        selected = ask_select(
            "pvx > módulos > atualizar >", list(modules.keys()) + ["todos", "voltar"]
        )
        if selected is None or selected == "voltar":
            return "BACK"

        names = list(modules) if selected == "todos" else [selected]
        for name in names:
            try:
                with widgets.spinner(f"Atualizando {name}..."):
                    installer.install(name, config.registry_index_url())
            except (RuntimeError, ValueError) as e:
                widgets.failed(str(e))
            else:
                widgets.success(f"{name} atualizado.")

        widgets.pause()
        return "BACK"
