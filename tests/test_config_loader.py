"""Tests for HANA config loader."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from hana.runtime.config_loader import (
    DEFAULT_CONFIG,
    _deep_merge,
    _expand_paths,
    _resolve_env_vars,
    load_config,
    load_workspace_files,
)


class TestDeepMerge:
    """Tests for _deep_merge."""

    def test_simple_override(self) -> None:
        base = {"a": 1, "b": 2}
        override = {"b": 3}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 3}

    def test_nested_override(self) -> None:
        base = {"a": {"x": 1, "y": 2}, "b": 3}
        override = {"a": {"y": 99}}
        result = _deep_merge(base, override)
        assert result == {"a": {"x": 1, "y": 99}, "b": 3}

    def test_new_key(self) -> None:
        base = {"a": 1}
        override = {"b": 2}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 2}

    def test_no_mutation(self) -> None:
        base = {"a": {"x": 1}}
        override = {"a": {"x": 2}}
        _deep_merge(base, override)
        assert base == {"a": {"x": 1}}


class TestExpandPaths:
    """Tests for _expand_paths."""

    def test_tilde_expansion(self) -> None:
        config = {"path": "~/test"}
        result = _expand_paths(config)
        assert "~" not in result["path"]
        assert result["path"].endswith("/test")

    def test_nested_expansion(self) -> None:
        config = {"outer": {"inner": "~/nested"}}
        result = _expand_paths(config)
        assert "~" not in result["outer"]["inner"]

    def test_non_path_unchanged(self) -> None:
        config = {"name": "hello"}
        result = _expand_paths(config)
        assert result["name"] == "hello"


class TestResolveEnvVars:
    """Tests for _resolve_env_vars."""

    def test_env_var_resolved(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_VAR", "test_value")
        config = {"key": "${TEST_VAR}"}
        result = _resolve_env_vars(config)
        assert result["key"] == "test_value"

    def test_missing_env_var_empty(self) -> None:
        config = {"key": "${NONEXISTENT_VAR_12345}"}
        result = _resolve_env_vars(config)
        assert result["key"] == ""

    def test_non_env_unchanged(self) -> None:
        config = {"key": "regular_value"}
        result = _resolve_env_vars(config)
        assert result["key"] == "regular_value"


class TestLoadConfig:
    """Tests for load_config."""

    def test_defaults_only(self) -> None:
        config = load_config(None)
        assert config["agent"]["model_id"] == DEFAULT_CONFIG["agent"]["model_id"]
        assert config["tools"]["exec"]["enabled"] is True

    def test_custom_config_file(self, tmp_path: Path) -> None:
        custom = {"agent": {"model_id": "custom-model", "region": "ap-northeast-1"}}
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(custom))

        config = load_config(str(config_file))
        assert config["agent"]["model_id"] == "custom-model"
        assert config["agent"]["region"] == "ap-northeast-1"
        # Defaults should still be present
        assert config["tools"]["exec"]["enabled"] is True

    def test_nonexistent_config_uses_defaults(self) -> None:
        config = load_config("/nonexistent/path/config.yaml")
        assert config["agent"]["model_id"] == DEFAULT_CONFIG["agent"]["model_id"]


class TestLoadWorkspaceFiles:
    """Tests for load_workspace_files."""

    def test_loads_existing_files(self, tmp_path: Path) -> None:
        (tmp_path / "AGENTS.md").write_text("# Agents Rules")
        (tmp_path / "SOUL.md").write_text("# Soul Config")

        config = {
            "workspace": {
                "root": str(tmp_path),
                "agents_md": "AGENTS.md",
                "soul_md": "SOUL.md",
            }
        }

        result = load_workspace_files(config)
        assert result["agents_md"] == "# Agents Rules"
        assert result["soul_md"] == "# Soul Config"

    def test_missing_files_return_empty(self, tmp_path: Path) -> None:
        config = {
            "workspace": {
                "root": str(tmp_path),
                "agents_md": "AGENTS.md",
                "soul_md": "SOUL.md",
            }
        }

        result = load_workspace_files(config)
        assert result["agents_md"] == ""
        assert result["soul_md"] == ""
