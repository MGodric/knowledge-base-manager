#!/usr/bin/env python3
"""Main entry point for knowledge-base-manager unified Python CLI."""

from pathlib import Path
import sys

# Prevent bytecode (.pyc / __pycache__) creation in Skill directory
sys.dont_write_bytecode = True

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from kb_core.cli import main

if __name__ == "__main__":
    sys.exit(main())
