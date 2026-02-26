"""Tests for Video Recorder (AC-76, AC-77). All mocked."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock

import pytest

from yui.workshop.video_recorder import DEFAULT_RESOLUTION, RecordingConfig, VideoRecorder


@pytest.fixture
def tmp_output_dir(tmp_path):
    return str(tmp_path / "recording_output")


@pytest.fixture
def recorder(tmp_output_dir):
    return VideoRecorder(output_dir=tmp_output_dir)


@pytest.fixture
def mock_browser():
    browser = AsyncMock()
    context = AsyncMock()
    context.pages = []
    browser.new_context.return_value = context
    return browser


@pytest.fixture
def mock_page():
    page = AsyncMock()
    page.screenshot = AsyncMock(return_value=None)
    page.video = MagicMock()
    page.video.path = AsyncMock(return_value="/tmp/videos/vid.webm")
    page.video.save_as = AsyncMock()
    return page


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
    async def test_creates_context_with_video_settings(self, recorder, mock_browser):
        await recorder.create_context_with_recording(mock_browser)
        mock_browser.new_context.assert_called_once()
        kw = mock_browser.new_context.call_args[1]
        assert kw["record_video_dir"] == recorder.config.videos_dir
        assert kw["record_video_size"] == recorder.config.resolution
        assert kw["viewport"] == recorder.config.resolution

    @pytest.mark.asyncio
    async def test_stores_context_reference(self, recorder, mock_browser):
        await recorder.create_context_with_recording(mock_browser)
        assert recorder._context is not None

    @pytest.mark.asyncio
    async def test_custom_resolution_passed(self, tmp_output_dir, mock_browser):
        rec = VideoRecorder(output_dir=tmp_output_dir, resolution={"width": 800, "height": 600})
        await rec.create_context_with_recording(mock_browser)
        assert mock_browser.new_context.call_args[1]["record_video_size"] == {"width": 800, "height": 600}


class TestScreenshotCapture:
    @pytest.mark.asyncio
    async def test_step_screenshot(self, recorder, mock_page):
        path = await recorder.capture_screenshot(mock_page, "1.2.3")
        assert "step-1.2.3.png" in path
        mock_page.screenshot.assert_called_once()

    @pytest.mark.asyncio
    async def test_failure_screenshot(self, recorder, mock_page):
        path = await recorder.capture_screenshot(mock_page, "1.2.3", on_failure=True)
        assert "fail-1.2.3.png" in path

    @pytest.mark.asyncio
    async def test_screenshot_full_page(self, recorder, mock_page):
        await recorder.capture_screenshot(mock_page, "1.1")
        assert mock_page.screenshot.call_args[1]["full_page"] is True

    @pytest.mark.asyncio
    async def test_screenshot_path_sanitised(self, recorder, mock_page):
        path = await recorder.capture_screenshot(mock_page, "mod/step/1")
        assert "mod-step-1" in path
        assert "/" not in os.path.basename(path)

    @pytest.mark.asyncio
    async def test_screenshot_bytes(self, recorder, tmp_output_dir):
        page = AsyncMock()
        async def _screenshot(path=None, full_page=True):
            if path:
                with open(path, "wb") as f:
                    f.write(b"fake-png")
        page.screenshot = AsyncMock(side_effect=_screenshot)
        data, path = await recorder.capture_screenshot_bytes(page, "1.1")
        assert data == b"fake-png"
        assert path.endswith("step-1.1.png")


class TestVideoPath:
    @pytest.mark.asyncio
    async def test_get_video_path(self, recorder, mock_page):
        assert await recorder.get_video_path(mock_page) == "/tmp/videos/vid.webm"

    @pytest.mark.asyncio
    async def test_get_video_path_no_video(self, recorder):
        page = AsyncMock()
        page.video = None
        assert await recorder.get_video_path(page) is None

    @pytest.mark.asyncio
    async def test_save_video(self, recorder, mock_page):
        assert await recorder.save_video(mock_page, "/tmp/my_video.webm") == "/tmp/my_video.webm"
        mock_page.video.save_as.assert_called_once_with("/tmp/my_video.webm")

    @pytest.mark.asyncio
    async def test_save_video_no_video(self, recorder):
        page = AsyncMock()
        page.video = None
        assert await recorder.save_video(page, "/tmp/vid.webm") is None


class TestClose:
    @pytest.mark.asyncio
    async def test_close_returns_video_paths(self, recorder, mock_browser):
        page1 = AsyncMock()
        page1.video = MagicMock()
        page1.video.path = AsyncMock(return_value="/tmp/vid1.webm")
        ctx = AsyncMock()
        ctx.pages = [page1]
        mock_browser.new_context.return_value = ctx
        await recorder.create_context_with_recording(mock_browser)
        paths = await recorder.close()
        assert "/tmp/vid1.webm" in paths
        ctx.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_without_context(self, recorder):
        assert await recorder.close() == []

    @pytest.mark.asyncio
    async def test_close_clears_context(self, recorder, mock_browser):
        await recorder.create_context_with_recording(mock_browser)
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
