"""HANA heartbeat — periodic autonomous actions."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)


class Heartbeat:
    """Periodic heartbeat runner for autonomous scheduled tasks.

    Runs configured tasks at a regular interval in a background thread.

    Args:
        config: HANA configuration dictionary.
        on_tick: Callback function invoked each heartbeat tick.
                 Receives the config dict as argument.
    """

    def __init__(
        self,
        config: dict[str, Any],
        on_tick: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        hb_config = config.get("heartbeat", {})
        self.enabled = hb_config.get("enabled", False)
        self.interval_minutes = hb_config.get("interval_minutes", 30)
        self.tasks = hb_config.get("tasks", [])
        self.config = config
        self.on_tick = on_tick

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._tick_count = 0

    def start(self) -> None:
        """Start the heartbeat in a background thread."""
        if not self.enabled:
            logger.info("Heartbeat disabled — skipping start")
            return

        if self._thread and self._thread.is_alive():
            logger.warning("Heartbeat already running")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="hana-heartbeat",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "Heartbeat started — interval=%dm, tasks=%d",
            self.interval_minutes,
            len(self.tasks),
        )

    def stop(self) -> None:
        """Stop the heartbeat thread."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            logger.info("Heartbeat stopped (ticks=%d)", self._tick_count)

    def _run_loop(self) -> None:
        """Main heartbeat loop — runs on background thread."""
        interval_sec = self.interval_minutes * 60

        while not self._stop_event.is_set():
            try:
                self._tick()
            except Exception as exc:
                logger.error("Heartbeat tick failed: %s", exc)

            # Sleep in small increments so we can respond to stop quickly
            for _ in range(int(interval_sec)):
                if self._stop_event.is_set():
                    return
                time.sleep(1)

    def _tick(self) -> None:
        """Execute one heartbeat tick."""
        self._tick_count += 1
        logger.info("Heartbeat tick #%d", self._tick_count)

        if self.on_tick:
            self.on_tick(self.config)

    @property
    def is_running(self) -> bool:
        """Check if heartbeat is currently running."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def tick_count(self) -> int:
        """Number of completed heartbeat ticks."""
        return self._tick_count
