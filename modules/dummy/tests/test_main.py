import unittest

from click.testing import CliRunner

from src.main import cli as dummy_module


class DummyModuleTest(unittest.TestCase):
    def test_cli_group_has_hello_command(self):
        result = CliRunner().invoke(dummy_module.cli_group(), ["hello"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("hello", result.output.lower())


if __name__ == "__main__":
    unittest.main()
