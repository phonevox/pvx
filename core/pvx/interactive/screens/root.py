import questionary

from pvx.cli import discover_installed_modules
from pvx.interactive import widgets
from pvx.interactive.auto_menu import build_choices
from pvx.interactive.inputs import ask_select

SCREEN_BY_SYSTEM_CHOICE = {"Módulos": "modules", "Logs": "logs", "Tema": "theme"}


class RootScreen:
    def render(self):
        widgets.banner()
        modules = discover_installed_modules()

        def indented(value):
            return questionary.Choice(title=f"  {value}", value=value)

        choices = [questionary.Separator("SYSTEM"), *(indented(c) for c in SCREEN_BY_SYSTEM_CHOICE)]
        if modules:
            choices += [questionary.Separator("MODULES"), *(indented(name) for name in modules)]
        choices += [questionary.Separator(), "Sair"]

        selected = ask_select("pvx >", choices)
        if selected is None or selected == "Sair":
            return "EXIT"

        if selected in SCREEN_BY_SYSTEM_CHOICE:
            return SCREEN_BY_SYSTEM_CHOICE[selected]

        module = modules[selected]
        if module.interactive_entry() is not None:
            return f"{selected}.main"

        group = module.cli_group()
        command_name = ask_select(f"pvx > {selected} >", build_choices(group))
        if command_name is not None:
            group.commands[command_name].main(args=[], standalone_mode=False)
        return None
