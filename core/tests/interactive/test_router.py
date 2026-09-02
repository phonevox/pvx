import unittest
from unittest.mock import patch

import click

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


class RouterCrashTest(unittest.TestCase):
    # achado ao vivo: uma tela (ex.: ModuleInstallScreen) estourando qualquer
    # exceção não tratada no próprio render() (não num comando de módulo, que
    # já tem seu próprio guard) derrubava a sessão inteira -- Router.run()
    # nunca teve try/except nenhum ao redor do render().
    @patch("pvx.interactive.router.widgets.pause")
    @patch("pvx.interactive.router.widgets.crash")
    def test_screen_crash_shows_crash_and_pops_back_instead_of_killing_the_session(
        self, mock_crash, mock_pause
    ):
        calls = []

        class RootScreen:
            def __init__(self):
                self._returns = iter(["broken", "EXIT"])

            def render(self):
                calls.append("root")
                return next(self._returns)

        class BrokenScreen:
            def render(self):
                raise RuntimeError("algo quebrou de verdade")

        router = Router({"root": RootScreen, "broken": BrokenScreen})
        router.run("root")

        self.assertEqual(calls, ["root", "root"])
        self.assertEqual(router.stack, [])
        mock_crash.assert_called_once()
        self.assertIn("algo quebrou de verdade", mock_crash.call_args.args[0])
        mock_pause.assert_called_once()

    @patch("pvx.interactive.router.widgets.pause")
    @patch("pvx.interactive.router.widgets.crash")
    def test_crash_on_the_root_screen_itself_ends_the_session_cleanly(self, mock_crash, mock_pause):
        class BrokenRootScreen:
            def render(self):
                raise RuntimeError("boom")

        router = Router({"root": BrokenRootScreen})
        router.run("root")  # não deve levantar

        self.assertEqual(router.stack, [])
        mock_crash.assert_called_once()


class RouterAbortTest(unittest.TestCase):
    # ctrl-c num prompt (ask_password/ask_text) vira click.exceptions.Abort
    # (via cmd.main() do click, dentro do auto-menu) -- precisa fechar o pvx
    # inteiro, não ser tratado como "tela crashou" (senão fica preso
    # mostrando traceback + voltando pro nível anterior em vez de sair).
    @patch("pvx.interactive.router.widgets.crash")
    def test_abort_propagates_instead_of_being_shown_as_a_crash(self, mock_crash):
        class RootScreen:
            def render(self):
                raise click.exceptions.Abort()

        router = Router({"root": RootScreen})
        with self.assertRaises(click.exceptions.Abort):
            router.run("root")
        mock_crash.assert_not_called()


if __name__ == "__main__":
    unittest.main()
