"""Tests for yui.cli — AC-01, AC-08."""

import io
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


class TestCLIStartup:
    """AC-01: python -m yui starts a CLI REPL that accepts user input."""

    def test_repl_starts_and_exits_on_eof(self):
        """REPL shows banner, accepts EOF (Ctrl+D) gracefully."""
        from yui.cli import main

        captured = io.StringIO()
        with patch("sys.stdin", io.StringIO("")), \
             patch("sys.stdout", captured), \
             patch("sys.argv", ["yui"]):
            main()

        output = captured.getvalue()
        assert "結（Yui）" in output
        assert "Goodbye" in output

    def test_repl_skips_empty_input(self):
        """Empty lines are skipped, REPL continues."""
        from yui.cli import main

        # Three empty lines then EOF
        captured = io.StringIO()
        with patch("sys.stdin", io.StringIO("\n\n\n")), \
             patch("sys.stdout", captured), \
             patch("sys.argv", ["yui"]):
            main()

        output = captured.getvalue()
        assert "結（Yui）" in output
        assert "Goodbye" in output


class TestReadlineHistory:
    """AC-08: CLI supports readline history (up arrow recalls previous input)."""

    def test_history_file_path(self):
        """History file is set to ~/.yui/.yui_history."""
        from yui.cli import HISTORY_FILE
        assert ".yui" in str(HISTORY_FILE)
        assert "history" in str(HISTORY_FILE).lower()

    def test_history_max_length(self):
        """History max length is reasonable."""
        from yui.cli import HISTORY_MAX_LENGTH
        assert HISTORY_MAX_LENGTH >= 100
        assert HISTORY_MAX_LENGTH <= 10000
