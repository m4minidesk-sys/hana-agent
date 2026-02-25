"""Safe git operations tool."""

import logging
import shlex
import subprocess

from strands import tool

logger = logging.getLogger(__name__)

ALLOWED_SUBCOMMANDS = {
    "status",
    "add",
    "commit",
    "push",
    "log",
    "diff",
    "branch",
    "checkout",
    "pull",
    "fetch",
    "stash",
    "reset",
}

BLOCKED_PATTERNS = [
    "push --force",
    "push -f",
    "reset --hard",
    "clean -f",
]


@tool
def git_tool(subcommand: str, args: str = "", working_directory: str = ".") -> str:
    """Execute git operations safely.

    Args:
        subcommand: Git subcommand (status, add, commit, etc.).
        args: Additional arguments for the subcommand.
        working_directory: Working directory for git execution.

    Returns:
        Git command output.
    """
    if subcommand not in ALLOWED_SUBCOMMANDS:
        return f"Error: Git subcommand '{subcommand}' not allowed. Allowed: {', '.join(ALLOWED_SUBCOMMANDS)}"

    # Check blocked patterns
    full_cmd = f"{subcommand} {args}".strip()
    for pattern in BLOCKED_PATTERNS:
        if pattern in full_cmd:
            return f"Error: Blocked git operation: {pattern}"

    cmd = ["git", subcommand] + (shlex.split(args) if args else [])

    try:
        result = subprocess.run(
            cmd,
            cwd=working_directory,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout + result.stderr

    except subprocess.TimeoutExpired:
        logger.warning("Git command timeout: %s", full_cmd)
        return "Error: Git command timed out after 30 seconds."
    except Exception as e:
        logger.error("Git command error: %s", e)
        return f"Error: {e}"
