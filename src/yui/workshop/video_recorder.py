"""Video Recorder — Playwright video recording and screenshot capture (AC-76, AC-77).

Uses Playwright's built-in ``record_video_dir`` feature for full session
recording, plus explicit screenshot capture at step boundaries and on failures.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_RESOLUTION = {"width": 1920, "height": 1080}
DEFAULT_SCREENSHOTS_SUBDIR = "screenshots"
DEFAULT_VIDEOS_SUBDIR = "videos"


@dataclass
class RecordingConfig:
    """Configuration for video recording and screenshots."""

    output_dir: str
    resolution: dict = field(default_factory=lambda: dict(DEFAULT_RESOLUTION))
    screenshots_subdir: str = DEFAULT_SCREENSHOTS_SUBDIR
    videos_subdir: str = DEFAULT_VIDEOS_SUBDIR
    full_page_screenshots: bool = True

    @property
    def screenshots_dir(self) -> str:
        return os.path.join(self.output_dir, self.screenshots_subdir)

    @property
    def videos_dir(self) -> str:
        return os.path.join(self.output_dir, self.videos_subdir)


class VideoRecorder:
    """Manage Playwright video recording and screenshot capture."""

    def __init__(self, output_dir: str, resolution: dict | None = None) -> None:
        if not output_dir:
            raise ValueError("output_dir must not be empty")

        self.config = RecordingConfig(
            output_dir=output_dir,
            resolution=resolution or dict(DEFAULT_RESOLUTION),
        )
        self._context: Any | None = None
        self._pages: list[Any] = []
        self._ensure_dirs()

    async def create_context_with_recording(self, browser: Any) -> Any:
        """Create a Playwright BrowserContext with video recording enabled."""
        self._ensure_dirs()
        context = await browser.new_context(
            record_video_dir=self.config.videos_dir,
            record_video_size=self.config.resolution,
            viewport=self.config.resolution,
        )
        self._context = context
        logger.info("Created recording context: video_dir=%s, resolution=%s",
                     self.config.videos_dir, self.config.resolution)
        return context

    async def capture_screenshot(self, page: Any, step_id: str, on_failure: bool = False) -> str:
        """Capture a screenshot at step completion or on failure."""
        self._ensure_dirs()
        prefix = "fail" if on_failure else "step"
        safe_id = step_id.replace("/", "-").replace("\\", "-").replace(" ", "_")
        filename = f"{prefix}-{safe_id}.png"
        path = os.path.join(self.config.screenshots_dir, filename)
        await page.screenshot(path=path, full_page=self.config.full_page_screenshots)
        logger.info("Screenshot captured: %s", path)
        return path

    async def capture_screenshot_bytes(self, page: Any, step_id: str, on_failure: bool = False) -> tuple[bytes, str]:
        """Capture a screenshot and return both bytes and saved path."""
        path = await self.capture_screenshot(page, step_id, on_failure=on_failure)
        with open(path, "rb") as f:
            data = f.read()
        return data, path

    async def get_video_path(self, page: Any) -> str | None:
        """Get the video file path for a page."""
        try:
            video = page.video
            if video is None:
                return None
            path = await video.path()
            return str(path)
        except Exception as exc:
            logger.warning("Could not get video path: %s", exc)
            return None

    async def save_video(self, page: Any, dest_path: str) -> str | None:
        """Save the video for a page to a specific path."""
        try:
            video = page.video
            if video is None:
                return None
            await video.save_as(dest_path)
            logger.info("Video saved to: %s", dest_path)
            return dest_path
        except Exception as exc:
            logger.warning("Could not save video: %s", exc)
            return None

    async def close(self) -> list[str]:
        """Close the recording context and return paths to recorded videos."""
        video_paths: list[str] = []
        if self._context is not None:
            try:
                pages = self._context.pages
                for p in pages:
                    path = await self.get_video_path(p)
                    if path:
                        video_paths.append(path)
                await self._context.close()
                logger.info("Recording context closed. Videos: %s", video_paths)
            except Exception as exc:
                logger.warning("Error closing recording context: %s", exc)
            finally:
                self._context = None
        return video_paths

    def make_screenshot_callback(self):
        """Return an async callback compatible with :class:`ConsoleExecutor`."""
        async def _callback(screenshot_bytes: bytes, step_id: str, on_failure: bool = False) -> str:
            self._ensure_dirs()
            prefix = "fail" if on_failure else "step"
            safe_id = step_id.replace("/", "-").replace("\\", "-").replace(" ", "_")
            filename = f"{prefix}-{safe_id}.png"
            path = os.path.join(self.config.screenshots_dir, filename)
            with open(path, "wb") as f:
                f.write(screenshot_bytes)
            logger.info("Screenshot saved via callback: %s", path)
            return path
        return _callback

    def _ensure_dirs(self) -> None:
        """Create output directories if they don't exist."""
        os.makedirs(self.config.screenshots_dir, exist_ok=True)
        os.makedirs(self.config.videos_dir, exist_ok=True)
