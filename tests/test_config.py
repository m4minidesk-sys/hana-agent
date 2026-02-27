"""Tests for yui.config — AC-06, AC-07."""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from yui.config import ConfigError, DEFAULT_CONFIG, load_config

pytestmark = pytest.mark.unit



class TestLoadConfig:
    """AC-06: config.yaml is loaded and validated on startup."""

    def test_returns_defaults_when_no_file(self, tmp_path):
        """No config file → returns DEFAULT_CONFIG."""
        config = load_config(str(tmp_path / "nonexistent.yaml"))
        assert config["model"]["model_id"] == DEFAULT_CONFIG["model"]["model_id"]
        assert config["model"]["region"] == DEFAULT_CONFIG["model"]["region"]

    def test_loads_valid_yaml(self, tmp_path):
        """Valid YAML merges with defaults."""
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(yaml.dump({"model": {"max_tokens": 8192}}))
        config = load_config(str(cfg_file))
        assert config["model"]["max_tokens"] == 8192
        # Other defaults still present
        assert config["model"]["model_id"] == DEFAULT_CONFIG["model"]["model_id"]

    def test_deep_merge_preserves_nested(self, tmp_path):
        """User config merges deeply — doesn't replace entire sections."""
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(yaml.dump({
            "tools": {"shell": {"timeout_seconds": 60}}
        }))
        config = load_config(str(cfg_file))
        assert config["tools"]["shell"]["timeout_seconds"] == 60
        # allowlist should still be the default
        assert "ls" in config["tools"]["shell"]["allowlist"]

    def test_empty_yaml_returns_defaults(self, tmp_path):
        """Empty YAML file → defaults."""
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("")
        config = load_config(str(cfg_file))
        assert config == DEFAULT_CONFIG


class TestConfigValidation:
    """AC-07: Invalid config produces a clear error message and exits."""

    def test_invalid_yaml_raises_config_error(self, tmp_path):
        """Broken YAML syntax → ConfigError."""
        cfg_file = tmp_path / "bad.yaml"
        cfg_file.write_text(": invalid: yaml: [")
        with pytest.raises(ConfigError, match="Invalid YAML"):
            load_config(str(cfg_file))

    def test_non_dict_yaml_raises_config_error(self, tmp_path):
        """YAML that parses to list → ConfigError."""
        cfg_file = tmp_path / "list.yaml"
        cfg_file.write_text("- just\n- a\n- list\n")
        with pytest.raises(ConfigError, match="must be a YAML mapping"):
            load_config(str(cfg_file))

    def test_missing_model_id_raises(self, tmp_path):
        """model.model_id set to empty → ConfigError."""
        cfg_file = tmp_path / "bad_model.yaml"
        cfg_file.write_text(yaml.dump({"model": {"model_id": ""}}))
        with pytest.raises(ConfigError, match="model.model_id"):
            load_config(str(cfg_file))

    def test_missing_region_raises(self, tmp_path):
        """model.region set to empty → ConfigError."""
        cfg_file = tmp_path / "bad_region.yaml"
        cfg_file.write_text(yaml.dump({"model": {"region": ""}}))
        with pytest.raises(ConfigError, match="model.region"):
            load_config(str(cfg_file))

    def test_allowlist_not_list_raises(self, tmp_path):
        """tools.shell.allowlist is a string → ConfigError."""
        cfg_file = tmp_path / "bad_allow.yaml"
        cfg_file.write_text(yaml.dump({
            "tools": {"shell": {"allowlist": "not-a-list"}}
        }))
        with pytest.raises(ConfigError, match="allowlist must be a list"):
            load_config(str(cfg_file))
