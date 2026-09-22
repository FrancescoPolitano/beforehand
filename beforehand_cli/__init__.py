"""beforehand — installer and command-line front end for the beforehand Claude Code skill."""
import sys

# A run from a source checkout must not leave __pycache__ in the tree (dev/check_generality.sh).
# Set here, before cli.py is imported; this file's own cache is written before it runs, so
# `python3 -B -m beforehand_cli` (or PYTHONDONTWRITEBYTECODE=1) is what keeps a checkout clean.
sys.dont_write_bytecode = True

__version__ = "1.0.0"
