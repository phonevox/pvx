import questionary

from pvx.interactive.inputs import ask_select

SCREEN_BY_CHOICE = {
    "instalar": "modules.install",
    "atualizar": "modules.update",
    "remover": "modules.uninstall",
    "listar": "modules.list",
}

_DESCRIPTIONS = {
    "instalar": "baixa e instala um módulo do registry (ou de outra URL)",
    "atualizar": "atualiza um módulo (ou todos) pra última versão do registry",
    "remover": "desinstala um módulo",
    "listar": "mostra versão instalada x disponível de cada módulo",
    "voltar": "volta pro menu anterior",
}

CHOICES = [
    questionary.Choice(name, description=description)
    for name, description in _DESCRIPTIONS.items()
]


class ModulesScreen:
    def render(self):
        selected = ask_select("pvx > módulos >", CHOICES)
        if selected is None or selected == "voltar":
            return "BACK"
        return SCREEN_BY_CHOICE[selected]
