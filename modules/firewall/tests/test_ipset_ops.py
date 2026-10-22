import unittest
from unittest.mock import MagicMock, patch

import ipset_ops


def _run_result(stdout="", returncode=0):
    return MagicMock(stdout=stdout, returncode=returncode)


class AvailableTest(unittest.TestCase):
    @patch("ipset_ops.shutil.which", return_value="/usr/sbin/ipset")
    def test_true_when_binary_found(self, mock_which):
        self.assertTrue(ipset_ops.available())

    @patch("ipset_ops.shutil.which", return_value=None)
    def test_false_when_binary_missing(self, mock_which):
        self.assertFalse(ipset_ops.available())


class ExistsTest(unittest.TestCase):
    @patch("ipset_ops.subprocess.run")
    def test_true_when_listing_succeeds(self, mock_run):
        mock_run.return_value = _run_result(returncode=0)
        self.assertTrue(ipset_ops.exists("pvx-geo"))

    @patch("ipset_ops.subprocess.run")
    def test_false_when_listing_fails(self, mock_run):
        mock_run.return_value = _run_result(returncode=1)
        self.assertFalse(ipset_ops.exists("pvx-geo"))


class CreateDestroyTest(unittest.TestCase):
    @patch("ipset_ops.exists", return_value=False)
    @patch("ipset_ops.subprocess.run")
    def test_creates_when_absent(self, mock_run, mock_exists):
        ipset_ops.create("pvx-geo")
        mock_run.assert_called_once_with(
            ["ipset", "create", "pvx-geo", "hash:net"], capture_output=True, text=True, check=False,
        )

    @patch("ipset_ops.exists", return_value=True)
    @patch("ipset_ops.subprocess.run")
    def test_skips_create_when_already_present(self, mock_run, mock_exists):
        ipset_ops.create("pvx-geo")
        mock_run.assert_not_called()

    @patch("ipset_ops.exists", return_value=True)
    @patch("ipset_ops.subprocess.run")
    def test_destroys_when_present(self, mock_run, mock_exists):
        ipset_ops.destroy("pvx-geo")
        mock_run.assert_called_once_with(
            ["ipset", "destroy", "pvx-geo"], capture_output=True, text=True, check=False,
        )

    @patch("ipset_ops.exists", return_value=False)
    @patch("ipset_ops.subprocess.run")
    def test_skips_destroy_when_absent(self, mock_run, mock_exists):
        ipset_ops.destroy("pvx-geo")
        mock_run.assert_not_called()


class AddTest(unittest.TestCase):
    @patch("ipset_ops.subprocess.run")
    def test_add_is_idempotent_via_exist_flag(self, mock_run):
        ipset_ops.add("pvx-geo", "1.2.3.0/24")
        mock_run.assert_called_once_with(
            ["ipset", "add", "pvx-geo", "1.2.3.0/24", "-exist"], capture_output=True, text=True, check=False,
        )


class AddManyTest(unittest.TestCase):
    @patch("ipset_ops.subprocess.run")
    def test_loads_all_cidrs_in_a_single_restore_call(self, mock_run):
        mock_run.return_value = _run_result()
        ipset_ops.add_many("pvx-geo-new", ["1.2.3.0/24", "5.6.7.0/24"])
        mock_run.assert_called_once_with(
            ["ipset", "restore", "-exist"],
            input="add pvx-geo-new 1.2.3.0/24\nadd pvx-geo-new 5.6.7.0/24\n",
            capture_output=True, text=True, check=False,
        )

    @patch("ipset_ops.subprocess.run")
    def test_raises_with_stderr_when_restore_fails(self, mock_run):
        mock_run.return_value = _run_result(returncode=1)
        mock_run.return_value.stderr = "ipset v7: Hash is full"
        with self.assertRaisesRegex(RuntimeError, "Hash is full"):
            ipset_ops.add_many("pvx-geo-new", ["1.2.3.0/24"])


class MembersTest(unittest.TestCase):
    @patch("ipset_ops.subprocess.run")
    def test_parses_members_after_the_header(self, mock_run):
        mock_run.return_value = _run_result(stdout=(
            "Name: pvx-geo\n"
            "Type: hash:net\n"
            "Members:\n"
            "1.2.3.0/24\n"
            "5.6.7.0/24\n"
        ), returncode=0)
        self.assertEqual(ipset_ops.members("pvx-geo"), ["1.2.3.0/24", "5.6.7.0/24"])

    @patch("ipset_ops.subprocess.run")
    def test_empty_when_set_does_not_exist(self, mock_run):
        mock_run.return_value = _run_result(returncode=1)
        self.assertEqual(ipset_ops.members("pvx-geo"), [])


class SwapTest(unittest.TestCase):
    @patch("ipset_ops.destroy")
    @patch("ipset_ops.subprocess.run")
    def test_swaps_then_destroys_the_temp_set(self, mock_run, mock_destroy):
        ipset_ops.swap("pvx-geo-new", "pvx-geo")
        mock_run.assert_called_once_with(
            ["ipset", "swap", "pvx-geo-new", "pvx-geo"], capture_output=True, text=True, check=False,
        )
        mock_destroy.assert_called_once_with("pvx-geo-new")


class ReplaceMembersTest(unittest.TestCase):
    @patch("ipset_ops.swap")
    @patch("ipset_ops.add_many")
    @patch("ipset_ops.create")
    @patch("ipset_ops.destroy")
    def test_builds_a_temp_set_and_swaps_it_in(self, mock_destroy, mock_create, mock_add_many, mock_swap):
        ipset_ops.replace_members("pvx-geo", ["1.2.3.0/24", "5.6.7.0/24"])

        mock_destroy.assert_called_once_with("pvx-geo-new")  # limpa sobra de uma falha anterior
        self.assertEqual(
            mock_create.call_args_list,
            [unittest.mock.call("pvx-geo"), unittest.mock.call("pvx-geo-new")],
        )
        mock_add_many.assert_called_once_with("pvx-geo-new", ["1.2.3.0/24", "5.6.7.0/24"])
        mock_swap.assert_called_once_with("pvx-geo-new", "pvx-geo")

    @patch("ipset_ops.swap")
    @patch("ipset_ops.add_many", side_effect=RuntimeError("falhou"))
    @patch("ipset_ops.create")
    @patch("ipset_ops.destroy")
    def test_failed_load_does_not_swap(self, mock_destroy, mock_create, mock_add_many, mock_swap):
        with self.assertRaises(RuntimeError):
            ipset_ops.replace_members("pvx-geo", ["1.2.3.0/24"])
        mock_swap.assert_not_called()


if __name__ == "__main__":
    unittest.main()
