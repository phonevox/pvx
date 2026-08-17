import questionary
from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
from prompt_toolkit.keys import Keys

from pvx.interactive import theme

NAV_HINT = questionary.Separator("↑↓ navega · enter confirma · esc/q volta · ctrl-c fecha o pvx")

_BACK = object()


def _ask(question, include_q=False):
    back_binding = KeyBindings()

    @back_binding.add(Keys.Escape, eager=True)
    def _(event):
        event.app.exit(result=_BACK)

    if include_q:
        @back_binding.add("q", eager=True)
        def _(event):
            event.app.exit(result=_BACK)

    question.application.key_bindings = merge_key_bindings(
        [question.application.key_bindings, back_binding]
    )

    # unsafe_ask(): não engole KeyboardInterrupt (Ctrl-C) -- questionary
    # trataria como "cancelado" igual o Esc; aqui precisa propagar pra
    # fechar o pvx inteiro, não só voltar uma tela.
    result = question.unsafe_ask()
    return None if result is _BACK else result


def ask_select(msg, choices, default=None):
    question = questionary.select(
        msg,
        choices=list(choices) + [NAV_HINT],
        default=default,
        instruction="",
        style=theme.current_style(),
    )
    return _ask(question, include_q=True)


def ask_checkbox(msg, choices, defaults=None):
    defaults = defaults or []
    wrapped = [questionary.Choice(title=str(c), value=c, checked=c in defaults) for c in choices]
    question = questionary.checkbox(msg, choices=wrapped, style=theme.current_style())
    return _ask(question)


def ask_confirm(msg, default=True):
    question = questionary.confirm(msg, default=default, style=theme.current_style())
    return _ask(question, include_q=True)


def ask_text(msg, validator=None, default=None):
    question = questionary.text(
        msg, default=default or "", validate=validator, style=theme.current_style()
    )
    return _ask(question)
