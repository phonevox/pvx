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

        self.assertEqual([c.value for c in build_choices(group)], ["bye", "hello"])

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

        self.assertEqual([c.value for c in build_choices(group)], ["hello"])

    def test_carries_the_command_help_as_description(self):
        @click.group()
        def group():
            pass

        @group.command(help="instala o troço todo.")
        def install():
            pass

        choice = build_choices(group)[0]
        self.assertEqual(choice.description, "instala o troço todo.")

    def test_no_description_when_command_has_no_help(self):
        @click.group()
        def group():
            pass

        @group.command()
        def install():
            pass

        choice = build_choices(group)[0]
        self.assertFalse(choice.description)

    def test_long_help_is_shortened(self):
        @click.group()
        def group():
            pass

        long_help = "a" * 250

        @group.command(help=long_help)
        def install():
            pass

        choice = build_choices(group)[0]
        self.assertLess(len(choice.description), 250)


if __name__ == "__main__":
    unittest.main()
