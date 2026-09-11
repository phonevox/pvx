import traceback

import click
import questionary

from pvx import build_info, self_update, update_check
from pvx import version as pvx_version
from pvx.cli import discover_installed_modules
from pvx.interactive import widgets
from pvx.interactive.auto_menu import build_choices
from pvx.interactive.inputs import ask_confirm, ask_select
from pvx.interactive.screens.module_update import update_modules
from pvx.logging_.setup import get_module_logger

SCREEN_BY_SYSTEM_CHOICE = {"módulos": "modules", "logs": "logs", "tema": "theme"}
# "versão"/"atualizar" não empurram tela própria -- são ações de uma linha só,
# tratadas inline (ver RootScreen.render()), igual "sair".
_SYSTEM_ACTIONS = list(SCREEN_BY_SYSTEM_CHOICE) + ["versão", "atualizar", "sair"]

_SYSTEM_DESCRIPTIONS = {
    "módulos": "instalar, atualizar, remover e listar módulos",
    "logs": "ver o log do core e de cada módulo, ao vivo",
    "tema": "personalizar cor, símbolos e formato do menu",
    "versão": "mostra a versão instalada do pvx",
    "atualizar": "atualiza o pvx pra versão mais recente",
    "sair": "fecha o pvx",
}


def _core_logger():
    return get_module_logger("core")


def _show_version():
    # installed_version() lê o .pyz em disco -- __version__ em memória fica
    # preso na versão antiga depois de um self-update na mesma sessão.
    current = pvx_version.installed_version()
    channel = build_info.describe()
    version_string = f"{current} ({channel})" if channel else current
    widgets.message(f"pvx {version_string}")
    widgets.pause()


def _update_core():
    channel = build_info.describe()
    if channel is not None and not ask_confirm(
        f"Você está rodando um build {channel} -- atualizar vai substituir pela "
        "versão oficial mais recente. Continuar?",
        default=False,
    ):
        return

    try:
        with widgets.spinner("Baixando atualização..."):
            version = self_update.self_update()
    except PermissionError:
        _core_logger().error("self-update falhou: sem privilégios de root.")
        widgets.failed("self-update precisa de privilégios de root (rode com sudo).")
        return

    _core_logger().info(f"pvx atualizado pra versão {version}.")
    widgets.success(f"pvx atualizado pra versão {version}.")


_UPDATE_TARGET_DESCRIPTIONS = {
    "tudo": "atualiza o core e todos os módulos instalados",
    "core": "atualiza o pvx em si pra versão mais recente",
    "módulos": "atalho pra pvx > módulos > atualizar",
}


class RootScreen:
    def render(self):
        widgets.banner()
        modules = discover_installed_modules()

        # só no menu interativo -- CLI direta (scripting) nunca passa por
        # RootScreen, então isso não atrapalha automação nenhuma. Cache
        # próprio (ver update_check.py) evita bater no registry a cada
        # redesenho do menu raiz.
        notices = update_check.pending_notices(modules)
        for notice in notices:
            widgets.warning(notice)
        if notices:
            click.echo()

        def indented(value, description=None):
            return questionary.Choice(title=f"  {value}", value=value, description=description)

        # "sair" fica dentro do grupo Sistema, como último item -- não mais
        # separado no fim da lista inteira.
        choices = [
            questionary.Separator("Sistema"),
            *(indented(c, _SYSTEM_DESCRIPTIONS[c]) for c in _SYSTEM_ACTIONS),
        ]
        if modules:
            choices += [
                questionary.Separator(" "),
                questionary.Separator("Módulos"),
                *(indented(name) for name in modules),
            ]

        # sem viewport limitado aqui de propósito -- é o menu mais navegado
        # de todos, lista curta e fixa, scroll atrapalharia mais que ajuda
        # (viewport de 5 é pras listas grandes -- módulos instalados, etc.).
        selected = ask_select("pvx >", choices, window_size=None)
        if selected is None or selected == "sair":
            return "EXIT"

        if selected == "versão":
            _show_version()
            return None

        if selected == "atualizar":
            choices = [
                questionary.Choice(title=v, value=v, description=_UPDATE_TARGET_DESCRIPTIONS[v])
                for v in _UPDATE_TARGET_DESCRIPTIONS
            ] + ["voltar"]
            # sem isso, "pvx >" (já respondida) fica presa na tela junto com
            # "pvx > atualizar >" -- mesmo achado do submenu de tema.
            widgets.clear()
            target = ask_select("pvx > atualizar >", choices)
            if target is None or target == "voltar":
                return None
            if target == "módulos":
                return "modules.update"
            _update_core()
            if target == "tudo":
                update_modules(list(modules))
            widgets.pause()
            return None

        if selected in SCREEN_BY_SYSTEM_CHOICE:
            return SCREEN_BY_SYSTEM_CHOICE[selected]

        module = modules[selected]
        if module.interactive_entry() is not None:
            return f"{selected}.main"

        group = module.cli_group()
        # sem o clear(), o header "pvx > <módulo>" já respondido fica na tela
        # e esse segundo prompt (auto-menu) aparece duplicado embaixo -- o
        # router só limpa ENTRE renders, não no meio de um render() só.
        widgets.clear()
        _run_auto_menu(group, f"pvx > {selected}")
        return None


def _run_auto_menu(group, breadcrumb):
    # loop nesse nível pra sempre: rodar um comando (ou voltar de um
    # subgrupo aninhado) só redesenha ESTE menu de novo -- nunca sobe pro
    # nível anterior sozinho. Só um esc dado NESTE nível sai daqui.
    while True:
        command_name = ask_select(f"{breadcrumb} >", build_choices(group))
        if command_name is None:
            return

        cmd = group.commands[command_name]
        if isinstance(cmd, click.Group):
            widgets.clear()
            _run_auto_menu(cmd, f"{breadcrumb} > {command_name}")
        else:
            try:
                cmd.main(args=[], standalone_mode=False)
            except click.ClickException as e:
                # standalone_mode=False faz o click propagar a exceção crua
                # (MissingParameter, UsageError, ...) em vez de tratar --
                # qualquer módulo com comando de argumento obrigatório
                # crasharia a sessão inteira do menu sem esse guard.
                widgets.message(str(e))
                widgets.pause()
            except click.exceptions.Abort:
                # ctrl-c num prompt (ask_password/ask_text) dentro do comando
                # vira Abort (cmd.main() do click já converte KeyboardInterrupt
                # com standalone_mode=False) -- isso fecha o pvx inteiro (ver
                # NAV_HINT: "ctrl-c fecha o pvx"), não é um crash de módulo pra
                # engolir e continuar o menu.
                raise
            except Exception:
                # catch global: qualquer exceção não tratada de um módulo
                # (ex.: CalledProcessError de um subprocess) não pode
                # derrubar a sessão inteira do menu -- mostra o traceback
                # de verdade (em vermelho, precisa saltar aos olhos) e
                # volta pro mesmo nível, igual o ClickException acima.
                widgets.crash(traceback.format_exc())
                widgets.pause()
        widgets.clear()
