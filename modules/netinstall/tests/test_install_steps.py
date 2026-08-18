import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch

import install_steps


class DisableIpv6Test(unittest.TestCase):
    @patch("install_steps.os_ops.run_cmd")
    def test_appends_line_when_absent(self, mock_run_cmd):
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".sysctl") as f:
            f.write("net.ipv4.ip_forward = 1\n")
            path = f.name
        install_steps._disable_ipv6(path)
        content = Path(path).read_text()
        self.assertIn("net.ipv6.conf.all.disable_ipv6 = 1", content)
        mock_run_cmd.assert_called_once_with(["sysctl", "-p"])

    @patch("install_steps.os_ops.run_cmd")
    def test_does_not_duplicate_when_already_present(self, mock_run_cmd):
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".sysctl") as f:
            f.write("net.ipv6.conf.all.disable_ipv6 = 1\n")
            path = f.name
        install_steps._disable_ipv6(path)
        content = Path(path).read_text()
        self.assertEqual(content.count("disable_ipv6"), 1)


class SetSelinuxDisabledTest(unittest.TestCase):
    def test_rewrites_selinux_line_to_disabled(self):
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".selinux") as f:
            f.write("SELINUX=enforcing\nSELINUXTYPE=targeted\n")
            path = f.name
        install_steps._set_selinux_config_disabled(path)
        content = Path(path).read_text()
        self.assertIn("SELINUX=disabled", content)
        self.assertIn("SELINUXTYPE=targeted", content)

    def test_no_op_when_file_missing(self):
        install_steps._set_selinux_config_disabled("/nonexistent/selinux/config")  # não levanta


class UserExistsTest(unittest.TestCase):
    def test_true_when_user_line_present(self):
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".passwd") as f:
            f.write("root:x:0:0::/root:/bin/bash\nasterisk:x:995:995::/var/lib/asterisk:/bin/bash\n")
            path = f.name
        self.assertTrue(install_steps._user_exists("asterisk", path))

    def test_false_when_absent(self):
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".passwd") as f:
            f.write("root:x:0:0::/root:/bin/bash\n")
            path = f.name
        self.assertFalse(install_steps._user_exists("asterisk", path))


class AddReposTest(unittest.TestCase):
    # os .repo vêm de DENTRO do .pyz (assets.py) -- no host instalado só module.pyz+
    # manifest.json existem no diretório do módulo, nunca uma pasta config/ solta ao lado
    # (achado raciocinando sobre o deploy real: os testes antigos assumiam um diretório
    # config/ que nunca existe fora da árvore de código-fonte local).
    @patch("install_steps.assets.extract_prefix", return_value=["/etc/yum.repos.d/Issabel5.repo"])
    @patch("install_steps._disable_ipv6")
    @patch("install_steps.os_ops.run_cmd")
    @patch("install_steps.os_ops.pkg_install", return_value=[])
    def test_installs_epel_htop_tmux_and_extracts_repo_files_from_the_pyz(
        self, mock_pkg, mock_run_cmd, mock_ipv6, mock_extract
    ):
        install_steps.add_repos("/path/to/module.pyz")

        mock_pkg.assert_any_call(["epel-release"])
        mock_pkg.assert_any_call(["htop", "tmux"])
        mock_run_cmd.assert_any_call(["dnf", "makecache"])
        mock_extract.assert_called_once_with("/path/to/module.pyz", "config/repos", "/etc/yum.repos.d")

    @patch("install_steps.assets.extract_prefix", return_value=[])
    @patch("install_steps._disable_ipv6")
    @patch("install_steps.os_ops.run_cmd")
    @patch("install_steps.os_ops.pkg_install", return_value=[])
    def test_no_op_when_pyz_has_no_repo_files(self, mock_pkg, mock_run_cmd, mock_ipv6, mock_extract):
        install_steps.add_repos("/path/to/module.pyz")  # não levanta mesmo sem repos no .pyz

    # pkg_install() já retorna quais pacotes falharam -- ignorar isso deixa o processo
    # seguir quieto e crashar (confuso) várias etapas depois, num ponto sem relação
    # nenhuma com o pacote que de fato não instalou (achado ao vivo: crash tentando
    # rodar /usr/sbin/amportal, causa real era outro pacote falho lá atrás).
    @patch("install_steps._disable_ipv6")
    @patch("install_steps.os_ops.run_cmd")
    @patch("install_steps.os_ops.pkg_install", return_value=["epel-release"])
    def test_raises_naming_the_package_when_epel_fails(self, mock_pkg, mock_run_cmd, mock_ipv6):
        with self.assertRaisesRegex(RuntimeError, "epel-release"):
            install_steps.add_repos("/path/to/module.pyz")


class PrepareSystemTest(unittest.TestCase):
    @patch("install_steps.os_ops.pkg_install", return_value=[])
    @patch("install_steps._user_exists", return_value=False)
    @patch("install_steps._set_selinux_config_disabled")
    @patch("install_steps.os_ops.run_cmd")
    def test_creates_asterisk_user_when_absent(self, mock_run_cmd, mock_selinux, mock_exists, mock_pkg):
        install_steps.prepare_system()
        useradd_calls = [c for c in mock_run_cmd.call_args_list if "useradd" in c.args[0]]
        self.assertEqual(len(useradd_calls), 1)
        mock_pkg.assert_called_once_with(["issabel-config_helpers"])

    @patch("install_steps.os_ops.pkg_install", return_value=[])
    @patch("install_steps._user_exists", return_value=True)
    @patch("install_steps._set_selinux_config_disabled")
    @patch("install_steps.os_ops.run_cmd")
    def test_skips_useradd_when_already_present(self, mock_run_cmd, mock_selinux, mock_exists, mock_pkg):
        install_steps.prepare_system()
        useradd_calls = [c for c in mock_run_cmd.call_args_list if "useradd" in c.args[0]]
        self.assertEqual(useradd_calls, [])

    @patch("install_steps.os_ops.pkg_install", return_value=["issabel-config_helpers"])
    @patch("install_steps._user_exists", return_value=True)
    @patch("install_steps._set_selinux_config_disabled")
    @patch("install_steps.os_ops.run_cmd")
    def test_raises_naming_the_package_when_it_fails(self, mock_run_cmd, mock_selinux, mock_exists, mock_pkg):
        with self.assertRaisesRegex(RuntimeError, "issabel-config_helpers"):
            install_steps.prepare_system()


class EnablePhpRemiTest(unittest.TestCase):
    @patch("install_steps.os_ops.run_cmd")
    @patch("install_steps.os_ops.pkg_install", return_value=[])
    def test_installs_remi_release_for_the_given_major_version(self, mock_pkg, mock_run_cmd):
        install_steps.enable_php_remi(9)
        mock_pkg.assert_called_once_with(["https://rpms.remirepo.net/enterprise/remi-release-9.rpm"])
        modules_reset = [c for c in mock_run_cmd.call_args_list if c.args[0][:3] == ["dnf", "module", "reset"]]
        self.assertEqual(len(modules_reset), 1)

    @patch("install_steps.os_ops.run_cmd")
    @patch("install_steps.os_ops.pkg_install", return_value=["https://rpms.remirepo.net/enterprise/remi-release-9.rpm"])
    def test_raises_naming_the_package_when_it_fails(self, mock_pkg, mock_run_cmd):
        with self.assertRaisesRegex(RuntimeError, "remi-release-9"):
            install_steps.enable_php_remi(9)


class InstallPackagesTest(unittest.TestCase):
    @patch("install_steps.os_ops.pkg_install", return_value=[])
    @patch("install_steps.os_ops.run_cmd")
    def test_substitutes_astver_placeholder_and_installs_both_lists(self, mock_run_cmd, mock_pkg):
        install_steps.install_packages("18", extra_packages=["wanpipe-utils"])
        base_call = mock_pkg.call_args_list[0].args[0]
        self.assertIn("asterisk18", base_call)
        self.assertNotIn("asterisk$ASTVER", base_call)
        issabel_call = mock_pkg.call_args_list[1].args[0]
        self.assertIn("wanpipe-utils", issabel_call)

    @patch("install_steps.os_ops.run_cmd")
    @patch("install_steps.os_ops.pkg_install", side_effect=[[], ["issabel"]])
    def test_raises_naming_the_package_when_issabel_list_fails(self, mock_pkg, mock_run_cmd):
        with self.assertRaisesRegex(RuntimeError, "issabel"):
            install_steps.install_packages("18")

    @patch("install_steps.os_ops.run_cmd")
    @patch("install_steps.os_ops.pkg_install", return_value=[])
    def test_forwards_on_line_to_both_package_lists(self, mock_pkg, mock_run_cmd):
        # é a etapa mais longa (base + Asterisk + Issabel) -- a única com log ao vivo
        # (docker-build-style) embaixo do spinner, ver widgets.step_with_log().
        on_line = lambda line: None
        install_steps.install_packages("18", on_line=on_line)
        self.assertEqual(mock_pkg.call_args_list[0].kwargs, {"on_line": on_line})
        self.assertEqual(mock_pkg.call_args_list[1].kwargs, {"on_line": on_line})

    @patch("install_steps.os_ops.run_cmd")
    @patch("install_steps.os_ops.pkg_install", return_value=[])
    def test_cleans_dnf_cache_by_default(self, mock_pkg, mock_run_cmd):
        install_steps.install_packages("18")
        mock_run_cmd.assert_any_call(["dnf", "clean", "all"])

    @patch("install_steps.os_ops.run_cmd")
    @patch("install_steps.os_ops.pkg_install", return_value=[])
    def test_skip_clean_avoids_wiping_the_dnf_cache(self, mock_pkg, mock_run_cmd):
        # reinstalar repetido na mesma máquina de teste paga o resync de metadata
        # inteiro toda vez por causa disso -- útil só numa máquina nova de verdade.
        install_steps.install_packages("18", skip_clean=True)
        clean_calls = [c for c in mock_run_cmd.call_args_list if c.args[0] == ["dnf", "clean", "all"]]
        self.assertEqual(clean_calls, [])


class PostInstallTest(unittest.TestCase):
    @patch("install_steps.os_ops.run_cmd", return_value=True)
    @patch("install_steps.shutil.which", return_value="/usr/bin/firewall-cmd")
    def test_disables_firewalld_when_present(self, mock_which, mock_run_cmd):
        install_steps.post_install()
        disable_calls = [c for c in mock_run_cmd.call_args_list if "firewalld" in " ".join(c.args[0])]
        self.assertTrue(len(disable_calls) >= 1)

    @patch("install_steps.os_ops.run_cmd", return_value=True)
    @patch("install_steps.shutil.which", return_value=None)
    def test_skips_firewalld_step_when_absent(self, mock_which, mock_run_cmd):
        install_steps.post_install()
        disable_calls = [c for c in mock_run_cmd.call_args_list if "firewalld" in " ".join(c.args[0])]
        self.assertEqual(disable_calls, [])


class InstallControlPanelTest(unittest.TestCase):
    @patch("install_steps.assets.extract_prefix",
           return_value=["/var/www/html/modules/control_panel/index.php"])
    @patch("install_steps.os_ops.run_cmd", return_value=True)
    def test_extracts_assets_from_the_pyz_and_runs_sqlite_inserts(self, mock_run_cmd, mock_extract):
        install_steps.install_control_panel("/path/to/module.pyz")
        mock_extract.assert_called_once_with(
            "/path/to/module.pyz", "config/control_panel", "/var/www/html/modules/control_panel"
        )
        sqlite_calls = [c for c in mock_run_cmd.call_args_list if c.args[0][0] == "sqlite3"]
        self.assertEqual(len(sqlite_calls), 3)

    @patch("install_steps.assets.extract_prefix", return_value=[])
    @patch("install_steps.os_ops.run_cmd", return_value=True)
    def test_no_sqlite_inserts_when_pyz_has_no_control_panel_assets(self, mock_run_cmd, mock_extract):
        install_steps.install_control_panel("/path/to/module.pyz")
        sqlite_calls = [c for c in mock_run_cmd.call_args_list if c.args[0][0] == "sqlite3"]
        self.assertEqual(sqlite_calls, [])


class SetPasswordsTest(unittest.TestCase):
    @patch("install_steps._sync_fop2_secret")
    @patch("install_steps.os_ops.run_cmd", return_value=True)
    def test_runs_admin_passwords_cli_then_syncs_fop2(self, mock_run_cmd, mock_fop2):
        install_steps.set_passwords("sqlpw", "webpw")
        admin_calls = [c for c in mock_run_cmd.call_args_list if "issabel-admin-passwords" in c.args[0][0]]
        self.assertEqual(len(admin_calls), 1)
        self.assertIn("sqlpw", admin_calls[0].args[0])
        self.assertIn("webpw", admin_calls[0].args[0])
        mock_fop2.assert_called_once()

    @patch("install_steps._sync_fop2_secret")
    @patch("install_steps.os_ops.run_cmd", return_value=False)
    def test_skips_fop2_sync_when_admin_passwords_fails(self, mock_run_cmd, mock_fop2):
        install_steps.set_passwords("sqlpw", "webpw")
        mock_fop2.assert_not_called()


class SyncFop2SecretTest(unittest.TestCase):
    @patch("install_steps.os_ops.run_cmd", return_value=True)
    @patch("install_steps.os.access", return_value=True)
    @patch("install_steps.os.path.exists", return_value=True)
    def test_runs_script_when_present(self, mock_exists, mock_access, mock_run_cmd):
        install_steps._sync_fop2_secret()
        mock_run_cmd.assert_called_once_with(["/usr/local/fop2/create_fop2_manager_user.pl"])

    @patch("install_steps.os_ops.run_cmd")
    @patch("install_steps.os.path.exists", return_value=False)
    def test_no_op_when_script_absent(self, mock_exists, mock_run_cmd):
        install_steps._sync_fop2_secret()
        mock_run_cmd.assert_not_called()


if __name__ == "__main__":
    unittest.main()
