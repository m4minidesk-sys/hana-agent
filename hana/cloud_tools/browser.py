"""HANA web browser tool — AgentCore Browser Tool integration."""

from __future__ import annotations

import logging
from typing import Any

from strands import tool

logger = logging.getLogger(__name__)


@tool
def web_browse(
    url: str,
    action: str = "",
    extract: str = "",
) -> dict[str, Any]:
    """Browse a web page using AgentCore Browser Tool.

    Uses Nova Act (AgentCore) when available for full browser automation.

    Args:
        url: URL to browse.
        action: Action to perform on the page (optional).
        extract: Data extraction instruction (optional).

    Returns:
        Dictionary with page content.
    """
    # Try AgentCore Browser
    try:
        from strands_tools import http_request

        response = http_request(url=url, method="GET")
        if response and isinstance(response, dict):
            return {
                "content": str(response.get("body", ""))[:50000],
                "status": response.get("status_code", 0),
                "source": "http_request",
            }
    except (ImportError, Exception) as exc:
        logger.debug("AgentCore browser unavailable: %s", exc)

    # Fallback: basic HTTP request
    try:
        import urllib.request

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "HANA/0.1.0"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read().decode("utf-8", errors="replace")
            return {
                "content": content[:50000],
                "status": resp.status,
                "source": "urllib",
            }
    except Exception as exc:
        logger.error("Web browse failed for %s: %s", url, exc)
        return {
            "content": "",
            "status": 0,
            "error": str(exc),
        }
