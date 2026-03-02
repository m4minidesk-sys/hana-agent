"""Kiro CLI runner for L3 execution.

Wraps kiro-cli chat commands with --no-interactive --trust-all-tools.
"""

import subprocess
from pathlib import Path
from typing import Any, Dict, List


class KiroRunner:
    """Executes Kiro CLI commands and captures output."""

    def __init__(self, kiro_path: str = "kiro-cli"):
        self.kiro_path = kiro_path

    def build_command(self, persona: str, instruction: str) -> List[str]:
        """Build kiro-cli chat command with required flags."""
        return [
            self.kiro_path,
            "chat",
            "--no-interactive",
            "--trust-all-tools",
            "--agent",
            persona,
            instruction,
        ]

    def run(
        self,
        persona: str,
        instruction: str,
        output_path: Path,
        timeout: int = 300,
    ) -> Dict[str, Any]:
        """Execute kiro-cli and save output to {persona}.md."""
        cmd = self.build_command(persona, instruction)
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        # Save stdout/stderr to output file
        with output_path.open("w", encoding="utf-8") as f:
            f.write(f"# Kiro CLI Output: {persona}\n\n")
            f.write(f"## Command\n```\n{' '.join(cmd)}\n```\n\n")
            f.write(f"## stdout\n```\n{result.stdout}\n```\n\n")
            f.write(f"## stderr\n```\n{result.stderr}\n```\n\n")
            f.write(f"## Exit Code\n{result.returncode}\n")

        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
