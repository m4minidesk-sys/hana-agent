"""Tests for yui.meeting.ipc — AC-58, AC-59.

Tests Unix socket IPC server/client communication.
Uses /tmp for socket paths to avoid macOS AF_UNIX 104-byte path limit.
"""

import json
import os
import socket
import threading
import time
import uuid
from pathlib import Path
import pytest

from yui.meeting.ipc import (
    DEFAULT_SOCKET_PATH,
    IPCClient,
    IPCConnectionError,
    IPCError,
    IPCServer,
)


@pytest.fixture
def sock_path():
    """Create a short socket path in /tmp and clean up after test."""
    path = f"/tmp/yui-test-{uuid.uuid4().hex[:8]}.sock"
    yield path
    # Cleanup
    try:
        os.unlink(path)
    except OSError:
        pass


class TestIPCServer:
    """Test IPC server functionality."""

    def test_server_starts_and_creates_socket(self, sock_path):
        """Server creates Unix socket file on start."""
        server = IPCServer(socket_path=sock_path)
        server.start(background=True)

        try:
            assert Path(sock_path).exists()
            assert server.is_running
        finally:
            server.stop()

    def test_server_stop_removes_socket(self, sock_path):
        """Server removes socket file on stop."""
        server = IPCServer(socket_path=sock_path)
        server.start(background=True)
        server.stop()

        assert not Path(sock_path).exists()
        assert not server.is_running

    def test_server_cleans_stale_socket(self, sock_path):
        """Server removes stale socket before binding."""
        Path(sock_path).touch()  # Create stale file

        server = IPCServer(socket_path=sock_path)
        server.start(background=True)

        try:
            assert server.is_running
        finally:
            server.stop()

    def test_server_default_handler_echoes(self, sock_path):
        """Default handler returns ack + echo."""
        server = IPCServer(socket_path=sock_path)
        server.start(background=True)

        try:
            time.sleep(0.2)  # Let server start
            client_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client_sock.connect(sock_path)
            client_sock.sendall(b'{"cmd": "ping"}\n')

            data = client_sock.recv(4096)
            response = json.loads(data.decode().strip())
            assert response["ack"] is True
            assert response["echo"]["cmd"] == "ping"
            client_sock.close()
        finally:
            server.stop()

    def test_server_custom_handler(self, sock_path):
        """Custom handler receives messages and returns responses."""
        def handler(msg):
            if msg.get("cmd") == "meeting_start":
                return {"status": "ok", "name": "Test Meeting"}
            return {"error": "unknown command"}

        server = IPCServer(socket_path=sock_path, handler=handler)
        server.start(background=True)

        try:
            time.sleep(0.2)
            client_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client_sock.connect(sock_path)
            client_sock.sendall(b'{"cmd": "meeting_start"}\n')

            data = client_sock.recv(4096)
            response = json.loads(data.decode().strip())
            assert response["status"] == "ok"
            assert response["name"] == "Test Meeting"
            client_sock.close()
        finally:
            server.stop()

    def test_server_handles_invalid_json(self, sock_path):
        """Server returns error for invalid JSON."""
        server = IPCServer(socket_path=sock_path)
        server.start(background=True)

        try:
            time.sleep(0.2)
            client_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client_sock.connect(sock_path)
            client_sock.sendall(b"not json\n")

            data = client_sock.recv(4096)
            response = json.loads(data.decode().strip())
            assert "error" in response
            client_sock.close()
        finally:
            server.stop()

    def test_server_socket_path_property(self, sock_path):
        """Socket path property returns resolved path."""
        server = IPCServer(socket_path=sock_path)
        assert server.socket_path == Path(sock_path)


class TestIPCClient:
    """Test IPC client functionality."""

    def test_client_send_and_receive(self, sock_path):
        """Client sends message and receives response via server."""
        def handler(msg):
            return {"ack": True, "received": msg}

        server = IPCServer(socket_path=sock_path, handler=handler)
        server.start(background=True)

        try:
            time.sleep(0.2)
            client = IPCClient(socket_path=sock_path)
            response = client.send({"cmd": "test"})

            assert response["ack"] is True
            assert response["received"]["cmd"] == "test"
        finally:
            server.stop()

    def test_client_raises_when_no_socket(self, tmp_path):
        """Client raises IPCConnectionError when socket doesn't exist."""
        client = IPCClient(socket_path=str(tmp_path / "nonexistent.sock"))

        with pytest.raises(IPCConnectionError, match="not found"):
            client.send({"cmd": "test"})

    def test_client_is_daemon_running_true(self, sock_path):
        """is_daemon_running returns True when daemon responds."""
        server = IPCServer(socket_path=sock_path)
        server.start(background=True)

        try:
            time.sleep(0.2)
            client = IPCClient(socket_path=sock_path)
            assert client.is_daemon_running() is True
        finally:
            server.stop()

    def test_client_is_daemon_running_false(self, tmp_path):
        """is_daemon_running returns False when daemon not running."""
        client = IPCClient(socket_path=str(tmp_path / "nonexistent.sock"))
        assert client.is_daemon_running() is False

    def test_client_meeting_start(self, sock_path):
        """meeting_start sends correct command."""
        def handler(msg):
            assert msg["cmd"] == "meeting_start"
            return {"status": "ok", "name": msg.get("name", "Meeting")}

        server = IPCServer(socket_path=sock_path, handler=handler)
        server.start(background=True)

        try:
            time.sleep(0.2)
            client = IPCClient(socket_path=sock_path)
            response = client.meeting_start(name="Daily")
            assert response["name"] == "Daily"
        finally:
            server.stop()

    def test_client_meeting_stop(self, sock_path):
        """meeting_stop sends correct command."""
        def handler(msg):
            assert msg["cmd"] == "meeting_stop"
            return {"status": "ok", "duration_seconds": 300}

        server = IPCServer(socket_path=sock_path, handler=handler)
        server.start(background=True)

        try:
            time.sleep(0.2)
            client = IPCClient(socket_path=sock_path)
            response = client.meeting_stop()
            assert response["duration_seconds"] == 300
        finally:
            server.stop()

    def test_client_meeting_status(self, sock_path):
        """meeting_status sends correct command."""
        def handler(msg):
            assert msg["cmd"] == "meeting_status"
            return {"status": "recording", "elapsed": 120}

        server = IPCServer(socket_path=sock_path, handler=handler)
        server.start(background=True)

        try:
            time.sleep(0.2)
            client = IPCClient(socket_path=sock_path)
            response = client.meeting_status()
            assert response["status"] == "recording"
            assert response["elapsed"] == 120
        finally:
            server.stop()

    def test_client_meeting_generate_minutes(self, sock_path):
        """meeting_generate_minutes sends correct command."""
        def handler(msg):
            assert msg["cmd"] == "meeting_generate_minutes"
            return {"status": "generating"}

        server = IPCServer(socket_path=sock_path, handler=handler)
        server.start(background=True)

        try:
            time.sleep(0.2)
            client = IPCClient(socket_path=sock_path)
            response = client.meeting_generate_minutes()
            assert response["status"] == "generating"
        finally:
            server.stop()

    def test_client_socket_path_property(self, sock_path):
        """Socket path property returns resolved path."""
        client = IPCClient(socket_path=sock_path)
        assert client.socket_path == Path(sock_path)


class TestIPCRoundTrip:
    """Integration tests for full IPC round-trip."""

    def test_multiple_sequential_commands(self, sock_path):
        """Multiple commands in sequence work correctly."""
        call_log = []

        def handler(msg):
            call_log.append(msg["cmd"])
            return {"ack": True, "cmd": msg["cmd"]}

        server = IPCServer(socket_path=sock_path, handler=handler)
        server.start(background=True)

        try:
            time.sleep(0.2)
            client = IPCClient(socket_path=sock_path)

            r1 = client.send({"cmd": "ping"})
            r2 = client.send({"cmd": "meeting_start"})
            r3 = client.send({"cmd": "meeting_status"})

            assert r1["cmd"] == "ping"
            assert r2["cmd"] == "meeting_start"
            assert r3["cmd"] == "meeting_status"
            assert call_log == ["ping", "meeting_start", "meeting_status"]
        finally:
            server.stop()

    def test_concurrent_clients(self, sock_path):
        """Multiple concurrent clients are handled."""
        def handler(msg):
            time.sleep(0.05)  # Simulate work
            return {"ack": True, "id": msg.get("id")}

        server = IPCServer(socket_path=sock_path, handler=handler)
        server.start(background=True)

        try:
            time.sleep(0.2)
            results = {}
            errors = []

            def send_msg(client_id):
                try:
                    client = IPCClient(socket_path=sock_path)
                    r = client.send({"cmd": "test", "id": client_id})
                    results[client_id] = r
                except Exception as e:
                    errors.append(e)

            threads = [
                threading.Thread(target=send_msg, args=(i,))
                for i in range(5)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5.0)

            assert len(errors) == 0
            assert len(results) == 5
        finally:
            server.stop()
