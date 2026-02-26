"""MCP server integration for Yui.

Connects to MCP servers defined in config.yaml and provides their tools
to the Strands Agent. Supports stdio, sse, and streamable_http transports.
"""

import logging
import re
import shutil
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from mcp import StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client
from strands.tools.mcp import MCPClient

logger = logging.getLogger(__name__)

# Supported transport types
SUPPORTED_TRANSPORTS = ("stdio", "sse", "streamable_http")

# Allowed URL schemes for SSE/HTTP transports
_ALLOWED_URL_SCHEMES = ("http", "https")

# Blocked environment variable names that could be used for injection
_BLOCKED_ENV_VARS = frozenset({
    "PATH", "LD_PRELOAD", "LD_LIBRARY_PATH", "DYLD_INSERT_LIBRARIES",
    "DYLD_LIBRARY_PATH", "PYTHONPATH", "NODE_PATH", "HOME", "USER",
    "SHELL", "TERM", "DISPLAY",
})


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server."""

    name: str
    transport: str
    command: list[str] | None = None
    env: dict[str, str] | None = None
    url: str | None = None
    headers: dict[str, str] | None = None
    auto_connect: bool = True

    def __post_init__(self) -> None:
        """Validate server configuration."""
        if self.transport not in SUPPORTED_TRANSPORTS:
            raise MCPConfigError(
                f"Server '{self.name}': unsupported transport '{self.transport}'. "
                f"Must be one of: {', '.join(SUPPORTED_TRANSPORTS)}"
            )

        if self.transport == "stdio":
            if not self.command or len(self.command) == 0:
                raise MCPConfigError(
                    f"Server '{self.name}': stdio transport requires 'command' field"
                )
            _validate_command(self.name, self.command)
        elif self.transport in ("sse", "streamable_http"):
            if not self.url:
                raise MCPConfigError(
                    f"Server '{self.name}': {self.transport} transport requires 'url' field"
                )
            _validate_url(self.name, self.url)

        if self.env:
            _validate_env(self.name, self.env)


class MCPConfigError(Exception):
    """Raised when MCP configuration is invalid."""


class MCPConnectionError(Exception):
    """Raised when MCP server connection fails."""


class MCPManager:
    """Manages MCP server connections and their lifecycle.

    Provides connect/disconnect/list operations and collects tools
    from connected servers for agent integration.
    """

    def __init__(self) -> None:
        self._clients: dict[str, MCPClient] = {}
        self._configs: dict[str, MCPServerConfig] = {}

    @property
    def connected_servers(self) -> list[str]:
        """Return names of currently connected servers."""
        return list(self._clients.keys())

    @property
    def configured_servers(self) -> list[str]:
        """Return names of all configured servers."""
        return list(self._configs.keys())

    def load_configs(self, mcp_config: dict[str, Any]) -> list[MCPServerConfig]:
        """Parse MCP config section and store server configurations.

        Args:
            mcp_config: The 'mcp' section from config.yaml.

        Returns:
            List of parsed server configurations.

        Raises:
            MCPConfigError: If config is malformed.
        """
        servers_raw = mcp_config.get("servers", [])
        if not isinstance(servers_raw, list):
            raise MCPConfigError("mcp.servers must be a list")

        configs: list[MCPServerConfig] = []
        seen_names: set[str] = set()

        for i, srv in enumerate(servers_raw):
            if not isinstance(srv, dict):
                raise MCPConfigError(f"mcp.servers[{i}] must be a mapping")

            name = srv.get("name")
            if not name or not isinstance(name, str):
                raise MCPConfigError(f"mcp.servers[{i}]: 'name' is required and must be a string")

            if name in seen_names:
                raise MCPConfigError(f"Duplicate MCP server name: '{name}'")
            seen_names.add(name)

            transport = srv.get("transport", "stdio")

            server_config = MCPServerConfig(
                name=name,
                transport=transport,
                command=srv.get("command"),
                env=srv.get("env"),
                url=srv.get("url"),
                headers=srv.get("headers"),
                auto_connect=srv.get("auto_connect", mcp_config.get("auto_connect", True)),
            )
            configs.append(server_config)
            self._configs[name] = server_config

        return configs

    def connect(self, name: str) -> MCPClient:
        """Connect to a named MCP server.

        Args:
            name: Server name from configuration.

        Returns:
            Connected MCPClient instance.

        Raises:
            MCPConfigError: If server name is not configured.
            MCPConnectionError: If connection fails.
        """
        if name in self._clients:
            logger.info("MCP server '%s' is already connected", name)
            return self._clients[name]

        config = self._configs.get(name)
        if config is None:
            raise MCPConfigError(f"MCP server '{name}' is not configured")

        transport_callable = _build_transport(config)

        try:
            client = MCPClient(transport_callable=transport_callable)
            # Enter the context manager to establish connection
            client.__enter__()
        except Exception as e:
            # Attempt cleanup if __enter__ partially succeeded
            try:
                client.__exit__(None, None, None)
            except Exception:
                pass  # Best-effort cleanup
            raise MCPConnectionError(
                f"Failed to connect to MCP server '{name}': {e}"
            ) from e

        self._clients[name] = client
        logger.info("Connected to MCP server '%s' (%s)", name, config.transport)
        return client

    def disconnect(self, name: str) -> None:
        """Disconnect from a named MCP server.

        Args:
            name: Server name to disconnect.

        Raises:
            MCPConfigError: If server name is not connected.
        """
        client = self._clients.pop(name, None)
        if client is None:
            raise MCPConfigError(f"MCP server '{name}' is not connected")

        try:
            client.__exit__(None, None, None)
            logger.info("Disconnected from MCP server '%s'", name)
        except Exception as e:
            logger.warning("Error disconnecting from MCP server '%s': %s", name, e)

    def disconnect_all(self) -> None:
        """Disconnect from all connected MCP servers."""
        names = list(self._clients.keys())
        for name in names:
            try:
                self.disconnect(name)
            except Exception as e:
                logger.warning("Error disconnecting '%s': %s", name, e)

    def get_tools(self) -> list[MCPClient]:
        """Return all connected MCPClient instances for agent tool registration.

        Returns:
            List of connected MCPClient instances.
        """
        return list(self._clients.values())

    def get_server_info(self, name: str) -> dict[str, Any]:
        """Get information about a configured server.

        Args:
            name: Server name.

        Returns:
            Dictionary with server info.

        Raises:
            MCPConfigError: If server is not configured.
        """
        config = self._configs.get(name)
        if config is None:
            raise MCPConfigError(f"MCP server '{name}' is not configured")

        return {
            "name": config.name,
            "transport": config.transport,
            "connected": name in self._clients,
            "auto_connect": config.auto_connect,
            "command": config.command,
            "url": config.url,
        }

    def list_servers(self) -> list[dict[str, Any]]:
        """List all configured servers with their status.

        Returns:
            List of server info dicts.
        """
        return [self.get_server_info(name) for name in self._configs]


def _validate_command(server_name: str, command: list[str]) -> None:
    """Validate command for stdio transport.

    Checks that the command binary exists and doesn't contain shell metacharacters.

    Args:
        server_name: Server name for error messages.
        command: Command list to validate.

    Raises:
        MCPConfigError: If command is invalid or potentially dangerous.
    """
    binary = command[0]

    # Check for shell metacharacters in command parts
    shell_meta = re.compile(r"[;&|`$(){}]")
    for part in command:
        if shell_meta.search(part):
            raise MCPConfigError(
                f"Server '{server_name}': command contains shell metacharacters: '{part}'"
            )

    # Check that the binary exists on PATH or is an absolute path
    if not shutil.which(binary):
        logger.warning(
            "Server '%s': command binary '%s' not found on PATH", server_name, binary
        )


def _validate_url(server_name: str, url: str) -> None:
    """Validate URL for SSE/HTTP transports.

    Args:
        server_name: Server name for error messages.
        url: URL to validate.

    Raises:
        MCPConfigError: If URL is invalid or uses disallowed scheme.
    """
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise MCPConfigError(f"Server '{server_name}': invalid URL '{url}': {e}") from e

    if parsed.scheme not in _ALLOWED_URL_SCHEMES:
        raise MCPConfigError(
            f"Server '{server_name}': URL scheme '{parsed.scheme}' is not allowed. "
            f"Must be one of: {', '.join(_ALLOWED_URL_SCHEMES)}"
        )

    if not parsed.hostname:
        raise MCPConfigError(f"Server '{server_name}': URL has no hostname: '{url}'")


def _validate_env(server_name: str, env: dict[str, str]) -> None:
    """Validate environment variables for safety.

    Args:
        server_name: Server name for error messages.
        env: Environment variables to validate.

    Raises:
        MCPConfigError: If env contains blocked variables.
    """
    blocked_found = set(env.keys()) & _BLOCKED_ENV_VARS
    if blocked_found:
        raise MCPConfigError(
            f"Server '{server_name}': env contains blocked variable(s): "
            f"{', '.join(sorted(blocked_found))}"
        )


def _build_transport(config: MCPServerConfig):
    """Build a transport callable for the given server config.

    Args:
        config: Server configuration.

    Returns:
        A callable that returns an async context manager for the transport.
    """
    if config.transport == "stdio":
        command = config.command[0]
        args = config.command[1:] if len(config.command) > 1 else []

        def _stdio_transport():
            return stdio_client(
                StdioServerParameters(
                    command=command,
                    args=args,
                    env=config.env,
                )
            )

        return _stdio_transport

    elif config.transport == "sse":

        def _sse_transport():
            return sse_client(
                url=config.url,
                headers=config.headers,
            )

        return _sse_transport

    elif config.transport == "streamable_http":

        def _http_transport():
            return streamablehttp_client(
                url=config.url,
                headers=config.headers,
            )

        return _http_transport

    else:
        raise MCPConfigError(f"Unsupported transport: {config.transport}")


def connect_mcp_servers(config: dict[str, Any]) -> MCPManager:
    """High-level function to create MCPManager and connect auto_connect servers.

    Used by agent.py during startup. Gracefully handles connection failures.

    Args:
        config: Full application config dict.

    Returns:
        Configured MCPManager instance (may have partial connections).
    """
    manager = MCPManager()
    mcp_config = config.get("mcp")

    if not mcp_config:
        logger.debug("No MCP configuration found — skipping MCP server setup")
        return manager

    try:
        server_configs = manager.load_configs(mcp_config)
    except MCPConfigError as e:
        logger.error("MCP configuration error: %s", e)
        return manager

    if not server_configs:
        logger.debug("No MCP servers configured")
        return manager

    # Connect servers with auto_connect=True
    for srv_config in server_configs:
        if not srv_config.auto_connect:
            logger.info("MCP server '%s' has auto_connect=false — skipping", srv_config.name)
            continue

        try:
            manager.connect(srv_config.name)
        except MCPConnectionError as e:
            logger.warning("Could not connect to MCP server '%s': %s", srv_config.name, e)
        except Exception as e:
            logger.warning(
                "Unexpected error connecting to MCP server '%s': %s", srv_config.name, e
            )

    connected = manager.connected_servers
    total = len(server_configs)
    logger.info(
        "MCP setup complete: %d/%d servers connected%s",
        len(connected),
        total,
        f" ({', '.join(connected)})" if connected else "",
    )

    return manager
