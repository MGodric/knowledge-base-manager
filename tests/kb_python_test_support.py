"""Test support utilities for Python kb-core unit tests."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

# Ensure project knowledge-base-manager/scripts is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "knowledge-base-manager" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def create_temp_dir(prefix: str = "kb-test-") -> str:
    """Create a temporary directory under the system temp directory."""
    return tempfile.mkdtemp(prefix=prefix)


def cleanup_dir(path: str) -> None:
    """Safely remove a directory tree."""
    if os.path.exists(path):
        shutil.rmtree(path, ignore_errors=True)


def write_file(path: str, content: str | bytes, encoding: str = "utf-8", newline: str | None = None) -> str:
    """Write content to a file, creating parent directories if needed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if isinstance(content, bytes):
        with open(path, "wb") as f:
            f.write(content)
    else:
        # If newline is specified, write with explicit line endings
        with open(path, "w", encoding=encoding, newline=newline) as f:
            f.write(content)
    return path


def setup_minimal_kb(root_dir: str, content_dir: str = "content", entrypoint: str = "content/index.md") -> str:
    """Setup a valid minimal knowledge base with kb.yaml and entrypoint."""
    os.makedirs(root_dir, exist_ok=True)
    kb_yaml = f"schema_version: 1\ncontent_dir: {content_dir}\nentrypoint: {entrypoint}\n"
    write_file(os.path.join(root_dir, "kb.yaml"), kb_yaml)

    entry_full = os.path.join(root_dir, entrypoint.replace("/", os.sep))
    write_file(entry_full, "# Knowledge Base\n\nWelcome to the knowledge base.\n")
    return root_dir
