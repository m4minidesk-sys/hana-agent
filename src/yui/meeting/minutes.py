"""Meeting minutes generation via Bedrock Converse API.

Provides:
- post_meeting_minutes(): Full transcript → structured minutes (markdown)
- real_time_analysis(): Sliding-window transcript → live insights (dict)
- Slack notification for completed minutes

Uses Bedrock Converse API (Claude) for LLM-powered analysis.
No direct Anthropic SDK dependency — uses boto3 bedrock-runtime only.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default model for minutes generation
DEFAULT_MODEL_ID = "us.anthropic.claude-haiku-3-20250307-v1:0"
DEFAULT_REGION = "us-east-1"
DEFAULT_MAX_TOKENS = 4096

MINUTES_SYSTEM_PROMPT = """\
You are a professional meeting analyst. Generate structured meeting minutes \
from the provided transcript.

Output format (Markdown):

# Meeting Minutes — {date} {time}

## Summary
(2-3 paragraph executive summary of the meeting)

## Key Decisions
1. [Decision] — [Context/Rationale]

## Action Items
| # | Action | Owner | Due Date | Status |
|---|--------|-------|----------|--------|
| 1 | ... | ... | ... | Open |

## Discussion Topics
### Topic 1: [Title]
- Key points discussed
- Outcome / Next steps

## Open Questions
- Questions raised but not resolved during the meeting

Rules:
- Be concise but thorough
- If no action items/decisions are found, say "None identified"
- Use the actual content from the transcript — do not fabricate
- For action items, infer owner/due date if mentioned; otherwise mark as "TBD"
- Write in the same language as the transcript (e.g., Japanese if transcript is Japanese)
"""

REALTIME_SYSTEM_PROMPT = """\
You are a live meeting analyst. Based on the following transcript excerpt \
(last ~5 minutes of an ongoing meeting), identify:

1. **Decisions**: Any decisions being made or agreed upon
2. **Action Items**: Tasks assigned to specific people
3. **Open Questions**: Questions asked but not yet answered
4. **Topic**: Current discussion topic

Respond in JSON format:
{
  "current_topic": "string",
  "decisions": ["string"],
  "action_items": [{"action": "string", "owner": "string"}],
  "open_questions": ["string"],
  "summary": "1-2 sentence summary of this window"
}

Rules:
- Only include items actually mentioned in the transcript
- If nothing notable, return empty lists
- Respond in the same language as the transcript
"""


def _create_bedrock_client(config: dict[str, Any]) -> Any:
    """Create a Bedrock Runtime client from config.

    Args:
        config: Main Yui config dict.

    Returns:
        boto3 bedrock-runtime client.
    """
    import boto3

    model_config = config.get("model", {})
    region = model_config.get("region", DEFAULT_REGION)
    return boto3.client("bedrock-runtime", region_name=region)


def _get_model_id(config: dict[str, Any]) -> str:
    """Get model ID from config."""
    return (
        config.get("meeting", {}).get("model_id")
        or config.get("model", {}).get("model_id")
        or DEFAULT_MODEL_ID
    )


def _get_max_tokens(config: dict[str, Any]) -> int:
    """Get max tokens from config."""
    return config.get("model", {}).get("max_tokens", DEFAULT_MAX_TOKENS)


def post_meeting_minutes(
    transcript: str,
    config: dict[str, Any],
    meeting_name: str = "",
    meeting_date: str = "",
    bedrock_client: Any = None,
) -> str:
    """Generate structured meeting minutes from a full transcript.

    Calls Bedrock Converse API with the transcript and a structured prompt
    to produce formatted meeting minutes in Markdown.

    Args:
        transcript: Full meeting transcript text.
        config: Main Yui config dict (for model settings).
        meeting_name: Optional meeting name for the header.
        meeting_date: Optional date string for the header.
        bedrock_client: Optional pre-created boto3 client (for DI/testing).

    Returns:
        Markdown-formatted meeting minutes string.

    Raises:
        RuntimeError: If Bedrock API call fails.
    """
    if not transcript.strip():
        return _empty_minutes(meeting_name, meeting_date)

    if bedrock_client is None:
        bedrock_client = _create_bedrock_client(config)

    model_id = _get_model_id(config)
    max_tokens = _get_max_tokens(config)

    # Build context with meeting info
    user_message = f"Meeting: {meeting_name or 'Untitled'}\n"
    if meeting_date:
        user_message += f"Date: {meeting_date}\n"
    user_message += f"\n--- TRANSCRIPT ---\n{transcript}\n--- END TRANSCRIPT ---"

    try:
        response = bedrock_client.converse(
            modelId=model_id,
            system=[{"text": MINUTES_SYSTEM_PROMPT}],
            messages=[
                {
                    "role": "user",
                    "content": [{"text": user_message}],
                }
            ],
            inferenceConfig={"maxTokens": max_tokens, "temperature": 0.3},
        )

        # Extract text from Converse response
        output = response.get("output", {})
        message = output.get("message", {})
        content_blocks = message.get("content", [])

        minutes_text = ""
        for block in content_blocks:
            if "text" in block:
                minutes_text += block["text"]

        if not minutes_text.strip():
            logger.warning("Bedrock returned empty minutes, using fallback")
            return _empty_minutes(meeting_name, meeting_date)

        return minutes_text

    except Exception as e:
        logger.error("Bedrock Converse API failed for minutes generation: %s", e)
        raise RuntimeError(f"Failed to generate meeting minutes: {e}") from e


def real_time_analysis(
    transcript_window: str,
    config: dict[str, Any],
    bedrock_client: Any = None,
) -> dict[str, Any]:
    """Analyze a sliding window of transcript for live insights.

    Called every ~60 seconds during an active meeting with the last
    ~5 minutes of transcript text.

    Args:
        transcript_window: Recent transcript text (sliding window).
        config: Main Yui config dict.
        bedrock_client: Optional pre-created boto3 client (for DI/testing).

    Returns:
        Dict with keys: current_topic, decisions, action_items,
        open_questions, summary.

    Raises:
        RuntimeError: If Bedrock API call fails.
    """
    if not transcript_window.strip():
        return _empty_analysis()

    if bedrock_client is None:
        bedrock_client = _create_bedrock_client(config)

    model_id = _get_model_id(config)

    try:
        response = bedrock_client.converse(
            modelId=model_id,
            system=[{"text": REALTIME_SYSTEM_PROMPT}],
            messages=[
                {
                    "role": "user",
                    "content": [{"text": transcript_window}],
                }
            ],
            inferenceConfig={"maxTokens": 1024, "temperature": 0.2},
        )

        output = response.get("output", {})
        message = output.get("message", {})
        content_blocks = message.get("content", [])

        text = ""
        for block in content_blocks:
            if "text" in block:
                text += block["text"]

        if not text.strip():
            return _empty_analysis()

        # Parse JSON response
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            # Try to extract JSON from text (LLM sometimes wraps in markdown)
            import re

            json_match = re.search(r"\{.*\}", text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                logger.warning("Failed to parse real-time analysis JSON: %s", text[:200])
                return _empty_analysis()

        # Normalize result structure
        return {
            "current_topic": result.get("current_topic", ""),
            "decisions": result.get("decisions", []),
            "action_items": result.get("action_items", []),
            "open_questions": result.get("open_questions", []),
            "summary": result.get("summary", ""),
        }

    except json.JSONDecodeError:
        logger.warning("Failed to parse real-time analysis response")
        return _empty_analysis()
    except Exception as e:
        logger.error("Bedrock real-time analysis failed: %s", e)
        raise RuntimeError(f"Real-time analysis failed: {e}") from e


def save_minutes(
    minutes_text: str,
    meeting_dir: Path,
) -> Path:
    """Save generated minutes to a markdown file.

    Args:
        minutes_text: Markdown-formatted minutes content.
        meeting_dir: Directory for this meeting's files.

    Returns:
        Path to the saved minutes.md file.
    """
    meeting_dir.mkdir(parents=True, exist_ok=True)
    minutes_path = meeting_dir / "minutes.md"
    minutes_path.write_text(minutes_text, encoding="utf-8")
    logger.info("Minutes saved to %s", minutes_path)
    return minutes_path


def save_analysis(
    analysis: dict[str, Any],
    meeting_dir: Path,
    timestamp: Optional[str] = None,
) -> Path:
    """Append real-time analysis to analysis.md.

    Args:
        analysis: Analysis dict from real_time_analysis().
        meeting_dir: Directory for this meeting's files.
        timestamp: Optional timestamp string. Defaults to now.

    Returns:
        Path to the analysis.md file.
    """
    meeting_dir.mkdir(parents=True, exist_ok=True)
    analysis_path = meeting_dir / "analysis.md"

    if timestamp is None:
        timestamp = datetime.now().strftime("%H:%M:%S")

    entry = f"\n## [{timestamp}]\n"
    if analysis.get("current_topic"):
        entry += f"**Topic**: {analysis['current_topic']}\n"
    if analysis.get("summary"):
        entry += f"**Summary**: {analysis['summary']}\n"
    if analysis.get("decisions"):
        entry += "**Decisions**:\n"
        for d in analysis["decisions"]:
            entry += f"- {d}\n"
    if analysis.get("action_items"):
        entry += "**Action Items**:\n"
        for item in analysis["action_items"]:
            owner = item.get("owner", "TBD")
            entry += f"- {item.get('action', '')} (Owner: {owner})\n"
    if analysis.get("open_questions"):
        entry += "**Open Questions**:\n"
        for q in analysis["open_questions"]:
            entry += f"- {q}\n"

    # Create header if file doesn't exist
    if not analysis_path.exists():
        header = "# Real-time Meeting Analysis\n"
        analysis_path.write_text(header + entry, encoding="utf-8")
    else:
        with open(analysis_path, "a", encoding="utf-8") as f:
            f.write(entry)

    return analysis_path


def notify_slack_minutes(
    minutes_text: str,
    meeting_name: str,
    meeting_id: str,
    config: dict[str, Any],
    slack_client: Any = None,
) -> bool:
    """Post meeting minutes summary to Slack.

    Args:
        minutes_text: Full minutes markdown text.
        meeting_name: Meeting name for the notification.
        meeting_id: Meeting ID for reference.
        config: Main Yui config dict.
        slack_client: Optional pre-created Slack WebClient (for DI/testing).

    Returns:
        True if notification was sent successfully, False otherwise.
    """
    slack_cfg = config.get("slack", {})
    output_cfg = config.get("meeting", {}).get("output", {})

    if not output_cfg.get("slack_notify", True):
        logger.debug("Slack notification disabled in config")
        return False

    # Determine channel — use configured channel or default
    channel = output_cfg.get("slack_channel", "")
    if not channel:
        logger.debug("No Slack channel configured for meeting notifications")
        return False

    if slack_client is None:
        try:
            from slack_sdk import WebClient

            bot_token = slack_cfg.get("bot_token", "")
            if not bot_token:
                import os
                from dotenv import load_dotenv

                env_file = Path("~/.yui/.env").expanduser()
                if env_file.exists():
                    load_dotenv(env_file)
                bot_token = os.getenv("SLACK_BOT_TOKEN", "")

            if not bot_token:
                logger.warning("No Slack bot token available for minutes notification")
                return False

            slack_client = WebClient(token=bot_token)
        except ImportError:
            logger.warning("slack_sdk not installed, skipping Slack notification")
            return False

    # Build a concise Slack message (extract summary section)
    summary = _extract_summary(minutes_text)
    message = (
        f"📝 *Meeting Minutes Ready* — {meeting_name}\n"
        f"ID: `{meeting_id}`\n\n"
        f"{summary}\n\n"
        f"_Full minutes saved to `~/.yui/meetings/{meeting_id}/minutes.md`_"
    )

    try:
        slack_client.chat_postMessage(channel=channel, text=message)
        logger.info("Slack notification sent for meeting %s", meeting_id)
        return True
    except Exception as e:
        logger.warning("Failed to send Slack notification: %s", e)
        return False


def _extract_summary(minutes_text: str) -> str:
    """Extract the Summary section from minutes markdown.

    Args:
        minutes_text: Full minutes markdown.

    Returns:
        Summary text, or first 500 chars if no Summary section found.
    """
    lines = minutes_text.split("\n")
    in_summary = False
    summary_lines: list[str] = []

    for line in lines:
        if line.strip().startswith("## Summary"):
            in_summary = True
            continue
        if in_summary:
            if line.strip().startswith("## "):
                break
            summary_lines.append(line)

    if summary_lines:
        return "\n".join(summary_lines).strip()

    # Fallback: first 500 chars
    return minutes_text[:500].strip()


def _empty_minutes(meeting_name: str = "", meeting_date: str = "") -> str:
    """Generate empty minutes template when no transcript available."""
    date_str = meeting_date or datetime.now().strftime("%Y-%m-%d %H:%M")
    name = meeting_name or "Untitled Meeting"
    return (
        f"# Meeting Minutes — {name}\n\n"
        f"**Date**: {date_str}\n\n"
        "## Summary\n\n"
        "No transcript content was available for this meeting.\n\n"
        "## Key Decisions\n\nNone identified.\n\n"
        "## Action Items\n\n"
        "| # | Action | Owner | Due Date | Status |\n"
        "|---|--------|-------|----------|--------|\n\n"
        "## Discussion Topics\n\nNone.\n\n"
        "## Open Questions\n\nNone.\n"
    )


def _empty_analysis() -> dict[str, Any]:
    """Return empty analysis result."""
    return {
        "current_topic": "",
        "decisions": [],
        "action_items": [],
        "open_questions": [],
        "summary": "",
    }
