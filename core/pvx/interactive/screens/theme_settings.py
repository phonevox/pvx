from pvx import config
from pvx.interactive.inputs import ask_select
from pvx.interactive.theme import PRESETS

LABELS = {name: name for name in PRESETS}


class ThemeScreen:
    def render(self):
        selected = ask_select("pvx > tema >", list(LABELS.values()) + ["voltar"])
        if selected is None or selected == "voltar":
            return "BACK"

        name = next(key for key, label in LABELS.items() if label == selected)
        config.set_theme_name(name)
        return "BACK"
