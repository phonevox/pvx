import questionary

from pvx.cli import discover_installed_modules
from pvx.interactive.auto_menu import build_choices
from pvx.interactive.inputs import ask_select

SCREEN_BY_SYSTEM_CHOICE = {"Módulos": "modules", "Logs": "logs", "Tema": "theme"}


class RootScreen:
    def render(self):
        modules = discover_installed_modules()

        choices = [questionary.Separator("SYSTEM"), *SCREEN_BY_SYSTEM_CHOICE]
        if modules:
            choices += [questionary.Separator("MODULES"), *modules.keys()]
        choices.append("Sair")

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
