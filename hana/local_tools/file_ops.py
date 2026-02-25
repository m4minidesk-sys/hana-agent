"""HANA file operations tools — read_file, write_file, edit_file."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from strands import tool

logger = logging.getLogger(__name__)

# Module-level config storage
_tool_config: dict[str, Any] = {}


def configure(config: dict[str, Any]) -> None:
    """Store file tool configuration.

    Args:
        config: The ``tools.file`` section of HANA config.
    """
    global _tool_config
    _tool_config = config


@tool
def read_file(file_path: str, offset: int = 0, limit: int = 0) -> dict[str, Any]:
    """Read the contents of a file.

    Supports reading text files with optional line offset and limit.
    Large files are truncated to configured limits.

    Args:
        file_path: Path to the file (relative to workspace or absolute).
        offset: Line offset to start reading from (0-indexed).
        limit: Maximum number of lines to read (0 = no limit).

    Returns:
        Dictionary with content, lines count, and truncated flag.
    """
    if not _tool_config.get("enabled", True):
        return {"content": "", "lines": 0, "truncated": False, "error": "file tool is disabled"}

    max_size = _tool_config.get("max_read_size", 51200)
    max_lines = _tool_config.get("max_read_lines", 2000)

    path = Path(file_path).expanduser()

    if not path.exists():
        return {"content": "", "lines": 0, "truncated": False, "error": f"File not found: {file_path}"}

    if not path.is_file():
        return {"content": "", "lines": 0, "truncated": False, "error": f"Not a file: {file_path}"}

    try:
        file_size = path.stat().st_size

        # Check if binary
        with open(path, "rb") as f:
            chunk = f.read(8192)
            if b"\x00" in chunk:
                return {
                    "content": f"[Binary file: {file_size} bytes]",
                    "lines": 0,
                    "truncated": False,
                }

        with open(path, encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()

        total_lines = len(all_lines)

        # Apply offset and limit
        if offset > 0:
            all_lines = all_lines[offset:]
        effective_limit = limit if limit > 0 else max_lines
        truncated = len(all_lines) > effective_limit
        all_lines = all_lines[:effective_limit]

        content = "".join(all_lines)

        # Truncate by size
        if len(content) > max_size:
            content = content[:max_size]
            truncated = True

        return {
            "content": content,
            "lines": total_lines,
            "truncated": truncated,
        }

    except Exception as exc:
        logger.error("Failed to read file %s: %s", file_path, exc)
        return {"content": "", "lines": 0, "truncated": False, "error": str(exc)}


@tool
def write_file(file_path: str, content: str, create_dirs: bool = True) -> dict[str, Any]:
    """Write content to a file, creating it if it doesn't exist.

    Creates parent directories automatically if requested.

    Args:
        file_path: Path to the file.
        content: Content to write.
        create_dirs: Whether to auto-create parent directories (default True).

    Returns:
        Dictionary with the final path and bytes written.
    """
    if not _tool_config.get("enabled", True):
        return {"path": "", "bytes_written": 0, "error": "file tool is disabled"}

    path = Path(file_path).expanduser()

    try:
        if create_dirs:
            path.parent.mkdir(parents=True, exist_ok=True)

        path.write_text(content, encoding="utf-8")
        bytes_written = path.stat().st_size

        logger.info("Wrote %d bytes to %s", bytes_written, path)
        return {"path": str(path), "bytes_written": bytes_written}

    except Exception as exc:
        logger.error("Failed to write file %s: %s", file_path, exc)
        return {"path": str(path), "bytes_written": 0, "error": str(exc)}


@tool
def edit_file(file_path: str, old_text: str, new_text: str) -> dict[str, Any]:
    """Replace exact text in a file (surgical edit).

    The old_text must match exactly (including whitespace).

    Args:
        file_path: Path to the file.
        old_text: Exact text to find.
        new_text: Text to replace with.

    Returns:
        Dictionary with the path and number of replacements.
    """
    if not _tool_config.get("enabled", True):
        return {"path": "", "replacements": 0, "error": "file tool is disabled"}

    path = Path(file_path).expanduser()

    if not path.exists():
        return {"path": str(path), "replacements": 0, "error": f"File not found: {file_path}"}

    try:
        content = path.read_text(encoding="utf-8")
        count = content.count(old_text)

        if count == 0:
            return {
                "path": str(path),
                "replacements": 0,
                "error": "old_text not found in file",
            }

        new_content = content.replace(old_text, new_text)
        path.write_text(new_content, encoding="utf-8")

        logger.info("Edited %s: %d replacement(s)", path, count)
        return {"path": str(path), "replacements": count}

    except Exception as exc:
        logger.error("Failed to edit file %s: %s", file_path, exc)
        return {"path": str(path), "replacements": 0, "error": str(exc)}
