"""Unix socket IPC for Menu Bar ↔ Daemon communication.

Provides a lightweight JSON message protocol over Unix domain sockets.
Socket path: ~/.yui/yui.sock

Protocol:
    - Messages are newline-delimited JSON objects
    - Commands: {"cmd": "meeting_start", ...}
    - Status:   {"status": "recording", "elapsed": 1425, ...}
    - Errors:   {"error": "message"}
"""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

DEFAULT_SOCKET_PATH = "~/.yui/yui.sock"


class IPCError(Exception):
    """Base IPC exception."""


class IPCConnectionError(IPCError):
    """Failed to connect to IPC socket."""


class IPCServer:
    """Unix socket IPC server (runs in the daemon side).

    Listens for JSON commands from menu bar / CLI clients and dispatches
    to registered handlers.

    Args:
        socket_path: Path to Unix socket. Defaults to ~/.yui/yui.sock.
        handler: Callback ``(msg: dict) -> dict`` that processes commands.
    """

    def __init__(
        self,
        socket_path: str = DEFAULT_SOCKET_PATH,
        handler: Optional[Callable[[dict[str, Any]], dict[str, Any]]] = None,
    ) -> None:
        self._socket_path = Path(socket_path).expanduser()
        self._handler = handler or self._default_handler
        self._server_socket: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

    @staticmethod
    def _default_handler(msg: dict[str, Any]) -> dict[str, Any]:
        """Default handler — echo back with ack."""
        return {"ack": True, "echo": msg}

    @property
    def socket_path(self) -> Path:
        """Return the resolved socket path."""
        return self._socket_path

    @property
    def is_running(self) -> bool:
        """Check if server is running."""
        return self._running

    def start(self, background: bool = True) -> None:
        """Start the IPC server.

        Args:
            background: If True, run in a daemon thread. If False, block.
        """
        # Clean up stale socket
        if self._socket_path.exists():
            self._socket_path.unlink()

        # Ensure parent directory exists
        self._socket_path.parent.mkdir(parents=True, exist_ok=True)

        self._server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server_socket.bind(str(self._socket_path))
        self._server_socket.listen(5)
        self._server_socket.settimeout(1.0)  # Allow periodic stop checks
        self._running = True

        logger.info(f"IPC server listening on {self._socket_path}")

        if background:
            self._thread = threading.Thread(
                target=self._accept_loop,
                daemon=True,
                name="yui-ipc-server",
            )
            self._thread.start()
        else:
            self._accept_loop()

    def stop(self) -> None:
        """Stop the IPC server and clean up socket."""
        self._running = False
        if self._server_socket:
            try:
                self._server_socket.close()
            except OSError:
                pass
            self._server_socket = None

        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None

        # Remove socket file
        if self._socket_path.exists():
            try:
                self._socket_path.unlink()
            except OSError:
                pass

        logger.info("IPC server stopped")

    def _accept_loop(self) -> None:
        """Accept connections and handle them."""
        while self._running:
            try:
                conn, _ = self._server_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                if self._running:
                    logger.error("IPC server socket error")
                break

            # Handle connection in a thread
            t = threading.Thread(
                target=self._handle_connection,
                args=(conn,),
                daemon=True,
                name="yui-ipc-conn",
            )
            t.start()

    def _handle_connection(self, conn: socket.socket) -> None:
        """Handle a single client connection."""
        try:
            conn.settimeout(5.0)
            data = b""
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\n" in data:
                    break

            if not data:
                return

            # Parse JSON message (take first line)
            line = data.split(b"\n")[0].decode("utf-8").strip()
            if not line:
                return

            msg = json.loads(line)
            logger.debug(f"IPC received: {msg}")

            # Dispatch to handler
            response = self._handler(msg)

            # Send response
            response_bytes = json.dumps(response).encode("utf-8") + b"\n"
            conn.sendall(response_bytes)

        except json.JSONDecodeError as e:
            error_resp = json.dumps({"error": f"Invalid JSON: {e}"}).encode("utf-8") + b"\n"
            try:
                conn.sendall(error_resp)
            except OSError:
                pass
        except socket.timeout:
            logger.warning("IPC connection timed out")
        except OSError as e:
            logger.warning(f"IPC connection error: {e}")
        finally:
            try:
                conn.close()
            except OSError:
                pass


class IPCClient:
    """Unix socket IPC client (used by menu bar / CLI).

    Sends JSON commands to the daemon and receives responses.

    Args:
        socket_path: Path to Unix socket. Defaults to ~/.yui/yui.sock.
        timeout: Connection/read timeout in seconds.
    """

    def __init__(
        self,
        socket_path: str = DEFAULT_SOCKET_PATH,
        timeout: float = 5.0,
    ) -> None:
        self._socket_path = Path(socket_path).expanduser()
        self._timeout = timeout

    @property
    def socket_path(self) -> Path:
        """Return the resolved socket path."""
        return self._socket_path

    def is_daemon_running(self) -> bool:
        """Check if daemon is reachable via IPC.

        Returns:
            True if daemon responds to ping.
        """
        try:
            response = self.send({"cmd": "ping"})
            return response is not None
        except IPCError:
            return False

    def send(self, msg: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON message and receive the response.

        Args:
            msg: Dictionary to send as JSON.

        Returns:
            Response dictionary from the daemon.

        Raises:
            IPCConnectionError: If cannot connect to daemon.
            IPCError: On other communication errors.
        """
        if not self._socket_path.exists():
            raise IPCConnectionError(
                f"Daemon socket not found at {self._socket_path}. "
                "Is the Yui daemon running? Start it with: yui daemon start"
            )

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self._timeout)

        try:
            sock.connect(str(self._socket_path))

            # Send message
            payload = json.dumps(msg).encode("utf-8") + b"\n"
            sock.sendall(payload)

            # Receive response
            data = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\n" in data:
                    break

            if not data:
                raise IPCError("Empty response from daemon")

            line = data.split(b"\n")[0].decode("utf-8").strip()
            return json.loads(line)

        except socket.timeout:
            raise IPCError("Timeout waiting for daemon response")
        except ConnectionRefusedError:
            raise IPCConnectionError(
                "Daemon refused connection. It may have crashed. "
                "Restart with: yui daemon start"
            )
        except OSError as e:
            raise IPCConnectionError(f"IPC connection failed: {e}")
        except json.JSONDecodeError as e:
            raise IPCError(f"Invalid response from daemon: {e}")
        finally:
            try:
                sock.close()
            except OSError:
                pass

    def meeting_start(self, name: str = "") -> dict[str, Any]:
        """Send meeting start command.

        Args:
            name: Optional meeting name.

        Returns:
            Response with meeting info.
        """
        return self.send({"cmd": "meeting_start", "name": name})

    def meeting_stop(self) -> dict[str, Any]:
        """Send meeting stop command.

        Returns:
            Response with meeting summary.
        """
        return self.send({"cmd": "meeting_stop"})

    def meeting_status(self) -> dict[str, Any]:
        """Get current meeting status.

        Returns:
            Response with status info.
        """
        return self.send({"cmd": "meeting_status"})

    def meeting_generate_minutes(self) -> dict[str, Any]:
        """Request minutes generation for the current/last meeting.

        Returns:
            Response with minutes info.
        """
        return self.send({"cmd": "meeting_generate_minutes"})
