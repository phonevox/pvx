class Router:
    def __init__(self, registry):
        self.registry = registry
        self.stack = []

    def run(self, start_screen_name):
        self.stack = [self.registry[start_screen_name]()]
        while self.stack:
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
    from pvx.interactive.screens.root import RootScreen

    Router({"root": RootScreen}).run("root")
