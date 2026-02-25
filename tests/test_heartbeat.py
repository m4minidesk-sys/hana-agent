"""Tests for HANA heartbeat."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock

import pytest

from hana.runtime.heartbeat import Heartbeat


class TestHeartbeat:
    """Tests for the Heartbeat runner."""

    def test_disabled_heartbeat_no_start(self) -> None:
        config = {"heartbeat": {"enabled": False, "interval_minutes": 1}}
        hb = Heartbeat(config)
        hb.start()
        assert not hb.is_running

    def test_enabled_heartbeat_starts(self) -> None:
        config = {"heartbeat": {"enabled": True, "interval_minutes": 1}}
        hb = Heartbeat(config)
        hb.start()
        assert hb.is_running
        hb.stop()
        assert not hb.is_running

    def test_heartbeat_tick_callback(self) -> None:
        callback = MagicMock()
        config = {"heartbeat": {"enabled": True, "interval_minutes": 60}}
        hb = Heartbeat(config, on_tick=callback)

        # Manually trigger tick
        hb._tick()
        assert hb.tick_count == 1
        callback.assert_called_once_with(config)

    def test_tick_count_increments(self) -> None:
        config = {"heartbeat": {"enabled": True, "interval_minutes": 60}}
        hb = Heartbeat(config)
        hb._tick()
        hb._tick()
        hb._tick()
        assert hb.tick_count == 3

    def test_stop_idempotent(self) -> None:
        config = {"heartbeat": {"enabled": False}}
        hb = Heartbeat(config)
        hb.stop()  # Should not raise
        hb.stop()  # Should not raise
