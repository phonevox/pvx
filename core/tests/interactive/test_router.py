import unittest
from unittest.mock import patch

from pvx.interactive.router import Router


class RouterTest(unittest.TestCase):
    def test_push_then_back_returns_to_previous_screen(self):
        calls = []

        class RootScreen:
            def __init__(self):
                self._returns = iter(["modules", "EXIT"])

            def render(self):
                calls.append("root")
                return next(self._returns)

        class ModulesScreen:
            def __init__(self):
                self._returns = iter(["BACK"])

            def render(self):
                calls.append("modules")
                return next(self._returns)

        router = Router({"root": RootScreen, "modules": ModulesScreen})
        router.run("root")

        self.assertEqual(calls, ["root", "modules", "root"])
        self.assertEqual(router.stack, [])

    def test_none_redraws_same_screen_without_navigating(self):
        calls = []

        class RootScreen:
            def __init__(self):
                self._returns = iter([None, "EXIT"])

            def render(self):
                calls.append("root")
                return next(self._returns)

        router = Router({"root": RootScreen})
        router.run("root")

        self.assertEqual(calls, ["root", "root"])
        self.assertEqual(router.stack, [])

    @patch("pvx.interactive.router.widgets.clear")
    def test_clears_screen_before_every_render(self, mock_clear):
        class RootScreen:
            def __init__(self):
                self._returns = iter(["modules", "EXIT"])

            def render(self):
                return next(self._returns)

        class ModulesScreen:
            def __init__(self):
                self._returns = iter(["BACK"])

            def render(self):
                return next(self._returns)

        router = Router({"root": RootScreen, "modules": ModulesScreen})
        router.run("root")

        self.assertEqual(mock_clear.call_count, 3)


if __name__ == "__main__":
    unittest.main()
