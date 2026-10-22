import datetime
import io
import sqlite3
import tarfile
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import Mock, patch

import backup_ops as ops


def _run_result(returncode=0, stderr="", stdout=""):
    result = Mock()
    result.returncode = returncode
    result.stderr = stderr
    result.stdout = stdout
    return result


def _make_acl_db(path, password):
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE acl_user (id INTEGER PRIMARY KEY, md5_password TEXT)")
        conn.execute("INSERT INTO acl_user (id, md5_password) VALUES (1, ?)", (password,))
        conn.commit()


class AvailableComponentsTest(unittest.TestCase):
    def test_official_components_without_the_extras_marker(self):
        with patch("backup_ops.os.path.isfile", return_value=False):
            components = ops.available_components()
        self.assertIn("as_db", components)
        self.assertNotIn("int_ixcsoft", components)

    def test_appends_phonevox_extras_when_the_marker_file_exists(self):
        with patch("backup_ops.os.path.isfile", return_value=True):
            components = ops.available_components()
        self.assertIn("int_ixcsoft", components)
        self.assertIn("as_db", components)


class AutodetectComponentsTest(unittest.TestCase):
    def test_detects_a_key_by_its_primary_directory(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, "etc/asterisk/sgp").mkdir(parents=True)
            detected = ops.autodetect_components(root=root)
        self.assertIn("int_sgp", detected)

    def test_ignores_a_key_when_none_of_its_directories_exist(self):
        with tempfile.TemporaryDirectory() as root:
            detected = ops.autodetect_components(root=root)
        self.assertEqual(detected, [])

    def test_ignores_a_shared_auxiliary_directory_that_is_not_the_primary_one(self):
        # achado ao vivo: /var/lib/asterisk/sounds/ura-inteligente aparece na
        # lista tanto de int_sgp quanto de int_receitanet -- só ele presente
        # não pode marcar os dois como detectados (falso positivo).
        with tempfile.TemporaryDirectory() as root:
            Path(root, "var/lib/asterisk/sounds/ura-inteligente").mkdir(parents=True)
            detected = ops.autodetect_components(root=root)
        self.assertEqual(detected, [])


class BackupfileForDirTest(unittest.TestCase):
    def test_matches_the_backupengine_naming_convention(self):
        self.assertEqual(ops.backupfile_for_dir("/etc/asterisk/sgp"), "etc.asterisk.sgp.tgz")
        self.assertEqual(
            ops.backupfile_for_dir("/var/lib/asterisk/agi-bin/ixcsoft"),
            "var.lib.asterisk.agi-bin.ixcsoft.tgz",
        )
        self.assertEqual(ops.backupfile_for_dir("/var/www/html/sgp"), "var.www.html.sgp.tgz")


class DefaultFilenameTest(unittest.TestCase):
    def test_matches_the_native_issabel_web_ui_naming_convention(self):
        # `modules/backup_restore/index.php` (System) só lista/restaura/baixa
        # um arquivo que bate exatamente com
        # `preg_match('/(^issabel|^cloud)backup-\d{14}-\w{2}\.tar$/', $nome)`
        # -- confirmado lendo o fonte público (IssabelFoundation/system). Os
        # 2 caracteres finais não têm significado nativo (lá são só
        # primeiro+último char do session id do PHP); "px" é a assinatura
        # Phonevox nesse espaço.
        self.assertEqual(
            ops.default_filename(now=datetime.datetime(2026, 9, 14, 13, 5, 9)),
            "issabelbackup-20260914130509-px.tar",
        )
        self.assertRegex(ops.default_filename(), r"^issabelbackup-\d{14}-px\.tar$")


class MatchesNativeNamingTest(unittest.TestCase):
    def test_accepts_the_pvx_default(self):
        self.assertTrue(ops.matches_native_naming(ops.default_filename()))

    def test_accepts_a_full_path_by_checking_only_the_basename(self):
        self.assertTrue(ops.matches_native_naming("/var/www/backup/issabelbackup-20260914130509-px.tar"))

    def test_accepts_the_cloud_prefix_too(self):
        self.assertTrue(ops.matches_native_naming("cloudbackup-20260914130509-zz.tar"))

    def test_rejects_a_prefix_before_issabel(self):
        # exatamente o caso que originou isso: nome com prefixo (mesmo que
        # "pvx-") na frente nunca bate, o regex nativo exige começar com
        # "issabel"/"cloud".
        self.assertFalse(ops.matches_native_naming("pvx-issabelbackup-20260914130509-px.tar"))

    def test_rejects_the_old_pvx_default_format(self):
        self.assertFalse(ops.matches_native_naming("issabel-backup-20260914130509.tar"))

    def test_rejects_a_non_tar_extension(self):
        self.assertFalse(ops.matches_native_naming("issabelbackup-20260914130509-px.tar.gz"))


class ExportBackupTest(unittest.TestCase):
    def test_raises_when_not_an_issabel_box(self):
        with patch("backup_ops.shutil.which", return_value=None):
            with self.assertRaises(ops.IssabelBackupError) as ctx:
                ops.export_backup("x.tar", ["as_db"])
        self.assertIn("issabel-helper", str(ctx.exception))

    def test_raises_when_no_components_given(self):
        with patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"):
            with self.assertRaises(ops.IssabelBackupError) as ctx:
                ops.export_backup("x.tar", [])
        self.assertIn("componente", str(ctx.exception))

    def test_calls_issabel_helper_with_an_absolute_path_split_into_tmpdir_and_bare_filename(self):
        # --backupfile do issabel-helper só aceita nome sem diretório --
        # --tmpdir vira o diretório de verdade que o usuário pediu.
        with tempfile.TemporaryDirectory() as tmp_dir:
            Path(tmp_dir, "x.tar").write_text("fake")
            with patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"), \
                 patch("backup_ops.subprocess.run", return_value=_run_result()) as mock_run:
                path, warning = ops.export_backup(f"{tmp_dir}/x.tar", ["as_db", "as_config_files"])

        self.assertEqual(path, f"{tmp_dir}/x.tar")
        self.assertIsNone(warning)
        args = mock_run.call_args.args[0]
        self.assertEqual(args[0], "issabel-helper")
        self.assertIn("--backup", args)
        self.assertIn("x.tar", args)
        self.assertIn("as_db,as_config_files", args)
        self.assertIn(tmp_dir, args)

    def test_retries_without_components_the_helper_reports_as_unimplemented(self):
        # achado ao vivo (Issabel 5 real, sem Call Center CE/Asternic/FOP2
        # instalados): issabel-helper recusa o --components inteiro (nenhum
        # arquivo é gerado) se QUALQUER um dos componentes pedidos não
        # estiver implementado nessa central específica -- ao contrário do
        # "componente individual falhou" (não-fatal, arquivo sai igual).
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = f"{tmp_dir}/x.tar"

            def fake_run(args, **kwargs):
                requested = args[args.index("--components") + 1]
                if "callcenter_db" in requested:
                    return _run_result(
                        returncode=1,
                        stderr="Option --components: unimplemented components: callcenter_db,asternic_db",
                    )
                Path(path).write_text("fake")
                return _run_result()

            with patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"), \
                 patch("backup_ops.subprocess.run", side_effect=fake_run) as mock_run:
                result_path, warning = ops.export_backup(path, ["as_db", "callcenter_db", "asternic_db"])

        self.assertEqual(result_path, path)
        self.assertEqual(mock_run.call_count, 2)
        second_call_args = mock_run.call_args.args[0]
        self.assertEqual(second_call_args[second_call_args.index("--components") + 1], "as_db")
        self.assertIn("callcenter_db", warning)
        self.assertIn("asternic_db", warning)

    def test_raises_a_clean_error_when_every_requested_component_is_unimplemented(self):
        with patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"), \
             patch("backup_ops.subprocess.run", return_value=_run_result(
                 returncode=1, stderr="Option --components: unimplemented components: callcenter_db",
             )):
            with self.assertRaises(ops.IssabelBackupError) as ctx:
                ops.export_backup("x.tar", ["callcenter_db"])
        self.assertIn("callcenter_db", str(ctx.exception))

    def test_a_bare_filename_lands_in_the_current_working_directory(self):
        # pedido explícito: exportar com só um nome de arquivo salva relativo
        # a onde o pvx foi chamado, não num diretório fixo do Issabel.
        with tempfile.TemporaryDirectory() as cwd:
            Path(cwd, "x.tar").write_text("fake")
            with patch("backup_ops.os.getcwd", return_value=cwd), \
                 patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"), \
                 patch("backup_ops.subprocess.run", return_value=_run_result()) as mock_run:
                path, _ = ops.export_backup("x.tar", ["as_db"])

        self.assertEqual(path, f"{cwd}/x.tar")
        self.assertIn(cwd, mock_run.call_args.args[0])

    def test_raises_when_the_target_directory_does_not_exist(self):
        with patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"):
            with self.assertRaises(ops.IssabelBackupError) as ctx:
                ops.export_backup("/nao/existe/x.tar", ["as_db"])
        self.assertIn("diretório", str(ctx.exception))

    def test_raises_when_issabel_helper_does_not_produce_the_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir, \
             patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"), \
             patch("backup_ops.subprocess.run", return_value=_run_result()):
            with self.assertRaises(ops.IssabelBackupError) as ctx:
                ops.export_backup(f"{tmp_dir}/x.tar", ["as_db"])
        self.assertIn("não foi gerado", str(ctx.exception))

    def test_raises_using_captured_output_when_the_file_is_missing_and_the_helper_failed(self):
        with patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"), \
             patch("backup_ops.subprocess.run", return_value=_run_result(returncode=1, stderr="boom")):
            with self.assertRaises(ops.IssabelBackupError) as ctx:
                ops.export_backup("x.tar", ["as_db"])
        self.assertIn("boom", str(ctx.exception))

    def test_falls_back_to_stdout_when_issabel_helper_writes_the_error_there(self):
        # achado ao vivo (autobackup): pbackup/issabel-helper às vezes erra sem
        # escrever nada em stderr -- sem o fallback pro stdout, o motivo real
        # do erro some sem deixar rastro nenhum.
        with patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"), \
             patch("backup_ops.subprocess.run", return_value=_run_result(returncode=1, stdout="deu ruim")):
            with self.assertRaises(ops.IssabelBackupError) as ctx:
                ops.export_backup("x.tar", ["as_db"])
        self.assertIn("deu ruim", str(ctx.exception))

    def test_writes_a_hidden_pvx_manifest_when_generated_by_is_given(self):
        # achado ao vivo: dá pra saber se um backup existente veio do pvx ou
        # de outra ferramenta (native/manual) só de olhar pra dentro dele.
        with tempfile.TemporaryDirectory() as tmp_dir:
            with tarfile.open(Path(tmp_dir, "x.tar"), "w"):
                pass  # tar vazio, mas válido -- issabel-helper é mockado abaixo
            with patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"), \
                 patch("backup_ops.subprocess.run", return_value=_run_result()):
                path, _ = ops.export_backup(f"{tmp_dir}/x.tar", ["as_db"], generated_by="pvx issabel v0.1.4")
            with tarfile.open(path) as tar:
                manifest = tar.extractfile(ops.MANIFEST_MEMBER).read().decode()
        self.assertIn("gerado_por=pvx issabel v0.1.4", manifest)
        self.assertIn("gerado_em=", manifest)

    def test_skips_the_manifest_when_generated_by_is_not_given(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with tarfile.open(Path(tmp_dir, "x.tar"), "w"):
                pass
            with patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"), \
                 patch("backup_ops.subprocess.run", return_value=_run_result()):
                path, _ = ops.export_backup(f"{tmp_dir}/x.tar", ["as_db"])
            with tarfile.open(path) as tar:
                self.assertNotIn(ops.MANIFEST_MEMBER, tar.getnames())

    def test_nonzero_exit_code_is_not_fatal_when_the_file_was_produced_anyway(self):
        # achado ao vivo: issabel-helper (igual a interface web nativa)
        # retorna código != 0 sempre que QUALQUER componente individual
        # falha (banco que não existe nessa central, etc.) mesmo com o
        # arquivo final gerado com sucesso -- exit code não é o sinal de
        # verdade, o arquivo no disco é.
        with tempfile.TemporaryDirectory() as tmp_dir:
            Path(tmp_dir, "x.tar").write_text("fake")
            with patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"), \
                 patch("backup_ops.subprocess.run", return_value=_run_result(returncode=1, stderr="WARN: ...")):
                path, warning = ops.export_backup(f"{tmp_dir}/x.tar", ["as_db"])
        self.assertEqual(path, f"{tmp_dir}/x.tar")
        self.assertEqual(warning, "WARN: ...")


class WriteManifestTest(unittest.TestCase):
    def _manifest_of(self, path):
        with tarfile.open(path) as tar:
            return tar.extractfile(ops.MANIFEST_MEMBER).read().decode()

    def test_omits_the_manual_field_when_no_manual_components_are_given(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = str(Path(tmp_dir, "x.tar"))
            with tarfile.open(path, "w"):
                pass
            ops.write_manifest(path, "pvx issabel v0.1")
            self.assertNotIn("componentes_manuais", self._manifest_of(path))

    def test_records_which_components_were_captured_manually(self):
        # distingue "veio do backupengine de verdade" de "empacotado cru por
        # fora dele" -- importa pra saber o quanto confiar na restauração
        # desse componente específico depois.
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = str(Path(tmp_dir, "x.tar"))
            with tarfile.open(path, "w"):
                pass
            ops.write_manifest(path, "pvx issabel v0.1", manual_components=["int_sgp", "int_ixcsoft"])
            self.assertIn("componentes_manuais=int_sgp,int_ixcsoft", self._manifest_of(path))

    def test_a_later_call_shadows_the_earlier_one_on_read(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = str(Path(tmp_dir, "x.tar"))
            with tarfile.open(path, "w"):
                pass
            ops.write_manifest(path, "pvx issabel v0.1")
            ops.write_manifest(path, "pvx issabel v0.1", manual_components=["int_sgp"])
            self.assertIn("componentes_manuais=int_sgp", self._manifest_of(path))


class RecordComponentsTest(unittest.TestCase):
    def test_writes_an_option_per_component(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = str(Path(tmp_dir, "x.tar"))
            with tarfile.open(path, "w"):
                pass
            ops.record_components(path, ["as_db", "int_sgp"])
            with tarfile.open(path) as tar:
                raw = tar.extractfile("backup/a_options.xml").read()
        options = [o.text for group in ET.fromstring(raw) for o in group]
        self.assertEqual(sorted(options), ["as_db", "int_sgp"])

    def test_a_later_call_shadows_the_earlier_one_on_read(self):
        # tarfile.getmember() resolve nome duplicado pro último membro --
        # é assim que dá pra "substituir" o a_options.xml de um export já
        # feito sem reescrever o tar inteiro.
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = str(Path(tmp_dir, "x.tar"))
            with tarfile.open(path, "w"):
                pass
            ops.record_components(path, ["as_db"])
            ops.record_components(path, ["as_db", "int_sgp"])
            with tarfile.open(path) as tar:
                raw = tar.extractfile("backup/a_options.xml").read()
        options = [o.text for group in ET.fromstring(raw) for o in group]
        self.assertEqual(sorted(options), ["as_db", "int_sgp"])


class CreateManualBackupShellTest(unittest.TestCase):
    def test_produces_a_backup_that_inspect_backup_can_read(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("backup_ops.installed_issabel_version", return_value="5.0.0"):
                path = ops.create_manual_backup_shell(
                    f"{tmp_dir}/x.tar", ["int_sgp"], generated_by="pvx issabel v0.1",
                )
            info = ops.inspect_backup(path)
        self.assertEqual(info["components"], ["int_sgp"])
        self.assertEqual(info["versions"]["issabelpbx"], "5.0.0")
        self.assertEqual(info["manifest"]["gerado_por"], "pvx issabel v0.1")
        self.assertEqual(info["manifest"]["componentes_manuais"], "int_sgp")

    def test_works_without_a_known_issabel_version(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("backup_ops.installed_issabel_version", return_value=None):
                path = ops.create_manual_backup_shell(f"{tmp_dir}/x.tar", ["int_sgp"])
            info = ops.inspect_backup(path)
        self.assertEqual(info["versions"], {})

    def test_raises_when_the_target_directory_does_not_exist(self):
        with self.assertRaises(ops.IssabelBackupError):
            ops.create_manual_backup_shell("/no/such/dir/x.tar", ["int_sgp"])


class ExportManualComponentTest(unittest.TestCase):
    def test_appends_a_tgz_member_for_each_existing_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir, "root")
            (root / "etc/asterisk/sgp").mkdir(parents=True)
            (root / "etc/asterisk/sgp/foo.conf").write_text("hello")
            backup_path = str(Path(tmp_dir, "x.tar"))
            with tarfile.open(backup_path, "w"):
                pass

            backed_up = ops.export_manual_component(backup_path, "int_sgp", root=str(root))

            with tarfile.open(backup_path) as tar:
                self.assertIn("backup/etc.asterisk.sgp.tgz", tar.getnames())
        self.assertEqual(backed_up, ["/etc/asterisk/sgp"])

    def test_skips_directories_that_do_not_exist_under_root(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir, "root")
            root.mkdir()
            backup_path = str(Path(tmp_dir, "x.tar"))
            with tarfile.open(backup_path, "w"):
                pass

            backed_up = ops.export_manual_component(backup_path, "int_sgp", root=str(root))

        self.assertEqual(backed_up, [])

    def test_round_trips_with_restore_manual_component(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src_root = Path(tmp_dir, "src")
            (src_root / "etc/asterisk/sgp").mkdir(parents=True)
            (src_root / "etc/asterisk/sgp/foo.conf").write_text("hello")
            backup_path = str(Path(tmp_dir, "x.tar"))
            with tarfile.open(backup_path, "w"):
                pass
            ops.export_manual_component(backup_path, "int_sgp", root=str(src_root))

            dest_root = Path(tmp_dir, "dest")
            with patch("backup_ops.subprocess.run"):
                restored = ops.restore_manual_component(backup_path, "int_sgp", root=str(dest_root))

            self.assertEqual((dest_root / "etc/asterisk/sgp/foo.conf").read_text(), "hello")
        self.assertIn("/etc/asterisk/sgp", restored)


class ImportBackupTest(unittest.TestCase):
    def test_raises_when_not_an_issabel_box(self):
        with patch("backup_ops.shutil.which", return_value=None):
            with self.assertRaises(ops.IssabelBackupError) as ctx:
                ops.import_backup("x.tar", ["as_db"])
        self.assertIn("issabel-helper", str(ctx.exception))

    def test_raises_when_no_components_given(self):
        with patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"):
            with self.assertRaises(ops.IssabelBackupError) as ctx:
                ops.import_backup("x.tar", [])
        self.assertIn("componente", str(ctx.exception))

    def test_raises_when_the_backup_file_is_not_found(self):
        with tempfile.TemporaryDirectory() as tmp_dir, \
             patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"):
            with self.assertRaises(ops.IssabelBackupError) as ctx:
                ops.import_backup(f"{tmp_dir}/missing.tar", ["as_db"])
        self.assertIn("não encontrado", str(ctx.exception))

    def test_calls_issabel_helper_using_the_files_own_directory_as_tmpdir(self):
        # --restore do issabel-helper exige o arquivo já dentro de --tmpdir,
        # referenciado só pelo nome -- nada de copiar pra um lugar fixo.
        with tempfile.TemporaryDirectory() as tmp_dir:
            Path(tmp_dir, "x.tar").write_text("fake")
            with patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"), \
                 patch("backup_ops.subprocess.run", return_value=_run_result()) as mock_run:
                ops.import_backup(f"{tmp_dir}/x.tar", ["as_db"])

        args = mock_run.call_args.args[0]
        self.assertIn("--restore", args)
        self.assertIn("x.tar", args)
        self.assertIn(tmp_dir, args)

    def test_a_bare_filename_is_resolved_against_the_current_working_directory(self):
        with tempfile.TemporaryDirectory() as cwd:
            Path(cwd, "x.tar").write_text("fake")
            with patch("backup_ops.os.getcwd", return_value=cwd), \
                 patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"), \
                 patch("backup_ops.subprocess.run", return_value=_run_result()) as mock_run:
                ops.import_backup("x.tar", ["as_db"])
        self.assertIn(cwd, mock_run.call_args.args[0])

    def test_nonzero_exit_code_is_not_fatal_and_is_returned_as_a_warning(self):
        # mesmo achado do export: o próprio --restore nativo (igual a
        # interface web) retorna código != 0 sempre que algum componente
        # individual falha, sem que a restauração como um todo tenha dado
        # errado -- não existe um "arquivo gerado" pra conferir aqui como no
        # export, então isso nunca é tratado como fatal.
        with tempfile.TemporaryDirectory() as tmp_dir:
            Path(tmp_dir, "x.tar").write_text("fake")
            with patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"), \
                 patch("backup_ops.subprocess.run", return_value=_run_result(returncode=1, stderr="WARN: ...")):
                warning = ops.import_backup(f"{tmp_dir}/x.tar", ["as_db"])
        self.assertEqual(warning, "WARN: ...")

    def test_returns_no_warning_on_a_clean_exit(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            Path(tmp_dir, "x.tar").write_text("fake")
            with patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"), \
                 patch("backup_ops.subprocess.run", return_value=_run_result()):
                warning = ops.import_backup(f"{tmp_dir}/x.tar", ["as_db"])
        self.assertIsNone(warning)


class RunNativeMigrationTest(unittest.TestCase):
    # migração 4->5: em vez de replicar campo a campo o que o backupengine
    # quebra (menu.db, senha de admin, upgrade de módulos PBX), usa o
    # migrador nativo (issabel-helper migration -> issabel_migration.sh),
    # o mesmo que o botão "Migrate from Issabel 4" da web roda.
    def test_raises_when_not_an_issabel_box(self):
        with patch("backup_ops.shutil.which", return_value=None):
            with self.assertRaises(ops.IssabelBackupError) as ctx:
                ops.run_native_migration("x.tar")
        self.assertIn("issabel-helper", str(ctx.exception))

    def test_raises_when_the_backup_file_is_not_found(self):
        with tempfile.TemporaryDirectory() as tmp_dir, \
             patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"):
            with self.assertRaises(ops.IssabelBackupError) as ctx:
                ops.run_native_migration(f"{tmp_dir}/missing.tar")
        self.assertIn("não encontrado", str(ctx.exception))

    def test_calls_issabel_helper_migration_with_the_full_path(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            Path(tmp_dir, "x.tar").write_text("fake")
            with patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"), \
                 patch("backup_ops.subprocess.run", return_value=_run_result()) as mock_run:
                ops.run_native_migration(f"{tmp_dir}/x.tar")

        args = mock_run.call_args.args[0]
        self.assertEqual(args, ["issabel-helper", "migration", f"{tmp_dir}/x.tar"])

    def test_nonzero_exit_code_is_not_fatal_and_is_returned_as_a_warning(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            Path(tmp_dir, "x.tar").write_text("fake")
            with patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"), \
                 patch("backup_ops.subprocess.run", return_value=_run_result(returncode=1, stderr="WARN: ...")):
                warning = ops.run_native_migration(f"{tmp_dir}/x.tar")
        self.assertEqual(warning, "WARN: ...")

    def test_returns_no_warning_on_a_clean_exit(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            Path(tmp_dir, "x.tar").write_text("fake")
            with patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"), \
                 patch("backup_ops.subprocess.run", return_value=_run_result()):
                warning = ops.run_native_migration(f"{tmp_dir}/x.tar")
        self.assertIsNone(warning)


class InspectBackupTest(unittest.TestCase):
    def _build_fake_backup(self, path, components, issabel_version="5.0.0"):
        with tempfile.TemporaryDirectory() as work_dir:
            backup_dir = Path(work_dir, "backup")
            backup_dir.mkdir()
            options_xml = "<raiz>" + "".join(
                f'<options id="grp">{"".join(f"<option>{c}</option>" for c in components)}</options>'
            ) + "</raiz>"
            (backup_dir / "a_options.xml").write_text(options_xml)
            versions_xml = f'<versions><program id="issabel" ver="{issabel_version}" rel="1"/></versions>'
            (backup_dir / "versions.xml").write_text(versions_xml)
            with tarfile.open(path, "w") as tar:
                tar.add(backup_dir, arcname="backup")

    def test_reads_components_and_issabel_version_from_the_archive(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = str(Path(tmp_dir, "x.tar"))
            self._build_fake_backup(path, ["as_db", "mysql_db"], issabel_version="5.0.0")
            info = ops.inspect_backup(path)

        self.assertEqual(sorted(info["components"]), ["as_db", "mysql_db"])
        self.assertEqual(info["versions"]["issabel"], "5.0.0")
        self.assertEqual(info["manifest"], {})

    def test_reads_the_pvx_manifest_when_present(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = str(Path(tmp_dir, "x.tar"))
            self._build_fake_backup(path, ["as_db"])
            manifest = b"gerado_por=pvx issabel v0.1.4\ngerado_em=2026-09-14T17:00:00\n"
            with tarfile.open(path, "a") as tar:
                info = tarfile.TarInfo(ops.MANIFEST_MEMBER)
                info.size = len(manifest)
                tar.addfile(info, io.BytesIO(manifest))

            info = ops.inspect_backup(path)

        self.assertEqual(info["manifest"]["gerado_por"], "pvx issabel v0.1.4")
        self.assertEqual(info["manifest"]["gerado_em"], "2026-09-14T17:00:00")

    def test_raises_a_clean_error_for_a_file_that_is_not_a_valid_backup(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = str(Path(tmp_dir, "not-a-backup.tar"))
            Path(path).write_text("nem um tar de verdade")
            with self.assertRaises(ops.IssabelBackupError):
                ops.inspect_backup(path)


class RestoreManualComponentTest(unittest.TestCase):
    def _build_backup_with_dir_tgz(self, path, member_name, dirname, files):
        with tempfile.TemporaryDirectory() as work_dir:
            src_root = Path(work_dir, "src")
            for relpath, content in files.items():
                p = src_root / dirname / relpath
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content)

            inner_path = Path(work_dir, "inner.tgz")
            with tarfile.open(inner_path, "w:gz") as inner:
                inner.add(src_root / dirname, arcname=dirname)

            with tarfile.open(path, "w") as outer:
                outer.add(inner_path, arcname=member_name)

    def test_extracts_the_matching_tgz_into_the_destination_path_under_root(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            backup_path = str(Path(tmp_dir, "x.tar"))
            self._build_backup_with_dir_tgz(
                backup_path, "backup/etc.asterisk.sgp.tgz", "sgp", {"foo.conf": "hello"},
            )
            root = Path(tmp_dir, "root")
            with patch("backup_ops.subprocess.run") as mock_run:
                restored = ops.restore_manual_component(backup_path, "int_sgp", root=str(root))

            self.assertEqual((root / "etc/asterisk/sgp/foo.conf").read_text(), "hello")
            self.assertIn("/etc/asterisk/sgp", restored)

    def test_chowns_each_restored_directory_to_asterisk(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            backup_path = str(Path(tmp_dir, "x.tar"))
            self._build_backup_with_dir_tgz(
                backup_path, "backup/etc.asterisk.sgp.tgz", "sgp", {"foo.conf": "hello"},
            )
            root = Path(tmp_dir, "root")
            with patch("backup_ops.subprocess.run") as mock_run:
                ops.restore_manual_component(backup_path, "int_sgp", root=str(root))

        args = mock_run.call_args.args[0]
        self.assertEqual(args[:2], ["chown", "-R"])
        self.assertIn("asterisk:asterisk", args)
        self.assertIn(f"{root}/etc/asterisk/sgp", args)

    def test_silently_skips_directories_absent_from_the_backup(self):
        # mesmo comportamento não-fatal do backupComponent_dir original:
        # diretório que não existia na hora do backup (mustExist implícito)
        # simplesmente não aparece no tarball -- não é erro.
        with tempfile.TemporaryDirectory() as tmp_dir:
            backup_path = str(Path(tmp_dir, "x.tar"))
            self._build_backup_with_dir_tgz(
                backup_path, "backup/etc.asterisk.sgp.tgz", "sgp", {"foo.conf": "hello"},
            )
            root = Path(tmp_dir, "root")
            with patch("backup_ops.subprocess.run"):
                restored = ops.restore_manual_component(backup_path, "int_ixcsoft", root=str(root))

        self.assertEqual(restored, [])


class InstalledIssabelVersionTest(unittest.TestCase):
    def test_returns_the_version_from_the_hyphenated_product_package(self):
        # achado ao vivo (2026-10): "issabelpbx" (sem hífen) pode nem estar
        # instalado numa central Issabel 5 real -- "issabel-pbx" (com
        # hífen) é o pacote de produto de verdade.
        with patch("backup_ops.subprocess.run", return_value=_run_result(stdout="5.0.0")):
            self.assertEqual(ops.installed_issabel_version(), "5.0.0")

    def test_falls_back_to_issabelpbx_when_the_hyphenated_package_is_not_installed(self):
        with patch("backup_ops.subprocess.run", side_effect=[
            _run_result(returncode=1), _run_result(stdout="4.0.0"),
        ]):
            self.assertEqual(ops.installed_issabel_version(), "4.0.0")

    def test_falls_back_to_the_meta_package_when_neither_pbx_package_is_installed(self):
        with patch("backup_ops.subprocess.run", side_effect=[
            _run_result(returncode=1), _run_result(returncode=1), _run_result(stdout="5.0.0"),
        ]):
            self.assertEqual(ops.installed_issabel_version(), "5.0.0")

    def test_returns_none_when_rpm_query_fails(self):
        with patch("backup_ops.subprocess.run", return_value=_run_result(returncode=1)):
            self.assertIsNone(ops.installed_issabel_version())


class RestartAsteriskTest(unittest.TestCase):
    def test_calls_asterisk_core_restart(self):
        with patch("backup_ops.subprocess.run", return_value=_run_result()) as mock_run:
            ops.restart_asterisk()
        self.assertEqual(mock_run.call_args.args[0], ["asterisk", "-rx", "core restart now"])

    def test_returns_none_on_a_clean_exit(self):
        with patch("backup_ops.subprocess.run", return_value=_run_result()):
            self.assertIsNone(ops.restart_asterisk())

    def test_returns_the_real_reason_when_it_fails(self):
        with patch("backup_ops.subprocess.run", return_value=_run_result(returncode=1, stderr="No such file or directory")):
            self.assertEqual(ops.restart_asterisk(), "No such file or directory")


if __name__ == "__main__":
    unittest.main()
