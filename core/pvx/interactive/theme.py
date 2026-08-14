import questionary

from pvx import config

ACCENT_COLORS = {
    "azul": "#0087ff",
    "verde": "#00af5f",
    "roxo": "#af5fff",
    "laranja": "#ff8700",
}

SEPARATOR_COLOR = "#808080"


def _rules_for(accent):
    return [
        ("pointer", f"fg:{accent} bold"),
        ("highlighted", f"fg:{accent} bold"),
        ("answer", f"fg:{accent} bold"),
        ("separator", f"fg:{SEPARATOR_COLOR}"),
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
