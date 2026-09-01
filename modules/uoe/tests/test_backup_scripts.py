import unittest

import backup_scripts


class BuildCommandTest(unittest.TestCase):
    def test_issabel_command_defaults_to_config_only(self):
        result = backup_scripts.build_command("issabel", token="eyJhbGc", pbackup_root="/root/pbackup")
        self.assertEqual(
            result,
            "bash /root/pbackup/scripts/issabel.sh --configuration "
            "-t http://uoe.interno.falevox.com.br/v1/upload:/ --token eyJhbGc",
        )

    def test_issabel_command_with_recordings(self):
        result = backup_scripts.build_command(
            "issabel", token="eyJhbGc", pbackup_root="/root/pbackup", issabel_recordings=True,
        )
        self.assertEqual(
            result,
            "bash /root/pbackup/scripts/issabel.sh --recordings --configuration "
            "-t http://uoe.interno.falevox.com.br/v1/upload:/ --token eyJhbGc",
        )

    def test_magnus_command(self):
        result = backup_scripts.build_command("magnus", token="eyJhbGc", pbackup_root="/opt/pbackup")
        self.assertEqual(
            result,
            "bash /opt/pbackup/scripts/magnus.sh -t http://uoe.interno.falevox.com.br/v1/upload:/ --token eyJhbGc",
        )

    def test_custom_command_substitutes_the_placeholder(self):
        result = backup_scripts.build_command(
            "custom", token="eyJhbGc", custom_template="/opt/meuscript.sh --upload --token {TOKEN} --verbose",
        )
        self.assertEqual(result, "/opt/meuscript.sh --upload --token eyJhbGc --verbose")

    def test_custom_without_placeholder_raises(self):
        # Q5 do design: {TOKEN} é obrigatório -- sem ele o relogin não teria como
        # saber onde trocar o token depois.
        with self.assertRaises(ValueError):
            backup_scripts.build_command("custom", token="eyJhbGc", custom_template="/opt/meuscript.sh --upload")

    def test_unknown_script_raises(self):
        with self.assertRaises(ValueError):
            backup_scripts.build_command("unknown", token="eyJhbGc")


if __name__ == "__main__":
    unittest.main()
