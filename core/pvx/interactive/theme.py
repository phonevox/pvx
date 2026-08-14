import questionary

from pvx import config

PRESETS = {
    "azul": [
        ("pointer", "fg:#0087ff bold"),
        ("highlighted", "fg:#0087ff bold"),
        ("separator", "fg:#808080"),
    ],
    "verde": [
        ("pointer", "fg:#00af5f bold"),
        ("highlighted", "fg:#00af5f bold"),
        ("separator", "fg:#808080"),
    ],
    "roxo": [
        ("pointer", "fg:#af5fff bold"),
        ("highlighted", "fg:#af5fff bold"),
        ("separator", "fg:#808080"),
    ],
    "laranja": [
        ("pointer", "fg:#ff8700 bold"),
        ("highlighted", "fg:#ff8700 bold"),
        ("separator", "fg:#808080"),
    ],
}

THEME_RULES = PRESETS["azul"]
THEME = questionary.Style(THEME_RULES)


def current_theme_rules():
    return PRESETS.get(config.get_theme_name(), PRESETS["azul"])


def current_style():
    return questionary.Style(current_theme_rules())
