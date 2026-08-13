"""Teste de integração do M13 (precisa de Docker), roda à parte:

    cd core && python3 -m unittest discover -s tests/integration -v
"""
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_CORE_URL = "file:///workspace/core/tests/integration/fixtures/fake_core.pyz"


def run_install_in_container(image, command, extra_env=None):
    env_flags = []
    for key, value in {"PVX_CORE_URL": FIXTURE_CORE_URL, **(extra_env or {})}.items():
        env_flags += ["-e", f"{key}={value}"]

    return subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{REPO_ROOT}:/workspace:ro",
            "-w", "/workspace",
            *env_flags,
            image,
            "sh", "-c", command,
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )


class InstallShFreshDebianTest(unittest.TestCase):
    def test_fresh_install_puts_pvx_on_path(self):
        result = run_install_in_container(
            "debian:bookworm-slim",
            "sh install.sh && pvx --version",
        )
        self.assertEqual(
            result.returncode, 0,
            msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        self.assertIn("pvx", result.stdout.lower())

    def test_pvx_works_for_non_root_user_after_install(self):
        result = run_install_in_container(
            "debian:bookworm-slim",
            "sh install.sh && useradd -m testuser && su testuser -c 'pvx --version'",
        )
        self.assertEqual(
            result.returncode, 0,
            msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        self.assertIn("pvx", result.stdout.lower())


class InstallShFailureTest(unittest.TestCase):
    def test_failed_download_leaves_no_pvx_on_path(self):
        result = run_install_in_container(
            "debian:bookworm-slim",
            "sh install.sh; echo INSTALL_EXIT=$?; which pvx || echo NO_PVX_ON_PATH",
            extra_env={"PVX_CORE_URL": "file:///workspace/does-not-exist.pyz"},
        )
        self.assertNotIn(
            "INSTALL_EXIT=0", result.stdout,
            msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        self.assertIn("NO_PVX_ON_PATH", result.stdout)


if __name__ == "__main__":
    unittest.main()
