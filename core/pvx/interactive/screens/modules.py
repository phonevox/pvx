from pvx.interactive.inputs import ask_select

CHOICES = ["Instalar", "Atualizar", "Remover", "Listar", "Voltar"]

SCREEN_BY_CHOICE = {
    "Instalar": "modules.install",
    "Atualizar": "modules.update",
    "Remover": "modules.uninstall",
    "Listar": "modules.list",
}


class ModulesScreen:
    def render(self):
        selected = ask_select("pvx > módulos >", CHOICES)
        if selected is None or selected == "Voltar":
            return "BACK"
        return SCREEN_BY_CHOICE[selected]
