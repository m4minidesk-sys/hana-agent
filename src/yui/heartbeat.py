"""Heartbeat scheduler for autonomous periodic actions."""

import hashlib
import logging
import threading
from datetime import datetime, time
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


class HeartbeatScheduler:
    """Periodic autonomous action scheduler with active hours and integrity checks.
    
    Args:
        config: Runtime configuration dictionary.
        agent_callback: Function to call with HEARTBEAT.md content on each tick.
    """

    def __init__(self, config: dict, agent_callback: Callable[[str], None]) -> None:
        self.config = config
        self.agent_callback = agent_callback
        self.heartbeat_config = config["runtime"]["heartbeat"]
        self.workspace = Path(config["tools"]["file"]["workspace_root"]).expanduser()
        self.heartbeat_file = self.workspace / "HEARTBEAT.md"
        self._timer: threading.Timer | None = None
        self._running = False
        self._file_hash: str | None = None

    def start(self) -> None:
        """Start the heartbeat scheduler."""
        if not self.heartbeat_config["enabled"]:
            logger.info("Heartbeat disabled in config")
            return
        
        if not self.heartbeat_file.exists():
            logger.warning("HEARTBEAT.md not found at %s — heartbeat disabled", self.heartbeat_file)
            return
        
        # Store initial hash (AC-21)
        self._file_hash = self._compute_hash()
        self._running = True
        self._schedule_next()
        logger.info("Heartbeat started (interval: %d min, active: %s, tz: %s)",
                   self.heartbeat_config["interval_minutes"],
                   self.heartbeat_config["active_hours"],
                   self.heartbeat_config["timezone"])

    def stop(self) -> None:
        """Stop the heartbeat scheduler."""
        self._running = False
        if self._timer:
            self._timer.cancel()
            self._timer = None
        logger.info("Heartbeat stopped")

    def _schedule_next(self) -> None:
        """Schedule the next tick."""
        if not self._running:
            return
        interval_seconds = self.heartbeat_config["interval_minutes"] * 60
        self._timer = threading.Timer(interval_seconds, self._tick)
        self._timer.daemon = True
        self._timer.start()

    def _tick(self) -> None:
        """Execute one heartbeat tick."""
        try:
            # Check active hours (AC-22)
            if not self._is_active_hour():
                logger.debug("Outside active hours — skipping tick")
                self._schedule_next()
                return
            
            # Verify file integrity (AC-21)
            current_hash = self._compute_hash()
            if current_hash != self._file_hash:
                logger.error("HEARTBEAT.md integrity check failed — stopping heartbeat")
                self.stop()
                return
            
            # Read and execute
            content = self.heartbeat_file.read_text(encoding="utf-8")
            logger.info("Heartbeat tick — executing HEARTBEAT.md")
            self.agent_callback(content)
            
        except Exception as e:
            logger.error("Heartbeat tick failed: %s", e, exc_info=True)
        finally:
            self._schedule_next()

    def _is_active_hour(self) -> bool:
        """Check if current time is within active hours (AC-22)."""
        tz = ZoneInfo(self.heartbeat_config["timezone"])
        now = datetime.now(tz).time()
        
        # Parse active_hours "HH:MM-HH:MM"
        active_hours = self.heartbeat_config["active_hours"]
        start_str, end_str = active_hours.split("-")
        
        # Handle 24:00 as end of day
        if end_str == "24:00":
            end_str = "23:59"
        
        start_time = time.fromisoformat(start_str)
        end_time = time.fromisoformat(end_str)
        
        # Handle overnight ranges (e.g., "22:00-02:00")
        if start_time <= end_time:
            return start_time <= now <= end_time
        else:
            return now >= start_time or now <= end_time

    def _compute_hash(self) -> str:
        """Compute SHA256 hash of HEARTBEAT.md."""
        content = self.heartbeat_file.read_bytes()
        return hashlib.sha256(content).hexdigest()
