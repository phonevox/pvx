from pvx import config
from pvx.interactive.inputs import ask_select, ask_text
from pvx.modules import installer

SOURCES = ["Registry oficial", "Outro repositório (URL)", "Voltar"]


class ModuleInstallScreen:
    def render(self):
        source = ask_select("pvx > módulos > instalar >", SOURCES)
        if source is None or source == "Voltar":
            return "BACK"

        if source == "Outro repositório (URL)":
            index_url = ask_text("URL do index.json:")
        else:
            index_url = config.registry_index_url()

        name = ask_text("Nome do módulo:")
        installer.install(name, index_url)

        return "BACK"
