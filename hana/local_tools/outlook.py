"""HANA Outlook tools — Calendar + Mail via macOS AppleScript.

macOS-only implementation using osascript to interact with
Microsoft Outlook for Mac.
"""

from __future__ import annotations

import json
import logging
import subprocess
from typing import Any

from strands import tool

logger = logging.getLogger(__name__)

_tool_config: dict[str, Any] = {}


def configure(config: dict[str, Any]) -> None:
    """Store Outlook tool configuration.

    Args:
        config: The ``tools.outlook`` section of HANA config.
    """
    global _tool_config
    _tool_config = config


def _run_applescript(script: str) -> str:
    """Execute an AppleScript via osascript.

    Args:
        script: AppleScript source code.

    Returns:
        Standard output from osascript.

    Raises:
        RuntimeError: If osascript fails.
    """
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"AppleScript error: {result.stderr.strip()}")
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        raise RuntimeError("AppleScript timed out after 30s")


@tool
def outlook_calendar(
    action: str,
    start_date: str = "",
    end_date: str = "",
    title: str = "",
    body: str = "",
) -> dict[str, Any]:
    """Read or create Outlook calendar events on macOS.

    Uses AppleScript to interact with Microsoft Outlook for Mac.

    Args:
        action: One of "list", "create", or "search".
        start_date: Start date in ISO format (for list/create).
        end_date: End date in ISO format (for list/create).
        title: Event title (for create).
        body: Event body/notes (for create).

    Returns:
        Dictionary with events or creation result.
    """
    if not _tool_config.get("enabled", False):
        return {"error": "Outlook tool is disabled. Enable in config.yaml."}

    if action == "list":
        script = f'''
        tell application "Microsoft Outlook"
            set eventList to {{}}
            set calEvents to calendar events of default calendar
            repeat with evt in calEvents
                set eventInfo to (subject of evt) & " | " & (start time of evt as string)
                set end of eventList to eventInfo
            end repeat
            return eventList as string
        end tell
        '''
        try:
            output = _run_applescript(script)
            events = [e.strip() for e in output.split(",") if e.strip()]
            return {"events": events, "count": len(events)}
        except RuntimeError as exc:
            return {"events": [], "error": str(exc)}

    elif action == "create":
        if not title:
            return {"error": "title is required for create action"}
        script = f'''
        tell application "Microsoft Outlook"
            set newEvent to make new calendar event with properties {{subject:"{title}", content:"{body}"}}
            return subject of newEvent
        end tell
        '''
        try:
            output = _run_applescript(script)
            return {"created": True, "title": output}
        except RuntimeError as exc:
            return {"created": False, "error": str(exc)}

    else:
        return {"error": f"Unknown action: {action}. Use 'list' or 'create'."}


@tool
def outlook_mail(
    action: str,
    folder: str = "Inbox",
    limit: int = 10,
    to: str = "",
    subject: str = "",
    body: str = "",
) -> dict[str, Any]:
    """Read or send Outlook emails on macOS.

    Uses AppleScript to interact with Microsoft Outlook for Mac.

    Args:
        action: One of "list", "read", "send", or "search".
        folder: Mail folder name (default "Inbox").
        limit: Maximum number of messages to return (default 10).
        to: Recipient email address (for send).
        subject: Email subject (for send).
        body: Email body text (for send).

    Returns:
        Dictionary with messages or send result.
    """
    if not _tool_config.get("enabled", False):
        return {"error": "Outlook tool is disabled. Enable in config.yaml."}

    if action == "list":
        script = f'''
        tell application "Microsoft Outlook"
            set msgList to {{}}
            set msgs to messages of folder "{folder}" of default account
            set msgCount to 0
            repeat with msg in msgs
                if msgCount >= {limit} then exit repeat
                set msgInfo to (subject of msg) & " | " & (time sent of msg as string)
                set end of msgList to msgInfo
                set msgCount to msgCount + 1
            end repeat
            return msgList as string
        end tell
        '''
        try:
            output = _run_applescript(script)
            messages = [m.strip() for m in output.split(",") if m.strip()]
            return {"messages": messages, "count": len(messages)}
        except RuntimeError as exc:
            return {"messages": [], "error": str(exc)}

    elif action == "send":
        if not to or not subject:
            return {"error": "Both 'to' and 'subject' are required for send"}
        # Create draft instead of sending directly (safety)
        script = f'''
        tell application "Microsoft Outlook"
            set newMsg to make new outgoing message with properties {{subject:"{subject}", content:"{body}"}}
            make new to recipient at newMsg with properties {{email address:{{address:"{to}"}}}}
            return "Draft created: " & subject of newMsg
        end tell
        '''
        try:
            output = _run_applescript(script)
            return {"sent": False, "draft_created": True, "message": output}
        except RuntimeError as exc:
            return {"sent": False, "error": str(exc)}

    else:
        return {"error": f"Unknown action: {action}. Use 'list' or 'send'."}
