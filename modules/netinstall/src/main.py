import sys

import click

from pvx import config as pvx_config
from pvx.interactive import widgets
from pvx.interactive.inputs import ask_checkbox, ask_confirm, ask_select, ask_text
from pvx.modules.base import PvxModule

import credentials
import defaults
import install_steps
import os_ops
import preflight


def _is_interactive():
    return sys.stdin.isatty()


def _pyz_path():
    # assets estáticos (repos, control_panel) vêm de DENTRO do .pyz (ver assets.py) -- no
    # host instalado só module.pyz+manifest.json existem no diretório do módulo.
    return str(pvx_config.modules_dir() / "netinstall" / "module.pyz")


def _state_dir():
    return pvx_config.modules_dir() / "netinstall" / "state"


def _default_tweaks():
    return [key for key, (on, _) in defaults.TWEAKS_CATALOG.items() if on]


_PREFLIGHT_STATUS_WORD = {"ok": "ok", "warn": "atenção", "error": "falha"}


def _preflight_reporter():
    # imprime cada checagem assim que ela resolve (nunca bufferiza tudo pra printar de
    # uma vez só -- ver preflight.check(), reporta na ordem real de execução). "rede" é a
    # única de fato lenta (curl real) -- só ela ganha spinner, via fase "pending".
    pending_steps = {}

    def report(label, status, detail=None):
        if status == "pending":
            step = widgets.step(f"Verificando {label}...")
            step.__enter__()
            pending_steps[label] = step
            return
        step = pending_steps.pop(label, None)
        if step is not None:
            step.__exit__(None, None, None)
        text = f"{label}: {_PREFLIGHT_STATUS_WORD[status]}"
        if detail:
            text += f" ({detail})"
        widgets.check_result(text, status)

    return report


def _run_step(logger, message, done_message, fn, *args):
    # duração já fica visível ao vivo no spinner (widgets.step -- TimeElapsedColumn),
    # repetir no sucesso é redundante. Log em arquivo é o que sobrevive depois de a
    # sessão fechar (achado ao vivo: instalação falhou e não sobrou log acionável).
    logger.info(f"iniciando: {message}")
    with widgets.step(message):
        try:
            fn(*args)
        except Exception as e:
            logger.error(f"falhou: {message} -- {e}")
            raise
    logger.info(f"concluído: {done_message}")
    widgets.success(done_message)


COFFEE_ART = r"""
                       .
                        `:.
                          `:.
                  .:'     ,::
                 .:'      ;:'
                 ::      ;:'
                  :    .:'
                   `.  :.
          _________________________
         : _ _ _ _ _ _ _ _ _ _ _ _ :
     ,---:".".".".".".".".".".".".":
    : ,'"`::.:.:.:.:.:.:.:.:.:.:.::'
    `.`.  `:-===-===-===-===-===-:'
      `.`-._:                   :
        `-.__`.               ,'
    ,--------`"`-------------'--------.
     `"--.__                   __.--"'
            `""-------------""'
"""


def _run_issabel5(logger, flags, interactive):
    errors, warnings = preflight.check(
        min_version=8, force=flags["force"], report=_preflight_reporter(),
    )
    for warning in warnings:
        click.echo(f"aviso: {warning}")
    if errors:
        raise click.ClickException("\n".join(errors))

    astver = flags["astver"]
    if astver is None:
        if not interactive:
            raise click.ClickException("informe --astver (16 ou 18).")
        choice = ask_select("Versão do Asterisk:", list(defaults.ASTERISK_VERSIONS), default="18")
        if choice is None:
            return
        astver = choice

    # não pergunta mais (usuário leigo não entendia os itens) -- sempre o default.
    addpkgs_keys = list(flags["addpkgs"]) or [k for k, v in defaults.ADDPKGS_DEFAULTS.items() if v]
    extra_packages = [pkg for key in addpkgs_keys for pkg in defaults.ADDPKGS[key]]

    tweak_keys = list(flags["tweaks"])
    if not tweak_keys:
        if interactive:
            selected = ask_checkbox(
                "Tweaks Phonevox:", list(defaults.TWEAKS_CATALOG), defaults=_default_tweaks(),
            )
            if selected is None:
                return
            tweak_keys = selected
        else:
            tweak_keys = _default_tweaks()

    def _resolve_password(flag_value, prompt):
        if flag_value:
            return flag_value
        if not interactive:
            return os_ops.gen_password()
        entered = ask_text(f"{prompt} (enter vazio = gera aleatória):")
        if entered is None:
            return None  # esc -- aborta
        return entered or os_ops.gen_password()

    sql_pw = _resolve_password(flags["sql_password"], "Senha do MySQL root")
    if sql_pw is None:
        return
    web_pw = _resolve_password(flags["web_password"], "Senha admin da interface Web")
    if web_pw is None:
        return

    click.echo("Resumo:")
    click.echo(f"  Asterisk: {astver}")
    click.echo(f"  Pacotes extras: {', '.join(addpkgs_keys) or 'nenhum'}")
    click.echo(f"  Tweaks: {', '.join(tweak_keys) or 'nenhum'}")
    if not flags["yes"] and not ask_confirm("Prosseguir com a instalação?", default=False):
        click.echo("Operação cancelada.")
        return

    pyz_path = _pyz_path()
    major = preflight.version_major()

    _run_step(
        logger,
        "Adicionando repositórios (epel, tmux/htop, Issabel 5)...", "Repositórios adicionados.",
        install_steps.add_repos, pyz_path,
    )
    _run_step(
        logger,
        "Preparando o sistema (SELinux, usuário asterisk)...", "Sistema preparado.",
        install_steps.prepare_system,
    )
    _run_step(
        logger,
        f"Habilitando repo Remi + módulo PHP (RHEL/Rocky {major})...", "Repo Remi + PHP habilitados.",
        install_steps.enable_php_remi, major,
    )
    widgets.message("esta é a etapa mais demorada -- aproveita, relaxa e pega um café.")
    click.echo(COFFEE_ART)
    click.echo()
    logger.info("iniciando: instalação de pacotes (base + Asterisk + Issabel)")
    with widgets.step_with_log("Instalando pacotes (base + Asterisk + Issabel)...") as s:
        try:
            install_steps.install_packages(
                astver, extra_packages, on_line=s.feed, skip_clean=flags["skip_clean"],
            )
        except Exception as e:
            logger.error(f"falhou: instalação de pacotes -- {e}")
            raise
    logger.info("concluído: pacotes instalados")
    widgets.success("Pacotes instalados.")
    _run_step(
        logger,
        "Pós-instalação (mariadb, httpd, firewalld, asterisk)...", "Pós-instalação concluída.",
        install_steps.post_install,
    )

    _run_step(
        logger,
        "Instalando o schema do banco de dados...", "Schema do banco instalado.",
        install_steps.install_db,
    )
    if "operator-panel" in tweak_keys:
        _run_step(
            logger,
            "Instalando o painel do operador...", "Painel do operador instalado.",
            install_steps.install_control_panel, pyz_path,
        )
    tz = flags["timezone"] or defaults.DEFAULT_TIMEZONE
    _run_step(
        logger, f"Ajustando timezone ({tz})...", f"Timezone ajustado para {tz}.",
        install_steps.set_timezone, tz,
    )

    _run_step(
        logger,
        "Definindo senhas de acesso (MySQL root / admin Web)...", "Senhas de acesso definidas.",
        install_steps.set_passwords, sql_pw, web_pw,
    )
    cred_path = credentials.save_credentials(str(_state_dir()), "issabel5", sql_pw, web_pw)
    widgets.success(f"credenciais salvas em {cred_path} (0600)")

    if flags["reboot"]:
        click.echo("reiniciando o servidor...")
        logger.info("reiniciando o servidor.")
        os_ops.run_cmd(["reboot"])
    else:
        click.echo("--no-reboot -- reinicie manualmente quando quiser.")


class NetinstallModule(PvxModule):
    name = "netinstall"
    version = "0.1.19"

    def cli_group(self):
        @click.group(name="netinstall")
        def group():
            pass

        @group.command(name="issabel5", help="instala o Issabel 5 do zero (Rocky/RHEL).")
        @click.option("--astver", type=click.Choice(defaults.ASTERISK_VERSIONS), default=None)
        @click.option("--addpkgs", multiple=True, type=click.Choice(list(defaults.ADDPKGS)))
        @click.option("--tweaks", multiple=True, type=click.Choice(list(defaults.TWEAKS_CATALOG)))
        @click.option("--timezone", default=None)
        @click.option("--sql-password", default=None)
        @click.option("--web-password", default=None)
        @click.option("--force", is_flag=True)
        @click.option(
            "--skip-clean", is_flag=True,
            help="pula 'dnf clean all' antes de instalar pacotes -- só pra reinstalar rápido "
                 "numa máquina de teste já usada, nunca numa máquina nova de verdade",
        )
        @click.option("--yes", is_flag=True)
        @click.option("--reboot/--no-reboot", default=True)
        def issabel5_cmd(**flags):
            logger = self.get_logger()
            interactive = _is_interactive()
            try:
                _run_issabel5(logger, flags, interactive)
            except click.ClickException:
                # já pausa centralmente no router (root.py) -- pausar aqui também
                # dobraria o "pressione enter" na cara do usuário.
                raise
            else:
                if interactive:
                    widgets.pause()

        return group


cli = NetinstallModule()
