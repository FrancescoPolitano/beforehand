"""`python3 -m beforehand_cli` — the same as the `beforehand` console script."""
import sys

sys.dont_write_bytecode = True

from beforehand_cli.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
