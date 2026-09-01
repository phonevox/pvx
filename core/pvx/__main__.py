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
        except KeyboardInterrupt:
            click.echo("\npvx encerrado.")


if __name__ == "__main__":
    main()
