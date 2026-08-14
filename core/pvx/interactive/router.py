from pvx.interactive import widgets


class Router:
    def __init__(self, registry):
        self.registry = registry
        self.stack = []

    def run(self, start_screen_name):
        self.stack = [self.registry[start_screen_name]()]
        while self.stack:
            widgets.clear()
            result = self.stack[-1].render()
            if result is None:
                continue
            if result == "EXIT":
                self.stack = []
                break
            if result == "BACK":
                self.stack.pop()
                continue
            self.stack.append(self.registry[result]())


def run_interactive():
    from pvx.interactive.screens.logs import LogsScreen
    from pvx.interactive.screens.module_install import ModuleInstallScreen
    from pvx.interactive.screens.module_uninstall import ModuleUninstallScreen
    from pvx.interactive.screens.module_update import ModuleUpdateScreen
    from pvx.interactive.screens.modules import ModulesScreen
    from pvx.interactive.screens.root import RootScreen
    from pvx.interactive.screens.theme_settings import ThemeScreen

    registry = {
        "root": RootScreen,
        "modules": ModulesScreen,
        "modules.install": ModuleInstallScreen,
        "modules.update": ModuleUpdateScreen,
        "modules.uninstall": ModuleUninstallScreen,
        "logs": LogsScreen,
        "theme": ThemeScreen,
    }
    Router(registry).run("root")
