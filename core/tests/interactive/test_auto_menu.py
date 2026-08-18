import unittest

import click

from pvx.interactive.auto_menu import build_choices


class BuildChoicesTest(unittest.TestCase):
    def test_returns_command_names_from_group(self):
        @click.group()
        def group():
            pass

        @group.command()
        def hello():
            pass

        @group.command()
        def bye():
            pass

        self.assertEqual(build_choices(group), ["bye", "hello"])

    def test_excludes_hidden_commands(self):
        @click.group()
        def group():
            pass

        @group.command()
        def hello():
            pass

        @group.command(hidden=True)
        def prepare():
            pass

        self.assertEqual(build_choices(group), ["hello"])


if __name__ == "__main__":
    unittest.main()
