from pvx.cli import discover_installed_modules
from pvx.interactive.auto_menu import build_choices
from pvx.interactive.inputs import ask_select


class RootScreen:
    def render(self):
        modules = discover_installed_modules()
        selected = ask_select("pvx >", list(modules.keys()) + ["Sair"])
        if selected is None or selected == "Sair":
            return "EXIT"

        module = modules[selected]
        if module.interactive_entry() is not None:
            return f"{selected}.main"

        group = module.cli_group()
        command_name = ask_select(f"pvx > {selected} >", build_choices(group))
        if command_name is not None:
            group.commands[command_name].main(args=[], standalone_mode=False)
        return None
