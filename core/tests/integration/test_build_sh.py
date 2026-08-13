"""Builda core.pyz localmente (precisa rede/pip) e valida o .pyz num
container limpo, SEM click/questionary/rich pré-instalados -- só prova
que o vendoring funcionou de verdade."""
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CORE_DIR = REPO_ROOT / "core"


class BuildShTest(unittest.TestCase):
    def test_built_core_pyz_runs_standalone_without_vendored_deps_preinstalled(self):
        build = subprocess.run(
            ["sh", "build.sh"], cwd=CORE_DIR, capture_output=True, text=True, timeout=180,
        )
        self.assertEqual(build.returncode, 0, msg=f"stdout:\n{build.stdout}\nstderr:\n{build.stderr}")

        pyz_path = CORE_DIR / "dist" / "core.pyz"
        self.assertTrue(pyz_path.exists())

        result = subprocess.run(
            [
                "docker", "run", "--rm",
                "-v", f"{pyz_path}:/core.pyz:ro",
                "python:3.11-slim",
                "python3", "/core.pyz", "--version",
            ],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}")
        self.assertIn("pvx", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
