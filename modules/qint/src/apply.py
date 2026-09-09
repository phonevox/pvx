from pathlib import Path

import deploy
import dialplan
import fetch
import history
import placeholders
import reload as reload_
import template_patch

# achado ao vivo, conferido contra o instalador bash original (installer.sh, sgp): o
# layout remoto não é plano por categoria -- agi/php/exten vivem dentro de "files/",
# "exten" é o nome real da pasta de dialplan, "audios" é plural, e toda categoria tem
# mais um nível "<tipo>" (ixcsoft/sgp) antes do conteúdo de fato. O destino também usa
# o nome do tipo como subpasta (nunca "qint"), e o include real aponta pro arquivo
# "phonevox.conf" (que encadeia os outros .conf), não direto pro macro.
PHP_FILENAME = "config.php"
MACRO_FILENAME = "phonevox-macros-atendimento.conf"
INCLUDE_FILENAME = "phonevox.conf"
MOH_CLASS_NAME = "sfx-teclado-digitando"
_REMOTE_CATEGORY_PATHS = {
    "agi": "files/agi",
    "php": "files/php",
    "dialplan": "files/exten",
    "moh": "moh",
    "audio": "audios",
}
CONTENT_CATEGORIES = tuple(_REMOTE_CATEGORY_PATHS)


def apply(config, remote_base, cache_root, destination_base_dirs, history_path):
    tipo = config["type"]
    versao = config.get("sftp_versao", "recent")
    sftp_info = {
        "user": config["sftp_user"],
        "host": config["sftp_host"],
        "port": config.get("sftp_port", 22),
    }

    cache_dir = fetch.prepare_cache_dir(cache_root, tipo, versao)
    fetch.fetch(sftp_info, remote_base, tipo, versao, cache_dir)

    source_dirs = {
        category: str(Path(cache_dir) / remote_path / tipo)
        for category, remote_path in _REMOTE_CATEGORY_PATHS.items()
    }

    php_path = Path(source_dirs["php"]) / PHP_FILENAME
    php_path.write_text(
        template_patch.patch(php_path.read_text(), placeholders.build_php_replacements(config))
    )

    macro_path = Path(source_dirs["dialplan"]) / MACRO_FILENAME
    macro_path.write_text(
        template_patch.patch(macro_path.read_text(), placeholders.build_macro_replacements(config))
    )

    deploy.deploy(source_dirs, destination_base_dirs, tipo)

    dialplan_dir = Path(destination_base_dirs["dialplan"])
    include_filename = f"{tipo}/{INCLUDE_FILENAME}"

    extensions_path = dialplan_dir / "extensions_custom.conf"
    extensions_text = extensions_path.read_text() if extensions_path.exists() else ""
    extensions_path.write_text(
        dialplan.add_include_if_absent(
            extensions_text, dialplan.build_include_line(tipo, include_filename)
        )
    )

    # deploy() joga o conteúdo de "moh" pra <base>/<tipo>/, preservando a subpasta
    # MOH_CLASS_NAME de dentro do source -- o "directory=" tem que apontar pra ela de
    # verdade (confirmado contra o instalador bash original), senão o Asterisk nunca
    # acha os áudios.
    moh_sound_dir = Path(destination_base_dirs["moh"]) / tipo / MOH_CLASS_NAME
    moh_conf_path = dialplan_dir / "musiconhold_custom.conf"
    moh_conf_text = moh_conf_path.read_text() if moh_conf_path.exists() else ""
    moh_conf_path.write_text(
        dialplan.add_moh_class_if_absent(moh_conf_text, MOH_CLASS_NAME, str(moh_sound_dir))
    )

    reloaded = reload_.reload_dialplan()
    history.append(history_path, f"apply {tipo} {versao}")

    return {"applied": True, "reloaded": reloaded}
