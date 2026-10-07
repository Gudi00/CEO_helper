"""PyInstaller entry point for the standalone `lms-tool` binary."""

import sys

from src.cli import main

if __name__ == "__main__":
    sys.exit(main())
