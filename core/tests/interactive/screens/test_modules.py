import unittest
from unittest.mock import patch

from pvx.interactive.screens.modules import CHOICES, ModulesScreen


class ChoicesHaveDescriptionsTest(unittest.TestCase):
    def test_every_choice_has_a_non_empty_description(self):
        for choice in CHOICES:
            self.assertTrue(choice.description, msg=f"{choice.value} sem description")


class ModulesScreenTest(unittest.TestCase):
    @patch("pvx.interactive.screens.modules.ask_select", return_value="instalar")
    def test_selecting_instalar_pushes_install_screen(self, mock_ask_select):
        self.assertEqual(ModulesScreen().render(), "modules.install")

    @patch("pvx.interactive.screens.modules.ask_select", return_value="atualizar")
    def test_selecting_atualizar_pushes_update_screen(self, mock_ask_select):
        self.assertEqual(ModulesScreen().render(), "modules.update")

    @patch("pvx.interactive.screens.modules.ask_select", return_value="remover")
    def test_selecting_remover_pushes_uninstall_screen(self, mock_ask_select):
        self.assertEqual(ModulesScreen().render(), "modules.uninstall")

    @patch("pvx.interactive.screens.modules.ask_select", return_value="listar")
    def test_selecting_listar_pushes_list_screen(self, mock_ask_select):
        self.assertEqual(ModulesScreen().render(), "modules.list")

    @patch("pvx.interactive.screens.modules.ask_select", return_value="voltar")
    def test_selecting_voltar_returns_back(self, mock_ask_select):
        self.assertEqual(ModulesScreen().render(), "BACK")

    @patch("pvx.interactive.screens.modules.ask_select", return_value=None)
    def test_none_selection_returns_back(self, mock_ask_select):
        self.assertEqual(ModulesScreen().render(), "BACK")


if __name__ == "__main__":
    unittest.main()
