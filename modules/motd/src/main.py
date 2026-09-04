import sys
import time

import click
from rich.console import Console

from pvx.interactive import widgets
from pvx.interactive.inputs import ask_confirm
from pvx.modules.base import PvxModule

import asterisk_info
import autobackup_info
import issabel_info
import profile_hook
import render
import services
import system_info

_INSTALL_HELP = "Instala o banner de login (com barra de status), fazendo backup dos scripts antigos."


def _is_interactive():
    return sys.stdin.isatty()


def gather_data():
    disk = system_info.disk_usage("/")
    memory = system_info.memory_usage()

    asterisk_status = services.daemon_status(("asterisk",), "asterisk")
    mariadb_status = services.daemon_status(("mysql", "mariadb"), "mysqld")

    asterisk_details = None
    if asterisk_status["installed"]:
        # aproximado (GB arredondado -> bytes) -- suficiente pro % que é só
        # indicativo, não precisa da precisão exata do total real do disco.
        disk_total_bytes = disk["total_gb"] * 2**30
        logdir = asterisk_info.find_logdir()
        asterisk_details = {
            "version": asterisk_info.version(),
            "active_calls": asterisk_info.active_calls(),
            "recordings_percent": issabel_info.recordings_percent(disk_total_bytes),
            "recordings_bytes": issabel_info.recordings_bytes(),
            "logs_percent": issabel_info.storage_percent(logdir, disk_total_bytes) if logdir else None,
            "logs_bytes": issabel_info.storage_bytes(logdir) if logdir else None,
            "dialer_percent": issabel_info.dialer_percent(disk_total_bytes),
            "dialer_bytes": issabel_info.dialer_bytes(),
        }

    return {
        "hostname": system_info.hostname(),
        "os_pretty_name": system_info.os_pretty_name() or "N/A",
        "machine_id": system_info.machine_id() or "N/A",
        "ips": system_info.ip_addresses(),
        "open_sessions": system_info.open_sessions(),
        "server_date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "timezone": system_info.timezone_name() or "N/A",
        "uptime": system_info.uptime_human(),
        "load_average": system_info.load_average(),
        "cpu_percent": system_info.cpu_usage_percent(),
        "ram_percent": memory["ram_percent"],
        "swap_percent": memory["swap_percent"],
        "disk_percent": disk["percent"],
        "disk_used_gb": disk["used_gb"],
        "disk_total_gb": disk["total_gb"],
        "asterisk": asterisk_status,
        "mariadb": mariadb_status,
        "asterisk_details": asterisk_details,
        "autobackup": autobackup_info.status(),
    }


class MotdModule(PvxModule):
    name = "motd"
    version = "0.1.10"

    def cli_group(self):
        @click.group(name="motd")
        def group():
            pass

        @group.command(name="show", help="mostra o banner agora -- é o que roda a cada login.")
        def show_cmd():
            # sem logger aqui de propósito: isso executa em TODO login via
            # /etc/profile.d -- logar cada execução lotaria o log à toa (ver
            # CONTEXT.md sobre logging). widgets.pause() é seguro sem gate:
            # ele mesmo detecta CLI direta via sys.argv e não pausa aí --
            # só pausa de verdade navegando "motd > show" no menu interativo.
            data = gather_data()
            Console().print(render.build_banner(data))
            widgets.pause()

        @group.command(name="install", help=_INSTALL_HELP)
        @click.option("--yes", is_flag=True, help="pula a confirmação.")
        def install_cmd(yes):
            logger = self.get_logger()
            interactive = _is_interactive()
            if not yes:
                if not interactive:
                    raise click.ClickException("informe --yes pra confirmar.")
                warning = (
                    "Isso substitui o banner de login atual (scripts antigos são salvos "
                    "num backup antes de sair). Continuar?"
                )
                if not ask_confirm(warning, default=True):
                    widgets.message("nada foi alterado.")
                    return

            result = profile_hook.install()
            logger.info(f"motd install -- hook instalado, backup_dir={result['backup_dir']}")
            if result["backed_up"]:
                widgets.state(
                    f"{len(result['backed_up'])} script(s) antigo(s) salvos em {result['backup_dir']}.", ok=True,
                )
            widgets.success(f"banner instalado em {profile_hook.HOOK_PATH}.")
            if interactive:
                widgets.pause()

        @group.command(name="uninstall", help="remove o banner de login instalado pelo pvx.")
        @click.option("--yes", is_flag=True, help="pula a confirmação.")
        def uninstall_cmd(yes):
            logger = self.get_logger()
            interactive = _is_interactive()
            if not profile_hook.is_installed():
                widgets.message("nada instalado.")
                return

            if not yes:
                if not interactive:
                    raise click.ClickException("informe --yes pra confirmar.")
                if not ask_confirm("Remover o banner de login do pvx?", default=False):
                    widgets.message("nada foi alterado.")
                    return

            profile_hook.uninstall()
            logger.info("motd uninstall -- hook removido.")
            widgets.success("banner removido.")
            if interactive:
                widgets.pause()

        return group


cli = MotdModule()
