import sys
import traceback

import click

from pvx.cli import cli
from pvx.interactive import widgets
from pvx.interactive.router import run_interactive


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv:
        try:
            cli.main(args=argv, prog_name="pvx")
        except SystemExit:
            raise
        except Exception:
            # catch global: mesma classe de bug do menu interativo, aqui pra
            # chamada direta (`pvx <modulo> <comando>`) -- click só trata
            # ClickException sozinho, qualquer outra exceção saía crua.
            widgets.crash(traceback.format_exc())
            sys.exit(1)
    else:
        try:
            run_interactive()
        except (KeyboardInterrupt, click.exceptions.Abort):
            # Abort: ctrl-c num prompt dentro de um comando de módulo (ver
            # root.py/router.py) chega até aqui como Abort, não
            # KeyboardInterrupt puro (cmd.main() do click já faz essa
            # conversão) -- mesmo encerramento limpo pros dois casos.
            click.echo("\npvx encerrado.")


if __name__ == "__main__":
    main()
