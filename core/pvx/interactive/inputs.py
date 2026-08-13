import questionary


def ask_select(msg, choices, default=None):
    return questionary.select(msg, choices=choices, default=default).ask()
