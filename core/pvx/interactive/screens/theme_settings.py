import questionary

from pvx import config
from pvx.interactive import widgets
from pvx.interactive.inputs import ask_select
from pvx.interactive.theme import ACCENT_COLORS, BORDERS, LINE_FORMATS, PRESETS, SYMBOL_SETS


def _color_preview(name):
    return f"cor: {ACCENT_COLORS[name]}"


def _symbol_preview(name):
    s = SYMBOL_SETS[name]
    return f"aviso {s['warning']} aviso!  ·  seção {s['section']} título  ·  item {s['item']} texto"


def _border_preview(name):
    return BORDERS[name] * 24


def _format_preview(name):
    return widgets.preview_outcome_line(name, "✓", "sucesso")


# (presets, nome do setter em config, preview por preset, descrição do eixo) --
# nome do setter (não a função em si) resolvido via getattr(config, ...) na hora
# de chamar: guardar a referência direta congelaria o mock de teste no valor lido
# no import do módulo, antes do @patch de config.<setter> agir.
_AXES = {
    "cor": (PRESETS, "set_theme_name", _color_preview, "cor de destaque usada em título, seção e item"),
    "símbolos": (SYMBOL_SETS, "set_symbol_set_name", _symbol_preview, "glifos de aviso, seção e item"),
    "moldura": (BORDERS, "set_border_name", _border_preview, "caractere da moldura do título"),
    "formato": (LINE_FORMATS, "set_line_format_name", _format_preview, "layout de sucesso/falha/aviso"),
}


def _choice(value, description):
    return questionary.Choice(title=value, value=value, description=description)


class ThemeScreen:
    def render(self):
        axis_choices = [_choice(axis, desc) for axis, (_, _, _, desc) in _AXES.items()] + ["voltar"]
        axis = ask_select("pvx > tema >", axis_choices)
        if axis is None or axis == "voltar":
            return "BACK"

        presets, setter_name, preview, _ = _AXES[axis]
        # sem isso, a pergunta do eixo (já respondida) fica presa na tela e a
        # pergunta do preset aparece duplicada embaixo -- achado ao vivo.
        widgets.clear()
        preset_choices = [_choice(name, preview(name)) for name in presets] + ["voltar"]
        selected = ask_select(f"pvx > tema > {axis} >", preset_choices)
        if selected is None or selected == "voltar":
            return None

        getattr(config, setter_name)(selected)
        return None
