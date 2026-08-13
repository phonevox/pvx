import sys

from pvx.cli import cli
from pvx.interactive.router import run_interactive


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv:
        cli.main(args=argv, prog_name="pvx")
    else:
        run_interactive()


if __name__ == "__main__":
    main()
