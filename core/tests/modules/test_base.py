import unittest

from pvx.modules.base import PvxModule


class DummyModule(PvxModule):
    name = "dummy"
    version = "0.0.1"

    def cli_group(self):
        import click

        @click.group()
        def group():
            pass

        return group


class PvxModuleTest(unittest.TestCase):
    def test_cannot_instantiate_without_cli_group(self):
        class Incomplete(PvxModule):
            name = "incomplete"
            version = "0.0.1"

        with self.assertRaises(TypeError):
            Incomplete()

    def test_minimal_subclass_instantiates(self):
        module = DummyModule()
        self.assertEqual(module.name, "dummy")

    def test_interactive_entry_defaults_to_none(self):
        module = DummyModule()
        self.assertIsNone(module.interactive_entry())


if __name__ == "__main__":
    unittest.main()
