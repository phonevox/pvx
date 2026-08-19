import questionary

from pvx import config

ACCENT_COLORS = {
    "azul": "#0087ff",
    "verde": "#00af5f",
    "roxo": "#af5fff",
    "laranja": "#ff8700",
    "vermelho": "#ff5555",
    "amarelo": "#ffd700",
    "ciano": "#00d7ff",
    "rosa": "#ff5fd7",
}

SEPARATOR_COLOR = "#808080"


def _rules_for(accent):
    return [
        ("pointer", f"fg:{accent} bold"),
        ("highlighted", f"fg:{accent} bold"),
        ("answer", f"fg:{accent} bold"),
        ("separator", f"fg:{SEPARATOR_COLOR}"),
        # prompt_toolkit.styles.defaults tem um "selected" embutido = "reverse" (inverte
        # fundo/texto do item marcado num checkbox), numa camada abaixo do style do
        # questionary. Merge de style é por atributo -- só não mencionar "reverse" aqui
        # não cancela o que essa camada de baixo já setou, precisa de "noreverse" explícito.
        ("selected", f"noreverse fg:{accent} bold"),
    ]


PRESETS = {name: _rules_for(accent) for name, accent in ACCENT_COLORS.items()}

THEME_RULES = PRESETS["azul"]
THEME = questionary.Style(THEME_RULES)


def current_theme_rules():
    return PRESETS.get(config.get_theme_name(), PRESETS["azul"])


def current_style():
    return questionary.Style(current_theme_rules())


def current_accent_color():
    return ACCENT_COLORS.get(config.get_theme_name(), ACCENT_COLORS["azul"])
