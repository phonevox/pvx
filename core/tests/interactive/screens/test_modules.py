import unittest
from unittest.mock import patch

from pvx.interactive.screens.modules import ModulesScreen


class ModulesScreenTest(unittest.TestCase):
    @patch("pvx.interactive.screens.modules.ask_select", return_value="Instalar")
    def test_selecting_instalar_pushes_install_screen(self, mock_ask_select):
        self.assertEqual(ModulesScreen().render(), "modules.install")

    @patch("pvx.interactive.screens.modules.ask_select", return_value="Atualizar")
    def test_selecting_atualizar_pushes_update_screen(self, mock_ask_select):
        self.assertEqual(ModulesScreen().render(), "modules.update")

    @patch("pvx.interactive.screens.modules.ask_select", return_value="Remover")
    def test_selecting_remover_pushes_uninstall_screen(self, mock_ask_select):
        self.assertEqual(ModulesScreen().render(), "modules.uninstall")

    @patch("pvx.interactive.screens.modules.ask_select", return_value="Voltar")
    def test_selecting_voltar_returns_back(self, mock_ask_select):
        self.assertEqual(ModulesScreen().render(), "BACK")

    @patch("pvx.interactive.screens.modules.ask_select", return_value=None)
    def test_none_selection_returns_back(self, mock_ask_select):
        self.assertEqual(ModulesScreen().render(), "BACK")


if __name__ == "__main__":
    unittest.main()
