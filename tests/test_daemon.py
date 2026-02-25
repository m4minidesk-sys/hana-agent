"""Tests for HANA daemon runner."""

from __future__ import annotations

import plistlib
from pathlib import Path

import pytest

from hana.runtime.daemon import DaemonRunner, LAUNCHD_LABEL


class TestDaemonPlistGeneration:
    """Tests for launchd plist generation."""

    def test_generate_plist_creates_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Override PLIST_DIR to use tmp
        monkeypatch.setattr("hana.runtime.daemon.PLIST_DIR", tmp_path)

        plist_path = DaemonRunner.generate_plist(
            config_path="~/.hana/config.yaml",
            python_path="/opt/homebrew/bin/python3",
            log_dir=str(tmp_path / "logs"),
        )

        assert Path(plist_path).exists()

    def test_plist_content_is_valid(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("hana.runtime.daemon.PLIST_DIR", tmp_path)

        plist_path = DaemonRunner.generate_plist(
            config_path="~/.hana/config.yaml",
            python_path="/opt/homebrew/bin/python3",
            log_dir=str(tmp_path / "logs"),
        )

        with open(plist_path, "rb") as f:
            plist = plistlib.load(f)

        assert plist["Label"] == LAUNCHD_LABEL
        assert plist["RunAtLoad"] is True
        assert plist["KeepAlive"] is True
        assert "/opt/homebrew/bin/python3" in plist["ProgramArguments"]
        assert "--daemon" in plist["ProgramArguments"]
        assert "PATH" in plist["EnvironmentVariables"]

    def test_plist_has_throttle_interval(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("hana.runtime.daemon.PLIST_DIR", tmp_path)

        plist_path = DaemonRunner.generate_plist(
            python_path="/usr/bin/python3",
            log_dir=str(tmp_path / "logs"),
        )

        with open(plist_path, "rb") as f:
            plist = plistlib.load(f)

        assert plist["ThrottleInterval"] == 30
