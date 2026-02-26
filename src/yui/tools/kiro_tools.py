"""Kiro CLI tools — review and implement via Kiro CLI subprocess.

AC-67: kiro_review delegates file review and returns structured findings.
AC-68: kiro_implement delegates implementation with spec file input.
AC-78: Startup availability check with clear error message.
"""

import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

from strands import tool

logger = logging.getLogger(__name__)

# Kiro CLI binary resolution: PATH lookup → fallback to known location
KIRO_CLI_PATH: str = shutil.which("kiro-cli") or str(
    Path("~/.local/bin/kiro-cli").expanduser()
)

MAX_OUTPUT_CHARS = 50_000

# ANSI escape pattern — covers SGR, cursor movement, etc.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    return _ANSI_RE.sub("", text)


def _truncate(text: str, max_chars: int = MAX_OUTPUT_CHARS) -> str:
    """Truncate text to max_chars with indicator."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n... [truncated]"


def check_kiro_available() -> bool:
    """Check if Kiro CLI is available at startup (AC-78).

    Returns True if found, False with logged error if not installed.
    Does NOT raise — callers decide whether to proceed.
    """
    path = Path(KIRO_CLI_PATH).expanduser()
    if path.exists() and os.access(str(path), os.X_OK):
        logger.info("Kiro CLI found at %s", path)
        return True

    # Also check via which (covers PATH-available binaries)
    which_result = shutil.which("kiro-cli")
    if which_result:
        logger.info("Kiro CLI found via PATH at %s", which_result)
        return True

    logger.error(
        "Kiro CLI not found. Install it with: "
        "curl -fsSL https://kiro.dev/install | bash  "
        "(expected at %s or in PATH)",
        KIRO_CLI_PATH,
    )
    return False


def _run_kiro_cli(
    prompt: str,
    cwd: str = ".",
    timeout: int = 120,
) -> str:
    """Run Kiro CLI with a prompt and return cleaned output.

    Shared implementation for kiro_review and kiro_implement.
    Uses --no-interactive and --trust-all-tools flags.

    Args:
        prompt: The prompt/instruction to send to Kiro.
        cwd: Working directory for the subprocess.
        timeout: Timeout in seconds.

    Returns:
        Cleaned, truncated output from Kiro CLI.

    Raises:
        FileNotFoundError: If Kiro CLI binary is not found.
        subprocess.TimeoutExpired: If execution exceeds timeout.
    """
    kiro_path = Path(KIRO_CLI_PATH).expanduser()
    if not kiro_path.exists():
        raise FileNotFoundError(
            f"Kiro CLI not found at {kiro_path}. "
            "Install it with: curl -fsSL https://kiro.dev/install | bash"
        )

    # Security: prompt is passed as a single argument, not shell-expanded
    cmd = [str(kiro_path), "chat", "--no-interactive", "--trust-all-tools", prompt]

    env = {**os.environ, "BYPASS_TOOL_CONSENT": "true"}

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=cwd,
        env=env,
    )

    # Combine stdout + stderr, strip ANSI, truncate
    output = result.stdout + (result.stderr or "")
    output = _strip_ansi(output)
    output = _truncate(output)

    return output


@tool
def kiro_review(file_path: str, review_focus: str = "general") -> str:
    """Delegate file review to Kiro CLI and return structured findings (AC-67).

    Asks Kiro to review the specified file with a focus area, returning
    findings classified as Critical / Major / Minor.

    Args:
        file_path: Path to the file to review.
        review_focus: Aspect to focus on (e.g. "security", "error handling",
                      "technical feasibility", "missing edge cases").

    Returns:
        Structured review output with Critical/Major/Minor findings,
        or an error message if Kiro CLI is unavailable or times out.
    """
    abs_path = str(Path(file_path).resolve())

    prompt = (
        f"Review the file at {abs_path} with focus on: {review_focus}. "
        "Classify each finding as Critical, Major, or Minor. "
        "Format: [SEVERITY] ID: description. Suggestion: fix."
    )

    cwd = str(Path(abs_path).parent) if os.path.dirname(abs_path) else "."

    try:
        output = _run_kiro_cli(prompt, cwd=cwd, timeout=120)
        logger.info("kiro_review completed (%d chars)", len(output))
        return output
    except FileNotFoundError as e:
        return f"Error: {e}"
    except subprocess.TimeoutExpired:
        logger.warning("kiro_review timed out after 120s for %s", file_path)
        return f"Error: Kiro CLI timed out reviewing {file_path} (120s limit)."
    except Exception as e:
        logger.error("kiro_review failed: %s", e)
        return f"Error: kiro_review failed — {e}"


@tool
def kiro_implement(spec_path: str, task_description: str) -> str:
    """Delegate implementation to Kiro CLI with a spec file as input (AC-68).

    Kiro reads the spec and implements according to the task description.

    Args:
        spec_path: Path to the specification / requirements file.
        task_description: What to implement (concise instruction).

    Returns:
        Kiro CLI output describing what was implemented,
        or an error message on failure.
    """
    abs_spec = str(Path(spec_path).resolve())

    prompt = (
        f"Read the spec at {abs_spec} and implement: {task_description}. "
        "Follow the spec precisely. Write tests where applicable. "
        "Report what files were created or modified."
    )

    cwd = str(Path(abs_spec).parent) if os.path.dirname(abs_spec) else "."

    try:
        output = _run_kiro_cli(prompt, cwd=cwd, timeout=180)
        logger.info("kiro_implement completed (%d chars)", len(output))
        return output
    except FileNotFoundError as e:
        return f"Error: {e}"
    except subprocess.TimeoutExpired:
        logger.warning("kiro_implement timed out for spec %s", spec_path)
        return f"Error: Kiro CLI timed out implementing from {spec_path} (180s limit)."
    except Exception as e:
        logger.error("kiro_implement failed: %s", e)
        return f"Error: kiro_implement failed — {e}"
