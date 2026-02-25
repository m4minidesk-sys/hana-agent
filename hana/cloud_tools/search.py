"""HANA web search tool — searches the web via AgentCore or fallback."""

from __future__ import annotations

import logging
from typing import Any

from strands import tool

logger = logging.getLogger(__name__)


@tool
def web_search(query: str, count: int = 5) -> dict[str, Any]:
    """Search the web for information.

    Uses AgentCore web search when available, with a simple
    requests-based fallback.

    Args:
        query: Search query string.
        count: Number of results to return (default 5).

    Returns:
        Dictionary with search results.
    """
    # Try AgentCore search tool first
    try:
        from strands_tools import http_request

        # Use a search API endpoint
        response = http_request(
            url=f"https://api.search.brave.com/res/v1/web/search?q={query}&count={count}",
            method="GET",
        )
        if response and isinstance(response, dict):
            return response
    except (ImportError, Exception) as exc:
        logger.debug("AgentCore search unavailable, using fallback: %s", exc)

    # Fallback: return a message suggesting the user configure a search API
    return {
        "results": [],
        "message": f"Web search for '{query}' — no search API configured. "
                   "Configure Brave Search API key in config.yaml to enable.",
    }
