import tempfile
import unittest
import zipfile
from pathlib import Path

import assets


def _build_pyz(entries):
    tmp = tempfile.mkdtemp()
    pyz_path = Path(tmp) / "module.pyz"
    with zipfile.ZipFile(pyz_path, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return str(pyz_path)


class ExtractPrefixTest(unittest.TestCase):
    def test_extracts_files_under_prefix_flattening_it(self):
        pyz_path = _build_pyz({
            "main.py": "print('x')",
            "config/repos/Issabel5.repo": "[issabel5]\n",
            "config/repos/Issabel.repo": "[issabel]\n",
            "config/control_panel/index.php": "<?php\n",
        })
        with tempfile.TemporaryDirectory() as dest:
            extracted = assets.extract_prefix(pyz_path, "config/repos", dest)
            self.assertEqual(len(extracted), 2)
            self.assertEqual((Path(dest) / "Issabel5.repo").read_text(), "[issabel5]\n")
            self.assertFalse((Path(dest) / "control_panel").exists())

    def test_returns_empty_list_when_prefix_absent(self):
        pyz_path = _build_pyz({"main.py": "print('x')"})
        with tempfile.TemporaryDirectory() as dest:
            self.assertEqual(assets.extract_prefix(pyz_path, "config/repos", dest), [])

    def test_returns_empty_list_when_pyz_missing(self):
        with tempfile.TemporaryDirectory() as dest:
            self.assertEqual(assets.extract_prefix("/nonexistent/module.pyz", "config/repos", dest), [])

    def test_preserves_nested_subdirectories(self):
        pyz_path = _build_pyz({"config/control_panel/assets/style.css": "body{}"})
        with tempfile.TemporaryDirectory() as dest:
            extracted = assets.extract_prefix(pyz_path, "config/control_panel", dest)
            self.assertEqual(extracted, [str(Path(dest) / "assets" / "style.css")])


if __name__ == "__main__":
    unittest.main()
