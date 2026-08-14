import questionary


def ask_select(msg, choices, default=None):
    return questionary.select(msg, choices=choices, default=default).ask()


def ask_confirm(msg, default=True):
    return questionary.confirm(msg, default=default).ask()


def ask_text(msg, validator=None, default=None):
    return questionary.text(msg, default=default or "", validate=validator).ask()
