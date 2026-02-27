"""Tests for MCP server integration."""

import sys
from contextlib import contextmanager
from unittest.mock import MagicMock, call, patch

import pytest

from yui.tools.mcp_integration import (
    MCPConfigError,
    MCPConnectionError,
    MCPManager,
    MCPServerConfig,
    _build_transport,
    _validate_command,
    _validate_env,
    _validate_url,
    connect_mcp_servers,
)

pytestmark = pytest.mark.component



# ─── MCPServerConfig validation tests ──────────────────────────────────


class TestMCPServerConfig:
    """Tests for MCPServerConfig dataclass validation."""

    def test_valid_stdio_config(self):
        """Valid stdio config passes validation."""
        config = MCPServerConfig(
            name="test-server",
            transport="stdio",
            command=["python", "-m", "my_server"],
        )
        assert config.name == "test-server"
        assert config.transport == "stdio"
        assert config.command == ["python", "-m", "my_server"]

    def test_valid_sse_config(self):
        """Valid SSE config passes validation."""
        config = MCPServerConfig(
            name="sse-server",
            transport="sse",
            url="http://localhost:8080/sse",
        )
        assert config.url == "http://localhost:8080/sse"

    def test_valid_streamable_http_config(self):
        """Valid streamable_http config passes validation."""
        config = MCPServerConfig(
            name="http-server",
            transport="streamable_http",
            url="http://localhost:9090/mcp",
        )
        assert config.transport == "streamable_http"

    def test_unsupported_transport_raises(self):
        """Unsupported transport raises MCPConfigError."""
        with pytest.raises(MCPConfigError, match="unsupported transport 'grpc'"):
            MCPServerConfig(name="bad", transport="grpc")

    def test_stdio_without_command_raises(self):
        """stdio transport without command raises MCPConfigError."""
        with pytest.raises(MCPConfigError, match="requires 'command' field"):
            MCPServerConfig(name="no-cmd", transport="stdio", command=None)

    def test_stdio_with_empty_command_raises(self):
        """stdio transport with empty command list raises MCPConfigError."""
        with pytest.raises(MCPConfigError, match="requires 'command' field"):
            MCPServerConfig(name="empty-cmd", transport="stdio", command=[])

    def test_sse_without_url_raises(self):
        """sse transport without url raises MCPConfigError."""
        with pytest.raises(MCPConfigError, match="requires 'url' field"):
            MCPServerConfig(name="no-url", transport="sse", url=None)

    def test_streamable_http_without_url_raises(self):
        """streamable_http transport without url raises MCPConfigError."""
        with pytest.raises(MCPConfigError, match="requires 'url' field"):
            MCPServerConfig(name="no-url", transport="streamable_http", url=None)

    def test_auto_connect_default_true(self):
        """auto_connect defaults to True."""
        config = MCPServerConfig(
            name="test", transport="stdio", command=["echo"]
        )
        assert config.auto_connect is True

    def test_env_and_headers_optional(self):
        """env and headers are optional fields."""
        config = MCPServerConfig(
            name="test",
            transport="stdio",
            command=["echo"],
            env={"FOO": "bar"},
        )
        assert config.env == {"FOO": "bar"}
        assert config.headers is None


# ─── MCPManager.load_configs tests ─────────────────────────────────────


class TestMCPManagerLoadConfigs:
    """Tests for config loading and parsing."""

    def test_load_empty_servers(self):
        """Empty servers list returns empty configs."""
        manager = MCPManager()
        configs = manager.load_configs({"servers": []})
        assert configs == []
        assert manager.configured_servers == []

    def test_load_single_stdio_server(self):
        """Single stdio server parsed correctly."""
        manager = MCPManager()
        mcp_config = {
            "servers": [
                {
                    "name": "my-mcp",
                    "transport": "stdio",
                    "command": ["python", "-m", "server"],
                }
            ]
        }
        configs = manager.load_configs(mcp_config)
        assert len(configs) == 1
        assert configs[0].name == "my-mcp"
        assert manager.configured_servers == ["my-mcp"]

    def test_load_multiple_servers(self):
        """Multiple servers with different transports parsed correctly."""
        manager = MCPManager()
        mcp_config = {
            "servers": [
                {"name": "stdio-srv", "transport": "stdio", "command": ["echo"]},
                {"name": "sse-srv", "transport": "sse", "url": "http://localhost:8080/sse"},
            ]
        }
        configs = manager.load_configs(mcp_config)
        assert len(configs) == 2
        assert manager.configured_servers == ["stdio-srv", "sse-srv"]

    def test_duplicate_names_raises(self):
        """Duplicate server names raise MCPConfigError."""
        manager = MCPManager()
        mcp_config = {
            "servers": [
                {"name": "dup", "transport": "stdio", "command": ["echo"]},
                {"name": "dup", "transport": "stdio", "command": ["cat"]},
            ]
        }
        with pytest.raises(MCPConfigError, match="Duplicate MCP server name"):
            manager.load_configs(mcp_config)

    def test_servers_not_list_raises(self):
        """Non-list servers raises MCPConfigError."""
        manager = MCPManager()
        with pytest.raises(MCPConfigError, match="must be a list"):
            manager.load_configs({"servers": "bad"})

    def test_server_entry_not_dict_raises(self):
        """Non-dict server entry raises MCPConfigError."""
        manager = MCPManager()
        with pytest.raises(MCPConfigError, match="must be a mapping"):
            manager.load_configs({"servers": ["not-a-dict"]})

    def test_server_missing_name_raises(self):
        """Server without name raises MCPConfigError."""
        manager = MCPManager()
        with pytest.raises(MCPConfigError, match="'name' is required"):
            manager.load_configs({"servers": [{"transport": "stdio", "command": ["echo"]}]})

    def test_auto_connect_inherits_from_global(self):
        """auto_connect inherits from global mcp config if not set per server."""
        manager = MCPManager()
        mcp_config = {
            "auto_connect": False,
            "servers": [
                {"name": "srv", "transport": "stdio", "command": ["echo"]},
            ],
        }
        configs = manager.load_configs(mcp_config)
        assert configs[0].auto_connect is False

    def test_auto_connect_per_server_overrides_global(self):
        """Per-server auto_connect overrides global setting."""
        manager = MCPManager()
        mcp_config = {
            "auto_connect": False,
            "servers": [
                {"name": "srv", "transport": "stdio", "command": ["echo"], "auto_connect": True},
            ],
        }
        configs = manager.load_configs(mcp_config)
        assert configs[0].auto_connect is True

    def test_load_no_servers_key(self):
        """Missing 'servers' key returns empty list."""
        manager = MCPManager()
        configs = manager.load_configs({})
        assert configs == []


# ─── MCPManager connect/disconnect tests ───────────────────────────────


class TestMCPManagerConnectDisconnect:
    """Tests for connect and disconnect operations (mocked)."""

    def _setup_manager_with_config(self) -> MCPManager:
        """Helper to create a manager with a configured server."""
        manager = MCPManager()
        manager.load_configs({
            "servers": [
                {"name": "test-srv", "transport": "stdio", "command": ["echo", "hello"]},
            ]
        })
        return manager

    @patch("yui.tools.mcp_integration.MCPClient")
    def test_connect_success(self, mock_mcp_class):
        """Successful connection stores client and returns it."""
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_mcp_class.return_value = mock_client

        manager = self._setup_manager_with_config()
        result = manager.connect("test-srv")

        assert result is mock_client
        assert "test-srv" in manager.connected_servers
        mock_client.__enter__.assert_called_once()

    @patch("yui.tools.mcp_integration.MCPClient")
    def test_connect_already_connected_returns_existing(self, mock_mcp_class):
        """Connecting to already-connected server returns existing client."""
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_mcp_class.return_value = mock_client

        manager = self._setup_manager_with_config()
        first = manager.connect("test-srv")
        second = manager.connect("test-srv")

        assert first is second
        # MCPClient should only be constructed once
        assert mock_mcp_class.call_count == 1

    def test_connect_unconfigured_raises(self):
        """Connecting to unconfigured server raises MCPConfigError."""
        manager = MCPManager()
        with pytest.raises(MCPConfigError, match="not configured"):
            manager.connect("nonexistent")

    @patch("yui.tools.mcp_integration.MCPClient")
    def test_connect_failure_raises_connection_error(self, mock_mcp_class):
        """Connection failure wraps in MCPConnectionError."""
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(side_effect=RuntimeError("connection refused"))
        mock_mcp_class.return_value = mock_client

        manager = self._setup_manager_with_config()
        with pytest.raises(MCPConnectionError, match="connection refused"):
            manager.connect("test-srv")

        assert "test-srv" not in manager.connected_servers

    @patch("yui.tools.mcp_integration.MCPClient")
    def test_disconnect_success(self, mock_mcp_class):
        """Successful disconnect removes client and calls __exit__."""
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_mcp_class.return_value = mock_client

        manager = self._setup_manager_with_config()
        manager.connect("test-srv")
        manager.disconnect("test-srv")

        assert "test-srv" not in manager.connected_servers
        mock_client.__exit__.assert_called_once_with(None, None, None)

    def test_disconnect_not_connected_raises(self):
        """Disconnecting non-connected server raises MCPConfigError."""
        manager = self._setup_manager_with_config()
        with pytest.raises(MCPConfigError, match="not connected"):
            manager.disconnect("test-srv")

    @patch("yui.tools.mcp_integration.MCPClient")
    def test_disconnect_all(self, mock_mcp_class):
        """disconnect_all cleans up all connected servers."""
        mock_client1 = MagicMock()
        mock_client1.__enter__ = MagicMock(return_value=mock_client1)
        mock_client1.__exit__ = MagicMock(return_value=None)

        mock_client2 = MagicMock()
        mock_client2.__enter__ = MagicMock(return_value=mock_client2)
        mock_client2.__exit__ = MagicMock(return_value=None)

        mock_mcp_class.side_effect = [mock_client1, mock_client2]

        manager = MCPManager()
        manager.load_configs({
            "servers": [
                {"name": "srv1", "transport": "stdio", "command": ["echo"]},
                {"name": "srv2", "transport": "stdio", "command": ["cat"]},
            ]
        })
        manager.connect("srv1")
        manager.connect("srv2")

        assert len(manager.connected_servers) == 2
        manager.disconnect_all()
        assert len(manager.connected_servers) == 0

    @patch("yui.tools.mcp_integration.MCPClient")
    def test_disconnect_error_logged_not_raised(self, mock_mcp_class):
        """disconnect_all logs but doesn't raise on __exit__ errors."""
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(side_effect=RuntimeError("cleanup failed"))
        mock_mcp_class.return_value = mock_client

        manager = self._setup_manager_with_config()
        manager.connect("test-srv")

        # Should not raise
        manager.disconnect_all()
        assert len(manager.connected_servers) == 0


# ─── MCPManager.get_tools tests ───────────────────────────────────────


class TestMCPManagerGetTools:
    """Tests for tool retrieval."""

    @patch("yui.tools.mcp_integration.MCPClient")
    def test_get_tools_returns_connected_clients(self, mock_mcp_class):
        """get_tools returns list of connected MCPClient instances."""
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_mcp_class.return_value = mock_client

        manager = MCPManager()
        manager.load_configs({
            "servers": [
                {"name": "srv", "transport": "stdio", "command": ["echo"]},
            ]
        })
        manager.connect("srv")

        tools = manager.get_tools()
        assert len(tools) == 1
        assert tools[0] is mock_client

    def test_get_tools_empty_when_no_connections(self):
        """get_tools returns empty list when no servers connected."""
        manager = MCPManager()
        assert manager.get_tools() == []


# ─── MCPManager.get_server_info / list_servers tests ──────────────────


class TestMCPManagerServerInfo:
    """Tests for server info and listing."""

    def test_get_server_info_configured(self):
        """get_server_info returns correct info for configured server."""
        manager = MCPManager()
        manager.load_configs({
            "servers": [
                {"name": "test", "transport": "sse", "url": "http://localhost:8080"},
            ]
        })
        info = manager.get_server_info("test")
        assert info["name"] == "test"
        assert info["transport"] == "sse"
        assert info["connected"] is False
        assert info["url"] == "http://localhost:8080"

    def test_get_server_info_unconfigured_raises(self):
        """get_server_info raises for unconfigured server."""
        manager = MCPManager()
        with pytest.raises(MCPConfigError, match="not configured"):
            manager.get_server_info("nope")

    def test_list_servers_returns_all(self):
        """list_servers returns info for all configured servers."""
        manager = MCPManager()
        manager.load_configs({
            "servers": [
                {"name": "a", "transport": "stdio", "command": ["echo"]},
                {"name": "b", "transport": "sse", "url": "http://x"},
            ]
        })
        servers = manager.list_servers()
        assert len(servers) == 2
        assert servers[0]["name"] == "a"
        assert servers[1]["name"] == "b"


# ─── _build_transport tests ───────────────────────────────────────────


class TestBuildTransport:
    """Tests for transport callable builder."""

    def test_build_stdio_transport_returns_callable(self):
        """Stdio transport builds a callable."""
        config = MCPServerConfig(
            name="test", transport="stdio", command=["python", "-m", "server"]
        )
        transport = _build_transport(config)
        assert callable(transport)

    def test_build_sse_transport_returns_callable(self):
        """SSE transport builds a callable."""
        config = MCPServerConfig(
            name="test", transport="sse", url="http://localhost:8080/sse"
        )
        transport = _build_transport(config)
        assert callable(transport)

    def test_build_streamable_http_transport_returns_callable(self):
        """streamable_http transport builds a callable."""
        config = MCPServerConfig(
            name="test", transport="streamable_http", url="http://localhost:9090/mcp"
        )
        transport = _build_transport(config)
        assert callable(transport)

    @patch("yui.tools.mcp_integration.stdio_client")
    def test_stdio_transport_callable_passes_params(self, mock_stdio):
        """Stdio transport callable passes correct StdioServerParameters."""
        config = MCPServerConfig(
            name="test",
            transport="stdio",
            command=["python", "-m", "my_server"],
            env={"KEY": "val"},
        )
        transport = _build_transport(config)
        transport()

        mock_stdio.assert_called_once()
        params = mock_stdio.call_args[0][0]
        assert params.command == "python"
        assert params.args == ["-m", "my_server"]
        assert params.env == {"KEY": "val"}

    @patch("yui.tools.mcp_integration.sse_client")
    def test_sse_transport_callable_passes_params(self, mock_sse):
        """SSE transport callable passes url and headers."""
        config = MCPServerConfig(
            name="test",
            transport="sse",
            url="http://localhost:8080/sse",
            headers={"Authorization": "Bearer token"},
        )
        transport = _build_transport(config)
        transport()

        mock_sse.assert_called_once_with(
            url="http://localhost:8080/sse",
            headers={"Authorization": "Bearer token"},
        )


# ─── connect_mcp_servers (high-level) tests ───────────────────────────


class TestConnectMCPServers:
    """Tests for the high-level connect_mcp_servers function."""

    def test_no_mcp_config_returns_empty_manager(self):
        """No MCP config returns manager with no servers."""
        manager = connect_mcp_servers({})
        assert manager.connected_servers == []
        assert manager.configured_servers == []

    def test_empty_servers_returns_empty_manager(self):
        """Empty servers list returns manager with no connections."""
        manager = connect_mcp_servers({"mcp": {"servers": []}})
        assert manager.connected_servers == []

    @patch("yui.tools.mcp_integration.MCPClient")
    def test_auto_connect_connects_server(self, mock_mcp_class):
        """Server with auto_connect=True is connected automatically."""
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_mcp_class.return_value = mock_client

        config = {
            "mcp": {
                "servers": [
                    {"name": "auto-srv", "transport": "stdio", "command": ["echo"]},
                ]
            }
        }
        manager = connect_mcp_servers(config)
        assert "auto-srv" in manager.connected_servers

    def test_auto_connect_false_skips_server(self):
        """Server with auto_connect=False is not connected automatically."""
        config = {
            "mcp": {
                "auto_connect": False,
                "servers": [
                    {"name": "manual-srv", "transport": "stdio", "command": ["echo"]},
                ],
            }
        }
        manager = connect_mcp_servers(config)
        assert "manual-srv" not in manager.connected_servers
        assert "manual-srv" in manager.configured_servers

    @patch("yui.tools.mcp_integration.MCPClient")
    def test_connection_failure_is_graceful(self, mock_mcp_class):
        """Connection failure doesn't crash — returns partial manager."""
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(side_effect=RuntimeError("fail"))
        mock_mcp_class.return_value = mock_client

        config = {
            "mcp": {
                "servers": [
                    {"name": "bad-srv", "transport": "stdio", "command": ["fail"]},
                ]
            }
        }
        manager = connect_mcp_servers(config)
        # Should not raise, but server is not connected
        assert "bad-srv" not in manager.connected_servers
        assert "bad-srv" in manager.configured_servers

    def test_invalid_config_is_graceful(self):
        """Invalid config returns empty manager instead of crashing."""
        config = {
            "mcp": {
                "servers": "not-a-list",
            }
        }
        manager = connect_mcp_servers(config)
        assert manager.connected_servers == []

    @patch("yui.tools.mcp_integration.MCPClient")
    def test_partial_connection(self, mock_mcp_class):
        """If one server fails, others still connect."""
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            mock = MagicMock()
            if call_count[0] == 1:
                mock.__enter__ = MagicMock(side_effect=RuntimeError("fail"))
            else:
                mock.__enter__ = MagicMock(return_value=mock)
            return mock

        mock_mcp_class.side_effect = side_effect

        config = {
            "mcp": {
                "servers": [
                    {"name": "bad", "transport": "stdio", "command": ["fail"]},
                    {"name": "good", "transport": "stdio", "command": ["echo"]},
                ]
            }
        }
        manager = connect_mcp_servers(config)
        assert "bad" not in manager.connected_servers
        assert "good" in manager.connected_servers


# ─── Config integration tests ─────────────────────────────────────────


class TestConfigIntegration:
    """Tests for MCP config section in the full config."""

    def test_default_config_has_mcp_section(self):
        """Default config includes empty mcp section."""
        from yui.config import DEFAULT_CONFIG

        assert "mcp" in DEFAULT_CONFIG
        assert DEFAULT_CONFIG["mcp"]["servers"] == []
        assert DEFAULT_CONFIG["mcp"]["auto_connect"] is True

    def test_load_config_with_mcp_servers(self, tmp_path):
        """Config file with MCP servers loads correctly."""
        import yaml
        from yui.config import load_config

        config_data = {
            "mcp": {
                "servers": [
                    {
                        "name": "my-server",
                        "transport": "stdio",
                        "command": ["python", "-m", "server"],
                    }
                ]
            }
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config_data))

        config = load_config(str(config_file))
        assert len(config["mcp"]["servers"]) == 1
        assert config["mcp"]["servers"][0]["name"] == "my-server"


# ─── Validation function tests ────────────────────────────────────────


class TestValidateCommand:
    """Tests for _validate_command security checks."""

    def test_valid_command_passes(self):
        """Normal command passes validation."""
        # Should not raise
        _validate_command("test", ["python", "-m", "my_server"])

    def test_shell_metacharacters_rejected(self):
        """Commands with shell metacharacters are rejected."""
        with pytest.raises(MCPConfigError, match="shell metacharacters"):
            _validate_command("test", ["echo", "foo; rm -rf /"])

    def test_pipe_rejected(self):
        """Pipe character is rejected."""
        with pytest.raises(MCPConfigError, match="shell metacharacters"):
            _validate_command("test", ["cat", "foo|bar"])

    def test_backtick_rejected(self):
        """Backtick is rejected."""
        with pytest.raises(MCPConfigError, match="shell metacharacters"):
            _validate_command("test", ["echo", "`whoami`"])

    def test_dollar_rejected(self):
        """Dollar sign expansion is rejected."""
        with pytest.raises(MCPConfigError, match="shell metacharacters"):
            _validate_command("test", ["echo", "$HOME"])


class TestValidateUrl:
    """Tests for _validate_url security checks."""

    def test_valid_http_url(self):
        """http:// URL passes."""
        _validate_url("test", "http://localhost:8080/sse")

    def test_valid_https_url(self):
        """https:// URL passes."""
        _validate_url("test", "https://example.com/mcp")

    def test_file_scheme_rejected(self):
        """file:// scheme is rejected."""
        with pytest.raises(MCPConfigError, match="not allowed"):
            _validate_url("test", "file:///etc/passwd")

    def test_ftp_scheme_rejected(self):
        """ftp:// scheme is rejected."""
        with pytest.raises(MCPConfigError, match="not allowed"):
            _validate_url("test", "ftp://example.com")

    def test_no_hostname_rejected(self):
        """URL without hostname is rejected."""
        with pytest.raises(MCPConfigError, match="no hostname"):
            _validate_url("test", "http:///path")


class TestValidateEnv:
    """Tests for _validate_env security checks."""

    def test_safe_env_passes(self):
        """Safe environment variables pass."""
        _validate_env("test", {"MY_TOKEN": "abc", "API_KEY": "xyz"})

    def test_path_blocked(self):
        """PATH override is blocked."""
        with pytest.raises(MCPConfigError, match="blocked variable"):
            _validate_env("test", {"PATH": "/tmp/evil"})

    def test_ld_preload_blocked(self):
        """LD_PRELOAD is blocked."""
        with pytest.raises(MCPConfigError, match="blocked variable"):
            _validate_env("test", {"LD_PRELOAD": "/tmp/evil.so"})

    def test_dyld_insert_blocked(self):
        """DYLD_INSERT_LIBRARIES is blocked (macOS)."""
        with pytest.raises(MCPConfigError, match="blocked variable"):
            _validate_env("test", {"DYLD_INSERT_LIBRARIES": "/tmp/evil.dylib"})

    def test_env_with_blocked_vars_raises(self):
        """Server config with blocked env vars raises during init."""
        with pytest.raises(MCPConfigError, match="blocked variable"):
            MCPServerConfig(
                name="bad-env",
                transport="stdio",
                command=["echo"],
                env={"PATH": "/evil"},
            )
