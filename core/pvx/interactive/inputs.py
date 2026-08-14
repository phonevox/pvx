import questionary
from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
from prompt_toolkit.keys import Keys

from pvx.interactive import theme

NAV_HINT = questionary.Separator("↑↓ navega · enter confirma · esc/ctrl-c volta")


def _cancel_on_escape(question):
    escape_binding = KeyBindings()

    @escape_binding.add(Keys.Escape, eager=True)
    def _(event):
        event.app.exit(exception=KeyboardInterrupt, style="class:aborting")

    question.application.key_bindings = merge_key_bindings(
        [question.application.key_bindings, escape_binding]
    )
    return question


def ask_select(msg, choices, default=None):
    question = questionary.select(
        msg,
        choices=list(choices) + [NAV_HINT],
        default=default,
        instruction="",
        style=theme.current_style(),
    )
    return _cancel_on_escape(question).ask()


def ask_confirm(msg, default=True):
    question = questionary.confirm(msg, default=default, style=theme.current_style())
    return _cancel_on_escape(question).ask()


def ask_text(msg, validator=None, default=None):
    question = questionary.text(
        msg, default=default or "", validate=validator, style=theme.current_style()
    )
    return _cancel_on_escape(question).ask()
