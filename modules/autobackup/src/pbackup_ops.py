import json
import os
import shutil
import tarfile
import tempfile
import urllib.request
import zipfile

REPO = "phonevox/pbackup"
INSTALL_DIR = "/opt/pbackup"
MIN_VERSION = (1, 1, 0)

# pbackup --install cria um symlink em um desses dois caminhos apontando pro
# pbackup.sh real -- resolver o symlink é como a gente acha a raiz de instalação
# de verdade, seja lá onde o técnico tenha extraído o repo (ex.: /root/pbackup).
BIN_PATHS = ("/usr/sbin/pbackup", "/usr/bin/pbackup")


def _parse_version(text):
    text = text.strip().lstrip("vV")
    parts = text.split(".")[:3]
    return tuple(int(p) for p in parts)


def is_supported(version):
    return version is not None and version >= MIN_VERSION


def find_install():
    for path in BIN_PATHS:
        if os.path.islink(path) or os.path.isfile(path):
            real = os.path.realpath(path)
            if os.path.isfile(real):
                return os.path.dirname(real)
    return None


def installed_version(pbackup_root):
    try:
        data = json.loads(open(os.path.join(pbackup_root, "lib", "version.json")).read())
        return _parse_version(data["version"])
    except (OSError, ValueError, KeyError):
        return None


def _download(url):
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read()


def _latest_release_tag():
    data = json.loads(_download(f"https://api.github.com/repos/{REPO}/releases/latest"))
    return data["tag_name"]


def _extract_archive(data, dest_dir, is_zip):
    with tempfile.TemporaryDirectory() as tmp:
        archive_path = os.path.join(tmp, "archive")
        with open(archive_path, "wb") as f:
            f.write(data)

        extract_dir = os.path.join(tmp, "extracted")
        if is_zip:
            with zipfile.ZipFile(archive_path) as zf:
                zf.extractall(extract_dir)
        else:
            with tarfile.open(archive_path) as tf:
                tf.extractall(extract_dir)

        # o tarball/zip do github tem uma única pasta raiz (repo-tag/...) -- o
        # conteúdo de verdade mora dentro dela.
        root = os.path.join(extract_dir, os.listdir(extract_dir)[0])
        os.makedirs(dest_dir, exist_ok=True)
        for name in os.listdir(root):
            src, dst = os.path.join(root, name), os.path.join(dest_dir, name)
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)


def _chmod_scripts(dest_dir):
    for dirpath, _, filenames in os.walk(dest_dir):
        for filename in filenames:
            if filename.endswith(".sh"):
                path = os.path.join(dirpath, filename)
                os.chmod(path, os.stat(path).st_mode | 0o111)


def _ensure_symlink(pbackup_root):
    # pbackup.sh --install pergunta y/n se o symlink já aponta pra outro lugar --
    # sem terminal pra responder isso, o pvx decide sozinho e garante o link certo.
    target = os.path.join(pbackup_root, "pbackup.sh")
    for path in BIN_PATHS:
        if os.path.realpath(path) == os.path.realpath(target):
            continue
        if os.path.lexists(path):
            os.remove(path)
        os.symlink(target, path)


def fresh_install(dest_dir=INSTALL_DIR):
    tag = _latest_release_tag()
    data = _download(f"https://github.com/{REPO}/archive/refs/tags/{tag}.tar.gz")
    _extract_archive(data, dest_dir, is_zip=False)
    _chmod_scripts(dest_dir)
    _ensure_symlink(dest_dir)
    return dest_dir


def update_in_place(pbackup_root):
    # mesma fonte que o próprio pbackup.sh usa no --update: o zip da branch main
    # (não uma tag) -- ver update_all_files() no pbackup.sh original.
    data = _download(f"https://github.com/{REPO}/archive/refs/heads/main.zip")
    _extract_archive(data, pbackup_root, is_zip=True)
    _chmod_scripts(pbackup_root)
