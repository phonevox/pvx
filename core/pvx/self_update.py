import hashlib
import json
import shutil
import urllib.request

from pvx import config


def self_update():
    with urllib.request.urlopen(config.core_manifest_url()) as response:
        manifest = json.loads(response.read())

    with urllib.request.urlopen(config.core_update_url()) as response:
        data = response.read()

    actual_checksum = hashlib.sha256(data).hexdigest()
    expected_checksum = manifest.get("checksum_sha256")
    if actual_checksum != expected_checksum:
        raise ValueError(
            f"checksum não bate no self-update: "
            f"esperado {expected_checksum}, obtido {actual_checksum}"
        )

    lib_path = config.core_lib_path()
    tmp_path = lib_path.with_suffix(".tmp")
    tmp_path.write_bytes(data)
    tmp_path.replace(lib_path)

    return manifest.get("version")


def uninstall(purge=False):
    lib_path = config.core_lib_path()
    lib_path.unlink(missing_ok=True)
    try:
        lib_path.parent.rmdir()
    except OSError:
        pass

    config.pvx_bin_path().unlink(missing_ok=True)
    config.pvx_bin_symlink_path().unlink(missing_ok=True)

    if purge:
        shutil.rmtree(config.pvx_home(), ignore_errors=True)
