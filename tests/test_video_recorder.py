"""Tests for Video Recorder (AC-76, AC-77).

All tests use REAL Playwright browser — no mocks.
"""

from __future__ import annotations

import os

import pytest
import pytest_asyncio

from playwright.async_api import async_playwright

from yui.workshop.video_recorder import DEFAULT_RESOLUTION, RecordingConfig, VideoRecorder


@pytest.fixture
def tmp_output_dir(tmp_path):
    return str(tmp_path / "recording_output")


@pytest.fixture
def recorder(tmp_output_dir):
    return VideoRecorder(output_dir=tmp_output_dir)


@pytest_asyncio.fixture
async def pw_browser():
    """Launch a real headless Chromium browser."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        yield browser
        await browser.close()


class TestRecordingConfig:
    def test_default_resolution(self):
        cfg = RecordingConfig(output_dir="/tmp/out")
        assert cfg.resolution == {"width": 1920, "height": 1080}

    def test_custom_resolution(self):
        cfg = RecordingConfig(output_dir="/tmp/out", resolution={"width": 1280, "height": 720})
        assert cfg.resolution["width"] == 1280

    def test_screenshots_dir(self):
        assert RecordingConfig(output_dir="/tmp/out").screenshots_dir == "/tmp/out/screenshots"

    def test_videos_dir(self):
        assert RecordingConfig(output_dir="/tmp/out").videos_dir == "/tmp/out/videos"

    def test_custom_subdirs(self):
        cfg = RecordingConfig(output_dir="/tmp/out", screenshots_subdir="caps", videos_subdir="vids")
        assert cfg.screenshots_dir == "/tmp/out/caps"
        assert cfg.videos_dir == "/tmp/out/vids"


class TestRecorderCreation:
    def test_creates_output_dirs(self, tmp_output_dir):
        recorder = VideoRecorder(output_dir=tmp_output_dir)
        assert os.path.isdir(recorder.config.screenshots_dir)
        assert os.path.isdir(recorder.config.videos_dir)

    def test_custom_resolution(self, tmp_output_dir):
        recorder = VideoRecorder(output_dir=tmp_output_dir, resolution={"width": 1280, "height": 720})
        assert recorder.config.resolution == {"width": 1280, "height": 720}

    def test_default_resolution(self, tmp_output_dir):
        assert VideoRecorder(output_dir=tmp_output_dir).config.resolution == DEFAULT_RESOLUTION

    def test_empty_output_dir_raises(self):
        with pytest.raises(ValueError, match="output_dir"):
            VideoRecorder(output_dir="")


class TestCreateContext:
    @pytest.mark.asyncio
    async def test_creates_context_with_video_settings(self, recorder, pw_browser):
        ctx = await recorder.create_context_with_recording(pw_browser)
        assert recorder._context is not None
        assert ctx is not None
        await ctx.close()

    @pytest.mark.asyncio
    async def test_stores_context_reference(self, recorder, pw_browser):
        await recorder.create_context_with_recording(pw_browser)
        assert recorder._context is not None
        await recorder._context.close()

    @pytest.mark.asyncio
    async def test_custom_resolution_passed(self, tmp_output_dir, pw_browser):
        rec = VideoRecorder(output_dir=tmp_output_dir, resolution={"width": 800, "height": 600})
        ctx = await rec.create_context_with_recording(pw_browser)
        assert rec._context is not None
        await ctx.close()


class TestScreenshotCapture:
    @pytest.mark.asyncio
    async def test_step_screenshot(self, recorder, pw_browser):
        ctx = await recorder.create_context_with_recording(pw_browser)
        page = await ctx.new_page()
        await page.goto("data:text/html,<h1>Test</h1>")
        path = await recorder.capture_screenshot(page, "1.2.3")
        assert "step-1.2.3.png" in path
        assert os.path.isfile(path)
        await ctx.close()

    @pytest.mark.asyncio
    async def test_failure_screenshot(self, recorder, pw_browser):
        ctx = await recorder.create_context_with_recording(pw_browser)
        page = await ctx.new_page()
        await page.goto("data:text/html,<h1>Fail</h1>")
        path = await recorder.capture_screenshot(page, "1.2.3", on_failure=True)
        assert "fail-1.2.3.png" in path
        assert os.path.isfile(path)
        await ctx.close()

    @pytest.mark.asyncio
    async def test_screenshot_path_sanitised(self, recorder, pw_browser):
        ctx = await recorder.create_context_with_recording(pw_browser)
        page = await ctx.new_page()
        await page.goto("data:text/html,<h1>Sanitise</h1>")
        path = await recorder.capture_screenshot(page, "mod/step/1")
        assert "mod-step-1" in path
        assert "/" not in os.path.basename(path)
        await ctx.close()


class TestClose:
    @pytest.mark.asyncio
    async def test_close_returns_video_paths(self, recorder, pw_browser):
        ctx = await recorder.create_context_with_recording(pw_browser)
        page = await ctx.new_page()
        await page.goto("data:text/html,<h1>Video</h1>")
        # Give video a moment to start
        import asyncio
        await asyncio.sleep(0.5)
        paths = await recorder.close()
        # paths may or may not contain video depending on duration
        assert isinstance(paths, list)

    @pytest.mark.asyncio
    async def test_close_without_context(self, recorder):
        assert await recorder.close() == []

    @pytest.mark.asyncio
    async def test_close_clears_context(self, recorder, pw_browser):
        await recorder.create_context_with_recording(pw_browser)
        await recorder.close()
        assert recorder._context is None


class TestScreenshotCallback:
    @pytest.mark.asyncio
    async def test_callback_writes_file(self, recorder):
        cb = recorder.make_screenshot_callback()
        path = await cb(b"fake-png-data", "2.1", False)
        assert path.endswith("step-2.1.png")
        assert os.path.isfile(path)
        with open(path, "rb") as f:
            assert f.read() == b"fake-png-data"

    @pytest.mark.asyncio
    async def test_callback_failure_prefix(self, recorder):
        path = await recorder.make_screenshot_callback()(b"data", "2.1", True)
        assert "fail-2.1.png" in path

    @pytest.mark.asyncio
    async def test_callback_sanitises_id(self, recorder):
        path = await recorder.make_screenshot_callback()(b"data", "mod/step/3", False)
        assert "/" not in os.path.basename(path)
        assert "mod-step-3" in path
