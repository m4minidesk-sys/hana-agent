"""Kiro CLI delegation tool."""

import logging
import re
import subprocess
from pathlib import Path

from strands import tool

logger = logging.getLogger(__name__)


@tool
def kiro_delegate(task: str, working_directory: str = ".") -> str:
    """Delegate a coding task to Kiro CLI.

    Args:
        task: Task description for Kiro.
        working_directory: Working directory for Kiro execution.

    Returns:
        Kiro's response with ANSI codes stripped.
    """
    kiro_path = Path("~/.local/bin/kiro-cli").expanduser()

    if not kiro_path.exists():
        return f"Error: Kiro CLI not found at {kiro_path}. Install it first."

    cmd = [str(kiro_path), "chat", "--no-interactive", "--trust-all-tools", task]

    try:
        result = subprocess.run(
            cmd,
            cwd=working_directory,
            capture_output=True,
            text=True,
            timeout=300,
        )
        output = result.stdout + result.stderr
        # Strip ANSI codes
        clean_output = re.sub(r"\x1b\[[0-9;]*m", "", output)
        logger.info("Kiro CLI output (%d chars): %s", len(clean_output), clean_output[:500])
        return clean_output

    except subprocess.TimeoutExpired:
        logger.warning("Kiro CLI timeout after 300s")
        return "Error: Kiro CLI timed out after 300 seconds."
    except Exception as e:
        logger.error("Kiro CLI error: %s", e)
        return f"Error: {e}"
