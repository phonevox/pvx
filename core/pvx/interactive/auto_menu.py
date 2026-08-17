def build_choices(group):
    return sorted(name for name, cmd in group.commands.items() if not cmd.hidden)
