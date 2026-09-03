import traceback

import click
import questionary

from pvx.cli import discover_installed_modules
from pvx.interactive import widgets
from pvx.interactive.auto_menu import build_choices
from pvx.interactive.inputs import ask_select

SCREEN_BY_SYSTEM_CHOICE = {"módulos": "modules", "logs": "logs", "tema": "theme"}

_SYSTEM_DESCRIPTIONS = {
    "módulos": "instalar, atualizar, remover e listar módulos",
    "logs": "ver o log do core e de cada módulo, ao vivo",
    "tema": "trocar a cor de destaque do menu",
    "sair": "fecha o pvx",
}


class RootScreen:
    def render(self):
        widgets.banner()
        modules = discover_installed_modules()

        def indented(value, description=None):
            return questionary.Choice(title=f"  {value}", value=value, description=description)

        # "sair" fica dentro do grupo Sistema, como último item -- não mais
        # separado no fim da lista inteira.
        choices = [
            questionary.Separator("Sistema"),
            *(indented(c, _SYSTEM_DESCRIPTIONS[c]) for c in SCREEN_BY_SYSTEM_CHOICE),
            indented("sair", _SYSTEM_DESCRIPTIONS["sair"]),
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
