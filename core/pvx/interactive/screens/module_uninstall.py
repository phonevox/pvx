from pvx.cli import discover_installed_modules
from pvx.interactive import widgets
from pvx.interactive.inputs import ask_confirm, ask_select
from pvx.modules import installer


class ModuleUninstallScreen:
    def render(self):
        modules = discover_installed_modules()
        if not modules:
            widgets.breadcrumb("pvx > módulos > remover")
            widgets.message("nenhum módulo instalado.")
            widgets.pause()
            return "BACK"

        selected = ask_select("pvx > módulos > remover >", list(modules.keys()) + ["Voltar"])
        if selected is None or selected == "Voltar":
            return "BACK"

        if ask_confirm(f"Remover o módulo '{selected}'?", default=False):
            installer.uninstall(selected)
            widgets.message(f"{selected} removido.")
            widgets.pause()

        return "BACK"
