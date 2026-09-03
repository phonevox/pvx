import questionary

# default do click (45) corta frase curta no meio -- a maioria das
# descrições reais dos módulos passa disso. 100 cobre praticamente tudo sem
# deixar a linha gigante.
_DESCRIPTION_LIMIT = 100


def build_choices(group):
    names = sorted(name for name, cmd in group.commands.items() if not cmd.hidden)
    return [
        questionary.Choice(
            name, description=group.commands[name].get_short_help_str(_DESCRIPTION_LIMIT) or None,
        )
        for name in names
    ]
