"""Allow running the bot with ``python -m propshield``."""

import sys

from propshield.cli import main

if __name__ == "__main__":
    sys.exit(main())
