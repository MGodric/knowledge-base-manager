#!/usr/bin/env python3
"""Main entry point for knowledge-base-manager unified Python CLI."""

import sys

# Prevent bytecode (.pyc / __pycache__) creation in Skill directory
sys.dont_write_bytecode = True

from kb_core.cli import main

if __name__ == "__main__":
    sys.exit(main())
