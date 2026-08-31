import unittest
from unittest.mock import MagicMock, patch

import os_ops


def _run_result(returncode=0):
    return MagicMock(returncode=returncode)


class RunCmdTest(unittest.TestCase):
    @patch("os_ops.subprocess.run")
    def test_delegates_to_subprocess_run(self, mock_run):
        mock_run.return_value = _run_result(returncode=0)
        result = os_ops.run_cmd(["dnf", "install", "-y", "zabbix-agent2"])
        self.assertTrue(result)
        mock_run.assert_called_once_with(
            ["dnf", "install", "-y", "zabbix-agent2"], capture_output=True, text=True
        )

    @patch("os_ops.subprocess.run")
    def test_false_on_nonzero_exit(self, mock_run):
        mock_run.return_value = _run_result(returncode=1)
        self.assertFalse(os_ops.run_cmd(["false"]))

    @patch("os_ops.subprocess.run", side_effect=FileNotFoundError())
    def test_false_when_the_executable_does_not_exist(self, mock_run):
        self.assertFalse(os_ops.run_cmd(["does-not-exist"]))


if __name__ == "__main__":
    unittest.main()
