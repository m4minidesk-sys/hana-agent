"""Tests for yui.meeting.minutes — AC-41, AC-45, AC-46, AC-47, AC-50.

All Bedrock API calls are mocked. No real API invocations.
"""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

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

pytestmark = pytest.mark.component



def make_config(tmp_path=None):
    """Create a test config dict."""
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
                "slack_channel": "C12345TEST",
            },
        },
        "slack": {
            "bot_token": "xoxb-test-token",
        },
    }
    return config


def make_bedrock_response(text: str) -> dict:
    """Create a mock Bedrock Converse API response."""
    return {
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"text": text}],
            }
        },
        "usage": {"inputTokens": 100, "outputTokens": 200},
        "stopReason": "end_turn",
    }


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

SAMPLE_ANALYSIS_JSON = json.dumps({
    "current_topic": "Deployment strategy",
    "decisions": ["Use Kafka instead of SQS"],
    "action_items": [
        {"action": "Send deployment doc", "owner": "Bob"},
    ],
    "open_questions": ["What about rollback strategy?"],
    "summary": "Team is discussing deployment approach for the new service.",
})


class TestPostMeetingMinutes:
    """AC-45: Bedrock generates structured meeting minutes."""

    def test_generates_minutes_from_transcript(self):
        """Bedrock Converse API generates structured minutes."""
        mock_client = MagicMock()
        mock_client.converse.return_value = make_bedrock_response(SAMPLE_MINUTES)

        config = make_config()
        result = post_meeting_minutes(
            transcript="Hello, let's discuss the deployment...",
            config=config,
            meeting_name="Weekly Standup",
            meeting_date="2026-02-26T10:00:00",
            bedrock_client=mock_client,
        )

        assert "Meeting Minutes" in result
        assert "Key Decisions" in result
        assert "Action Items" in result
        mock_client.converse.assert_called_once()

    def test_uses_correct_model_id(self):
        """Uses model ID from config."""
        mock_client = MagicMock()
        mock_client.converse.return_value = make_bedrock_response(SAMPLE_MINUTES)

        config = make_config()
        config["model"]["model_id"] = "us.anthropic.claude-haiku-4-20250514-v1:0"

        post_meeting_minutes(
            transcript="test transcript",
            config=config,
            bedrock_client=mock_client,
        )

        call_args = mock_client.converse.call_args
        assert call_args.kwargs["modelId"] == "us.anthropic.claude-haiku-4-20250514-v1:0"

    def test_includes_meeting_name_in_prompt(self):
        """Meeting name is included in the user message."""
        mock_client = MagicMock()
        mock_client.converse.return_value = make_bedrock_response(SAMPLE_MINUTES)

        config = make_config()
        post_meeting_minutes(
            transcript="test",
            config=config,
            meeting_name="Sprint Planning",
            bedrock_client=mock_client,
        )

        call_args = mock_client.converse.call_args
        user_content = call_args.kwargs["messages"][0]["content"][0]["text"]
        assert "Sprint Planning" in user_content

    def test_empty_transcript_returns_template(self):
        """Empty transcript returns a template without API call."""
        mock_client = MagicMock()
        config = make_config()

        result = post_meeting_minutes(
            transcript="   ",
            config=config,
            meeting_name="Empty Meeting",
            bedrock_client=mock_client,
        )

        assert "No transcript content" in result
        mock_client.converse.assert_not_called()

    def test_bedrock_error_raises_runtime_error(self):
        """Bedrock API failure raises RuntimeError."""
        mock_client = MagicMock()
        mock_client.converse.side_effect = Exception("Throttling")

        config = make_config()
        with pytest.raises(RuntimeError, match="Failed to generate meeting minutes"):
            post_meeting_minutes(
                transcript="test transcript",
                config=config,
                bedrock_client=mock_client,
            )

    def test_empty_bedrock_response_returns_template(self):
        """Empty Bedrock response falls back to template."""
        mock_client = MagicMock()
        mock_client.converse.return_value = make_bedrock_response("  ")

        config = make_config()
        result = post_meeting_minutes(
            transcript="test transcript",
            config=config,
            bedrock_client=mock_client,
        )

        assert "No transcript content" in result

    def test_system_prompt_is_included(self):
        """System prompt for minutes generation is sent to Bedrock."""
        mock_client = MagicMock()
        mock_client.converse.return_value = make_bedrock_response(SAMPLE_MINUTES)

        config = make_config()
        post_meeting_minutes(
            transcript="test",
            config=config,
            bedrock_client=mock_client,
        )

        call_args = mock_client.converse.call_args
        system = call_args.kwargs["system"]
        assert len(system) > 0
        assert "meeting analyst" in system[0]["text"].lower()

    def test_temperature_is_low(self):
        """Minutes generation uses low temperature for consistency."""
        mock_client = MagicMock()
        mock_client.converse.return_value = make_bedrock_response(SAMPLE_MINUTES)

        config = make_config()
        post_meeting_minutes(
            transcript="test",
            config=config,
            bedrock_client=mock_client,
        )

        call_args = mock_client.converse.call_args
        inference_config = call_args.kwargs["inferenceConfig"]
        assert inference_config["temperature"] <= 0.5


class TestRealTimeAnalysis:
    """AC-50: Real-time analysis updates every 60s during active meeting."""

    def test_returns_structured_analysis(self):
        """Real-time analysis returns structured dict."""
        mock_client = MagicMock()
        mock_client.converse.return_value = make_bedrock_response(SAMPLE_ANALYSIS_JSON)

        config = make_config()
        result = real_time_analysis(
            transcript_window="Bob said he'll send the doc by Friday.",
            config=config,
            bedrock_client=mock_client,
        )

        assert result["current_topic"] == "Deployment strategy"
        assert len(result["decisions"]) == 1
        assert len(result["action_items"]) == 1
        assert result["action_items"][0]["owner"] == "Bob"
        assert len(result["open_questions"]) == 1

    def test_empty_transcript_returns_empty_analysis(self):
        """Empty transcript returns empty analysis without API call."""
        mock_client = MagicMock()
        config = make_config()

        result = real_time_analysis(
            transcript_window="  ",
            config=config,
            bedrock_client=mock_client,
        )

        assert result["decisions"] == []
        assert result["action_items"] == []
        mock_client.converse.assert_not_called()

    def test_handles_json_in_markdown_block(self):
        """Handles JSON wrapped in markdown code block."""
        wrapped = '```json\n' + SAMPLE_ANALYSIS_JSON + '\n```'
        mock_client = MagicMock()
        mock_client.converse.return_value = make_bedrock_response(wrapped)

        config = make_config()
        result = real_time_analysis(
            transcript_window="test transcript",
            config=config,
            bedrock_client=mock_client,
        )

        assert result["current_topic"] == "Deployment strategy"

    def test_bedrock_error_raises_runtime_error(self):
        """Bedrock API failure raises RuntimeError."""
        mock_client = MagicMock()
        mock_client.converse.side_effect = Exception("Service unavailable")

        config = make_config()
        with pytest.raises(RuntimeError, match="Real-time analysis failed"):
            real_time_analysis(
                transcript_window="test",
                config=config,
                bedrock_client=mock_client,
            )

    def test_invalid_json_returns_empty(self):
        """Invalid JSON response returns empty analysis."""
        mock_client = MagicMock()
        mock_client.converse.return_value = make_bedrock_response("not json at all, no braces")

        config = make_config()
        result = real_time_analysis(
            transcript_window="test",
            config=config,
            bedrock_client=mock_client,
        )

        assert result == _empty_analysis()

    def test_uses_lower_max_tokens(self):
        """Real-time analysis uses smaller max tokens than full minutes."""
        mock_client = MagicMock()
        mock_client.converse.return_value = make_bedrock_response(SAMPLE_ANALYSIS_JSON)

        config = make_config()
        real_time_analysis(
            transcript_window="test",
            config=config,
            bedrock_client=mock_client,
        )

        call_args = mock_client.converse.call_args
        assert call_args.kwargs["inferenceConfig"]["maxTokens"] <= 1024


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
    """AC-47: Slack notification with meeting summary posted after meeting ends."""

    def test_sends_notification(self):
        """Sends Slack message with meeting summary."""
        mock_client = MagicMock()
        config = make_config()

        result = notify_slack_minutes(
            minutes_text=SAMPLE_MINUTES,
            meeting_name="Weekly Standup",
            meeting_id="abc123",
            config=config,
            slack_client=mock_client,
        )

        assert result is True
        mock_client.chat_postMessage.assert_called_once()
        call_args = mock_client.chat_postMessage.call_args
        assert call_args.kwargs["channel"] == "C12345TEST"
        assert "Minutes Ready" in call_args.kwargs["text"]
        assert "Weekly Standup" in call_args.kwargs["text"]

    def test_includes_summary_in_message(self):
        """Slack message includes the summary section from minutes."""
        mock_client = MagicMock()
        config = make_config()

        notify_slack_minutes(
            minutes_text=SAMPLE_MINUTES,
            meeting_name="Test",
            meeting_id="abc123",
            config=config,
            slack_client=mock_client,
        )

        call_args = mock_client.chat_postMessage.call_args
        assert "deployment timeline" in call_args.kwargs["text"]

    def test_disabled_in_config(self):
        """Returns False when slack_notify is disabled."""
        mock_client = MagicMock()
        config = make_config()
        config["meeting"]["output"]["slack_notify"] = False

        result = notify_slack_minutes(
            minutes_text=SAMPLE_MINUTES,
            meeting_name="Test",
            meeting_id="abc123",
            config=config,
            slack_client=mock_client,
        )

        assert result is False
        mock_client.chat_postMessage.assert_not_called()

    def test_no_channel_configured(self):
        """Returns False when no Slack channel configured."""
        mock_client = MagicMock()
        config = make_config()
        config["meeting"]["output"]["slack_channel"] = ""

        result = notify_slack_minutes(
            minutes_text=SAMPLE_MINUTES,
            meeting_name="Test",
            meeting_id="abc123",
            config=config,
            slack_client=mock_client,
        )

        assert result is False

    def test_slack_error_returns_false(self):
        """Slack API error returns False (non-fatal)."""
        mock_client = MagicMock()
        mock_client.chat_postMessage.side_effect = Exception("channel_not_found")
        config = make_config()

        result = notify_slack_minutes(
            minutes_text=SAMPLE_MINUTES,
            meeting_name="Test",
            meeting_id="abc123",
            config=config,
            slack_client=mock_client,
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
    """AC-41: yui meeting stop triggers minutes generation.

    Tests the integration of minutes generation into MeetingManager.stop().
    """

    def _make_manager(self, tmp_path, *, auto_generate=True, realtime=False):
        """Create a MeetingManager with mock components."""
        from yui.meeting.manager import MeetingManager

        config = make_config(tmp_path)
        config["meeting"]["analysis"]["minutes_auto_generate"] = auto_generate
        config["meeting"]["analysis"]["realtime_enabled"] = realtime
        config["meeting"]["analysis"]["realtime_interval_seconds"] = 1  # Fast for tests

        chunks = [np.random.randn(16000, 1).astype(np.float32)]
        responses = [
            TranscriptChunk(text="We decided to use Kafka for the new service.",
                            start_time=0.0, end_time=5.0)
        ]

        mock_recorder = MagicMock()
        mock_recorder.is_recording = True
        mock_recorder.elapsed_seconds = 10.0
        mock_recorder.start = MagicMock()
        mock_recorder.stop = MagicMock()
        _chunk_index = [0]

        def get_chunk(timeout=1.0):
            if _chunk_index[0] < len(chunks):
                c = chunks[_chunk_index[0]]
                _chunk_index[0] += 1
                return c
            return None

        mock_recorder.get_chunk = get_chunk

        mock_transcriber = MagicMock()
        _resp_index = [0]

        def transcribe_chunk(audio_data, sample_rate=16000, chunk_start_time=0.0):
            if _resp_index[0] < len(responses):
                r = responses[_resp_index[0]]
                _resp_index[0] += 1
                return r
            return None

        mock_transcriber.transcribe_chunk = transcribe_chunk

        mock_bedrock = MagicMock()
        mock_bedrock.converse.return_value = make_bedrock_response(SAMPLE_MINUTES)

        mock_slack = MagicMock()

        manager = MeetingManager(
            config=config,
            recorder=mock_recorder,
            transcriber=mock_transcriber,
            bedrock_client=mock_bedrock,
            slack_client=mock_slack,
        )

        return manager, mock_bedrock, mock_slack

    def test_stop_triggers_minutes_generation(self, tmp_path):
        """AC-41: Stop triggers minutes generation via Bedrock."""
        manager, mock_bedrock, mock_slack = self._make_manager(tmp_path)

        manager.start(name="Integration Test")
        time.sleep(0.5)
        meeting = manager.stop()

        # Bedrock was called to generate minutes
        mock_bedrock.converse.assert_called()

        # Minutes file was saved
        meeting_dir = tmp_path / "meetings" / meeting.meeting_id
        minutes_path = meeting_dir / "minutes.md"
        assert minutes_path.exists()
        assert "Meeting Minutes" in minutes_path.read_text()

    def test_stop_sends_slack_notification(self, tmp_path):
        """AC-47: Slack notification sent after minutes generation."""
        manager, mock_bedrock, mock_slack = self._make_manager(tmp_path)

        manager.start(name="Slack Test")
        time.sleep(0.5)
        manager.stop()

        mock_slack.chat_postMessage.assert_called()

    def test_stop_updates_status_to_completed(self, tmp_path):
        """Meeting status transitions: STOPPED → GENERATING_MINUTES → COMPLETED."""
        manager, mock_bedrock, mock_slack = self._make_manager(tmp_path)

        manager.start()
        time.sleep(0.5)
        meeting = manager.stop()

        # After stop, status should be COMPLETED (minutes were generated)
        # Check the metadata file for final status
        meeting_dir = tmp_path / "meetings" / meeting.meeting_id
        meta = json.loads((meeting_dir / "metadata.json").read_text())
        assert meta["status"] == "completed"

    def test_stop_without_auto_generate(self, tmp_path):
        """No minutes generated when minutes_auto_generate is False."""
        manager, mock_bedrock, _ = self._make_manager(tmp_path, auto_generate=False)

        manager.start()
        time.sleep(0.5)
        meeting = manager.stop()

        mock_bedrock.converse.assert_not_called()

        meeting_dir = tmp_path / "meetings" / meeting.meeting_id
        assert not (meeting_dir / "minutes.md").exists()

    def test_minutes_generation_failure_does_not_crash_stop(self, tmp_path):
        """Minutes generation failure is caught — stop() still completes."""
        manager, mock_bedrock, _ = self._make_manager(tmp_path)
        mock_bedrock.converse.side_effect = Exception("API Error")

        manager.start()
        time.sleep(0.5)
        meeting = manager.stop()

        # Stop completed (did not raise)
        assert meeting.stop_time is not None

    def test_realtime_analysis_thread_starts(self, tmp_path):
        """AC-50: Real-time analysis thread starts when enabled."""
        manager, mock_bedrock, _ = self._make_manager(tmp_path, realtime=True)

        manager.start(name="Realtime Test")
        assert manager._analysis_thread is not None
        assert manager._analysis_thread.is_alive()

        time.sleep(0.3)
        manager.stop()

    def test_realtime_analysis_not_started_when_disabled(self, tmp_path):
        """Analysis thread not started when realtime_enabled is False."""
        manager, _, _ = self._make_manager(tmp_path, realtime=False)

        manager.start()
        assert manager._analysis_thread is None
        manager.stop()


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
        # Defaults preserved
        assert config["meeting"]["analysis"]["minutes_auto_generate"] is True
        assert config["meeting"]["analysis"]["max_cost_per_meeting_usd"] == 2.0
