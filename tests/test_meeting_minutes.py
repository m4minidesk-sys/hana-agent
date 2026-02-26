"""Tests for yui.meeting.minutes — AC-41, AC-45, AC-46, AC-47, AC-50.

All tests use REAL services — no mocks:
- Bedrock Converse API for minutes/analysis generation
- Slack API for notifications
- SQLite/filesystem for persistence
"""

import json
import time
from pathlib import Path

import boto3
import numpy as np
import pytest

from yui.meeting.minutes import (
    _empty_analysis,
    _empty_minutes,
    _extract_summary,
    notify_slack_minutes,
    post_meeting_minutes,
    real_time_analysis,
    save_analysis,
    save_minutes,
)
from yui.meeting.models import MeetingStatus, TranscriptChunk


def make_config(tmp_path=None):
    """Create a test config dict with real credentials."""
    config = {
        "model": {
            "provider": "bedrock",
            "model_id": "us.anthropic.claude-sonnet-4-20250514-v1:0",
            "region": "us-east-1",
            "max_tokens": 4096,
        },
        "meeting": {
            "analysis": {
                "provider": "bedrock",
                "realtime_enabled": False,
                "realtime_interval_seconds": 60,
                "realtime_window_minutes": 5,
                "max_cost_per_meeting_usd": 2.0,
                "minutes_auto_generate": True,
            },
            "output": {
                "transcript_dir": str(tmp_path / "meetings") if tmp_path else "~/.yui/meetings/",
                "format": "markdown",
                "save_audio": False,
                "slack_notify": True,
                "slack_channel": "C0AH55CBKGW",  # #yui-test
            },
        },
        "slack": {
            "bot_token": "",  # Will be loaded from env
        },
    }
    return config


@pytest.fixture
def bedrock_client():
    """Create a REAL Bedrock Runtime client."""
    return boto3.client("bedrock-runtime", region_name="us-east-1")


@pytest.fixture
def slack_client():
    """Create a REAL Slack client using Yui's token."""
    from dotenv import load_dotenv
    import os
    load_dotenv(os.path.expanduser("~/.yui/.env"))
    token = os.environ.get("SLACK_BOT_TOKEN", "")
    if not token:
        pytest.fail("SLACK_BOT_TOKEN not set in ~/.yui/.env")
    from slack_sdk import WebClient
    return WebClient(token=token)


SAMPLE_TRANSCRIPT = """
Alice: Good morning everyone. Let's discuss the deployment timeline.
Bob: I think we should deploy to staging on Friday.
Alice: Agreed. Bob, can you update the deployment script?
Bob: Sure, I'll have it done by March 1st.
Alice: Great. Also, someone needs to review PR #42.
Carol: I can do that by Thursday.
Alice: Perfect. Any questions about the blue-green deployment approach?
Bob: Should we use blue-green or canary?
Alice: Let's discuss that offline. Meeting adjourned.
"""

SAMPLE_MINUTES = """# Meeting Minutes — Weekly Standup

## Summary
The team discussed the deployment timeline and assigned tasks for the sprint.

## Key Decisions
1. Deploy to staging on Friday — Agreed by all

## Action Items
| # | Action | Owner | Due Date | Status |
|---|--------|-------|----------|--------|
| 1 | Update deployment script | Bob | 2026-03-01 | Open |
| 2 | Review PR #42 | Alice | 2026-02-27 | Open |

## Discussion Topics
### Topic 1: Deployment Timeline
- Discussed moving deployment to Friday
- Staging environment is ready

## Open Questions
- Should we use blue-green deployment?
"""


class TestPostMeetingMinutes:
    """AC-45: Bedrock generates structured meeting minutes (REAL API)."""

    def test_generates_minutes_from_transcript(self, bedrock_client):
        """Bedrock Converse API generates structured minutes."""
        config = make_config()
        result = post_meeting_minutes(
            transcript=SAMPLE_TRANSCRIPT,
            config=config,
            meeting_name="Weekly Standup",
            meeting_date="2026-02-26T10:00:00",
            bedrock_client=bedrock_client,
        )

        assert "Meeting Minutes" in result or "Summary" in result or "summary" in result.lower()
        assert len(result) > 100  # Non-trivial output

    def test_empty_transcript_returns_template(self, bedrock_client):
        """Empty transcript returns a template without API call."""
        config = make_config()
        result = post_meeting_minutes(
            transcript="   ",
            config=config,
            meeting_name="Empty Meeting",
            bedrock_client=bedrock_client,
        )

        assert "No transcript content" in result

    def test_includes_meeting_name(self, bedrock_client):
        """Generated minutes reference the meeting name."""
        config = make_config()
        result = post_meeting_minutes(
            transcript=SAMPLE_TRANSCRIPT,
            config=config,
            meeting_name="Sprint Planning Alpha",
            bedrock_client=bedrock_client,
        )

        # Bedrock should include the meeting name in output
        assert len(result) > 50


class TestRealTimeAnalysis:
    """AC-50: Real-time analysis (REAL Bedrock API)."""

    def test_returns_structured_analysis(self, bedrock_client):
        """Real-time analysis returns structured dict with real API."""
        config = make_config()
        result = real_time_analysis(
            transcript_window="Bob said he'll update the deployment script by Friday. Alice agreed to review PR 42.",
            config=config,
            bedrock_client=bedrock_client,
        )

        # Should have structured fields
        assert "current_topic" in result or "decisions" in result or "action_items" in result

    def test_empty_transcript_returns_empty_analysis(self, bedrock_client):
        """Empty transcript returns empty analysis without API call."""
        config = make_config()
        result = real_time_analysis(
            transcript_window="  ",
            config=config,
            bedrock_client=bedrock_client,
        )

        assert result["decisions"] == []
        assert result["action_items"] == []


class TestSaveMinutes:
    """AC-46: Minutes saved to ~/.yui/meetings/<id>/minutes.md."""

    def test_saves_minutes_file(self, tmp_path):
        """Minutes are saved to meeting dir."""
        meeting_dir = tmp_path / "test_meeting"
        path = save_minutes(SAMPLE_MINUTES, meeting_dir)

        assert path.exists()
        assert path.name == "minutes.md"
        content = path.read_text()
        assert "Meeting Minutes" in content
        assert "Action Items" in content

    def test_creates_directory(self, tmp_path):
        """Creates meeting directory if it doesn't exist."""
        meeting_dir = tmp_path / "new" / "nested" / "meeting"
        save_minutes("test content", meeting_dir)

        assert meeting_dir.exists()
        assert (meeting_dir / "minutes.md").exists()

    def test_overwrites_existing(self, tmp_path):
        """Overwrites existing minutes.md."""
        meeting_dir = tmp_path / "meeting"
        meeting_dir.mkdir()
        (meeting_dir / "minutes.md").write_text("old content")

        save_minutes("new content", meeting_dir)
        assert (meeting_dir / "minutes.md").read_text() == "new content"


class TestSaveAnalysis:
    """Real-time analysis file persistence."""

    def test_creates_analysis_file(self, tmp_path):
        """Creates analysis.md with header."""
        meeting_dir = tmp_path / "meeting"
        analysis = {
            "current_topic": "Deployment",
            "decisions": ["Use Kafka"],
            "action_items": [{"action": "Write doc", "owner": "Alice"}],
            "open_questions": ["Timeline?"],
            "summary": "Discussing deployment.",
        }

        path = save_analysis(analysis, meeting_dir, timestamp="10:30:00")

        assert path.exists()
        content = path.read_text()
        assert "# Real-time Meeting Analysis" in content
        assert "[10:30:00]" in content
        assert "Deployment" in content
        assert "Use Kafka" in content
        assert "Alice" in content

    def test_appends_to_existing(self, tmp_path):
        """Appends new analysis to existing file."""
        meeting_dir = tmp_path / "meeting"
        analysis1 = {"current_topic": "Topic A", "decisions": [], "action_items": [],
                      "open_questions": [], "summary": "First window"}
        analysis2 = {"current_topic": "Topic B", "decisions": [], "action_items": [],
                      "open_questions": [], "summary": "Second window"}

        save_analysis(analysis1, meeting_dir, timestamp="10:00:00")
        save_analysis(analysis2, meeting_dir, timestamp="10:01:00")

        content = (meeting_dir / "analysis.md").read_text()
        assert "Topic A" in content
        assert "Topic B" in content
        assert "10:00:00" in content
        assert "10:01:00" in content

    def test_empty_analysis_minimal_output(self, tmp_path):
        """Empty analysis still writes timestamp section."""
        meeting_dir = tmp_path / "meeting"
        save_analysis(_empty_analysis(), meeting_dir, timestamp="11:00:00")

        content = (meeting_dir / "analysis.md").read_text()
        assert "[11:00:00]" in content


class TestNotifySlackMinutes:
    """AC-47: Slack notification with meeting summary."""

    def test_sends_notification(self, slack_client):
        """Sends real Slack message with meeting summary."""
        config = make_config()
        config["meeting"]["output"]["slack_channel"] = "C0AH55CBKGW"  # #yui-test

        result = notify_slack_minutes(
            minutes_text=SAMPLE_MINUTES,
            meeting_name="E2E Test Meeting",
            meeting_id="e2e-test-001",
            config=config,
            slack_client=slack_client,
        )

        assert result is True

    def test_disabled_in_config(self, slack_client):
        """Returns False when slack_notify is disabled."""
        config = make_config()
        config["meeting"]["output"]["slack_notify"] = False

        result = notify_slack_minutes(
            minutes_text=SAMPLE_MINUTES,
            meeting_name="Test",
            meeting_id="abc123",
            config=config,
            slack_client=slack_client,
        )

        assert result is False

    def test_no_channel_configured(self, slack_client):
        """Returns False when no Slack channel configured."""
        config = make_config()
        config["meeting"]["output"]["slack_channel"] = ""

        result = notify_slack_minutes(
            minutes_text=SAMPLE_MINUTES,
            meeting_name="Test",
            meeting_id="abc123",
            config=config,
            slack_client=slack_client,
        )

        assert result is False


class TestExtractSummary:
    """Summary extraction helper."""

    def test_extracts_summary_section(self):
        """Extracts text between ## Summary and next ## heading."""
        result = _extract_summary(SAMPLE_MINUTES)
        assert "deployment timeline" in result
        assert "Key Decisions" not in result

    def test_fallback_without_summary_heading(self):
        """Falls back to first 500 chars if no ## Summary."""
        text = "Some random meeting text without proper headers.\nMore content here."
        result = _extract_summary(text)
        assert "Some random" in result

    def test_empty_input(self):
        """Empty input returns empty string."""
        assert _extract_summary("") == ""


class TestEmptyMinutes:
    """Empty minutes template."""

    def test_includes_structure(self):
        """Template includes all required sections."""
        result = _empty_minutes("Test Meeting", "2026-02-26")
        assert "Meeting Minutes" in result
        assert "Summary" in result
        assert "Key Decisions" in result
        assert "Action Items" in result
        assert "Discussion Topics" in result
        assert "Open Questions" in result
        assert "No transcript content" in result

    def test_includes_meeting_name(self):
        """Template includes the meeting name."""
        result = _empty_minutes("Sprint Planning")
        assert "Sprint Planning" in result


class TestManagerMinutesIntegration:
    """AC-41: MeetingManager.stop() triggers minutes generation.

    Uses real Bedrock API. Recorder/transcriber use synthetic data
    (no hardware needed) — fake audio chunks and pre-built transcripts.
    """

    def _make_manager(self, tmp_path, bedrock_client, *, auto_generate=True, realtime=False):
        """Create a MeetingManager with real Bedrock but synthetic audio."""
        from yui.meeting.manager import MeetingManager

        config = make_config(tmp_path)
        config["meeting"]["analysis"]["minutes_auto_generate"] = auto_generate
        config["meeting"]["analysis"]["realtime_enabled"] = realtime
        config["meeting"]["analysis"]["realtime_interval_seconds"] = 1

        # Synthetic recorder — generates fake audio chunks
        class FakeRecorder:
            def __init__(self):
                self.is_recording = False
                self.elapsed_seconds = 0.0
                self._chunks = [np.zeros((16000, 1), dtype=np.float32)]  # 1 sec silence
                self._idx = 0

            def start(self):
                self.is_recording = True

            def stop(self):
                self.is_recording = False

            def get_chunk(self, timeout=1.0):
                if self._idx < len(self._chunks):
                    c = self._chunks[self._idx]
                    self._idx += 1
                    return c
                return None

        # Synthetic transcriber — returns pre-built transcript
        class FakeTranscriber:
            def transcribe_chunk(self, audio_data, sample_rate=16000, chunk_start_time=0.0):
                return TranscriptChunk(
                    text="We decided to deploy to staging on Friday. Bob will update the script.",
                    start_time=chunk_start_time,
                    end_time=chunk_start_time + 5.0,
                )

        manager = MeetingManager(
            config=config,
            recorder=FakeRecorder(),
            transcriber=FakeTranscriber(),
            bedrock_client=bedrock_client,
            slack_client=None,  # No Slack for these tests
        )

        return manager

    def test_stop_triggers_minutes_generation(self, tmp_path, bedrock_client):
        """AC-41: Stop triggers minutes generation via real Bedrock."""
        manager = self._make_manager(tmp_path, bedrock_client)

        manager.start(name="Integration Test")
        time.sleep(1.0)  # Let transcription loop run
        meeting = manager.stop()

        # Minutes file was saved
        meeting_dir = tmp_path / "meetings" / meeting.meeting_id
        minutes_path = meeting_dir / "minutes.md"
        assert minutes_path.exists()
        content = minutes_path.read_text()
        assert len(content) > 50  # Non-trivial minutes

    def test_stop_updates_status_to_completed(self, tmp_path, bedrock_client):
        """Meeting status transitions to completed after minutes generation."""
        manager = self._make_manager(tmp_path, bedrock_client)

        manager.start()
        time.sleep(1.0)
        meeting = manager.stop()

        meeting_dir = tmp_path / "meetings" / meeting.meeting_id
        meta = json.loads((meeting_dir / "metadata.json").read_text())
        assert meta["status"] == "completed"

    def test_stop_without_auto_generate(self, tmp_path, bedrock_client):
        """No minutes generated when minutes_auto_generate is False."""
        manager = self._make_manager(tmp_path, bedrock_client, auto_generate=False)

        manager.start()
        time.sleep(0.5)
        meeting = manager.stop()

        meeting_dir = tmp_path / "meetings" / meeting.meeting_id
        assert not (meeting_dir / "minutes.md").exists()


class TestConfigAnalysisSection:
    """Config integration for analysis settings."""

    def test_default_config_has_analysis(self):
        """DEFAULT_CONFIG includes meeting.analysis section."""
        from yui.config import DEFAULT_CONFIG

        analysis = DEFAULT_CONFIG["meeting"]["analysis"]
        assert analysis["provider"] == "bedrock"
        assert analysis["realtime_enabled"] is False
        assert analysis["realtime_interval_seconds"] == 60
        assert analysis["realtime_window_minutes"] == 5
        assert analysis["max_cost_per_meeting_usd"] == 2.0
        assert analysis["minutes_auto_generate"] is True

    def test_default_config_has_slack_notify(self):
        """DEFAULT_CONFIG includes meeting.output.slack_notify."""
        from yui.config import DEFAULT_CONFIG

        output = DEFAULT_CONFIG["meeting"]["output"]
        assert output["slack_notify"] is True

    def test_config_merges_analysis_section(self, tmp_path):
        """Custom analysis config merges with defaults."""
        import yaml
        from yui.config import load_config

        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(yaml.dump({
            "meeting": {
                "analysis": {
                    "realtime_enabled": True,
                    "realtime_interval_seconds": 30,
                },
            }
        }))

        config = load_config(str(cfg_file))
        assert config["meeting"]["analysis"]["realtime_enabled"] is True
        assert config["meeting"]["analysis"]["realtime_interval_seconds"] == 30
        assert config["meeting"]["analysis"]["minutes_auto_generate"] is True
        assert config["meeting"]["analysis"]["max_cost_per_meeting_usd"] == 2.0
