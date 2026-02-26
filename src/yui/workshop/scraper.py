"""Content Scraper — scrape Workshop Studio pages via Playwright (AC-70).

Playwright is an optional dependency.  Install it with::

    pip install yui-agent[workshop]

"""

from __future__ import annotations

import logging
import re
from urllib.parse import urljoin, urlparse

from yui.workshop.models import WorkshopPage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_PAGE_TIMEOUT_MS = 30_000

# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

_WORKSHOP_STUDIO_PATTERN = re.compile(
    r"^https?://catalog\.(?:us-east-1\.)?workshops\.aws/"
    r"|^https?://[a-z0-9-]+\.workshop\.aws/"
)


def normalise_workshop_url(url: str) -> str:
    """Return a canonical Workshop Studio URL (https, trailing-slash stripped)."""
    url = url.strip()
    if not url:
        raise ValueError("Workshop URL must not be empty")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme!r}")
    # Upgrade http → https
    if parsed.scheme == "http":
        url = "https" + url[4:]
    # Strip trailing slash for consistency
    return url.rstrip("/")


def validate_workshop_url(url: str) -> str:
    """Normalise *and* validate that *url* looks like a Workshop Studio URL.

    Returns the normalised URL or raises ``ValueError``.
    """
    url = normalise_workshop_url(url)
    if not _WORKSHOP_STUDIO_PATTERN.match(url):
        raise ValueError(
            f"URL does not look like a Workshop Studio URL: {url}"
        )
    return url


# ---------------------------------------------------------------------------
# Playwright import guard
# ---------------------------------------------------------------------------


def _require_playwright() -> None:
    """Raise a clear error if Playwright is not installed."""
    try:
        import playwright.async_api  # noqa: F401
    except ImportError:
        raise RuntimeError(
            "Playwright is required for workshop scraping but is not installed.\n"
            "Install it with:  pip install yui-agent[workshop]\n"
            "Then run:          playwright install chromium"
        ) from None


def _get_async_playwright():  # type: ignore[no-untyped-def]
    """Import and return ``async_playwright`` from Playwright.

    Separated from the guard so tests can patch this single function.
    """
    from playwright.async_api import async_playwright

    return async_playwright


def _get_pw_timeout_error() -> type:
    """Import and return Playwright's TimeoutError class."""
    from playwright.async_api import TimeoutError as PwTimeoutError

    return PwTimeoutError


# ---------------------------------------------------------------------------
# Internal extraction helpers
# ---------------------------------------------------------------------------


def _extract_code_blocks(page_content: str) -> list[str]:
    """Extract fenced code blocks from markdown-ish content."""
    blocks: list[str] = []
    in_block = False
    current: list[str] = []
    for line in page_content.splitlines():
        if line.strip().startswith("```"):
            if in_block:
                blocks.append("\n".join(current))
                current = []
                in_block = False
            else:
                in_block = True
        elif in_block:
            current.append(line)
    # Handle unclosed block gracefully
    if current:
        blocks.append("\n".join(current))
    return blocks


async def _extract_page_content(page: object) -> tuple[str, list[str], list[str]]:
    """Extract text content, code blocks, and image URLs from the current page.

    *page* is a Playwright ``Page`` object (untyped to avoid hard import).
    """
    # Main content area — Workshop Studio uses <main> or role="main"
    main_selector = "main, [role='main'], #main-content, .content-area, article"
    try:
        main_el = await page.query_selector(main_selector)  # type: ignore[union-attr]
    except Exception:
        main_el = None

    if main_el:
        text = await main_el.inner_text()  # type: ignore[union-attr]
    else:
        text = await page.inner_text("body")  # type: ignore[union-attr]

    # Code blocks: look for <pre> or <code> elements
    code_elements = await page.query_selector_all("pre code, pre")  # type: ignore[union-attr]
    code_blocks: list[str] = []
    for el in code_elements:
        code_text = await el.inner_text()
        if code_text.strip():
            code_blocks.append(code_text.strip())

    # If no pre/code found, fall back to markdown-style extraction
    if not code_blocks:
        code_blocks = _extract_code_blocks(text)

    # Images
    img_elements = await page.query_selector_all("main img, [role='main'] img, article img")  # type: ignore[union-attr]
    images: list[str] = []
    for img in img_elements:
        src = await img.get_attribute("src")
        if src:
            current_url = page.url  # type: ignore[union-attr]
            images.append(urljoin(current_url, src))

    return text.strip(), code_blocks, images


async def _collect_sidebar_links(page: object, base_url: str) -> list[dict]:
    """Discover all module/step links from the Workshop Studio sidebar.

    Returns a list of ``{"title": …, "url": …, "module_index": …, "step_index": …}``
    dicts, ordered by appearance.
    """
    # Workshop Studio sidebar typically has a nav with nested lists
    sidebar_selectors = [
        "nav a[href]",
        "[class*='sidebar'] a[href]",
        "[class*='navigation'] a[href]",
        "[class*='toc'] a[href]",
        "#sidebar a[href]",
    ]

    links: list[dict] = []
    seen_urls: set[str] = set()

    for selector in sidebar_selectors:
        elements = await page.query_selector_all(selector)  # type: ignore[union-attr]
        if elements:
            for el in elements:
                href = await el.get_attribute("href")
                title = (await el.inner_text()).strip()
                if not href or not title:
                    continue
                full_url = urljoin(base_url, href)
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)
                links.append({"title": title, "url": full_url})
            break  # Use the first selector that yields results

    # Assign module/step indices by order
    module_idx = 0
    step_idx = 0
    for i, link in enumerate(links):
        # Heuristic: major sections (few links, or different path segments) bump module
        if i > 0:
            prev_path = urlparse(links[i - 1]["url"]).path
            curr_path = urlparse(link["url"]).path
            prev_parts = [p for p in prev_path.split("/") if p]
            curr_parts = [p for p in curr_path.split("/") if p]
            if len(curr_parts) <= len(prev_parts) - 1:
                module_idx += 1
                step_idx = 0
            else:
                step_idx += 1
        link["module_index"] = module_idx
        link["step_index"] = step_idx

    return links


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def scrape_workshop(
    url: str,
    headed: bool = False,
    timeout_ms: int = DEFAULT_PAGE_TIMEOUT_MS,
) -> list[WorkshopPage]:
    """Scrape all pages from a Workshop Studio workshop.

    Parameters
    ----------
    url:
        The root Workshop Studio URL.
    headed:
        Launch the browser in headed mode (useful for debugging).
    timeout_ms:
        Page-load timeout in milliseconds.

    Returns
    -------
    list[WorkshopPage]
        Ordered list of scraped pages.

    Raises
    ------
    RuntimeError
        If Playwright is not installed.
    ValueError
        If *url* is empty or has an unsupported scheme.
    TimeoutError
        If a page load exceeds *timeout_ms*.
    """
    url = normalise_workshop_url(url)

    _require_playwright()

    async_playwright = _get_async_playwright()
    PwTimeoutError = _get_pw_timeout_error()
    pages: list[WorkshopPage] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not headed)
        try:
            context = await browser.new_context()
            page = await context.new_page()
            page.set_default_timeout(timeout_ms)

            # Navigate to root page
            try:
                await page.goto(url, wait_until="networkidle")
            except PwTimeoutError:
                raise TimeoutError(f"Timed out loading workshop root: {url}")
            except (OSError, ConnectionError) as exc:
                raise RuntimeError(f"Failed to load workshop: {exc}") from exc

            # Collect sidebar links
            sidebar_links = await _collect_sidebar_links(page, url)

            if not sidebar_links:
                # Single-page workshop — scrape the current page
                text, code_blocks, images = await _extract_page_content(page)
                title = await page.title()
                pages.append(
                    WorkshopPage(
                        title=title or "Workshop",
                        url=url,
                        content=text,
                        module_index=0,
                        step_index=0,
                        code_blocks=code_blocks,
                        images=images,
                    )
                )
            else:
                # Multi-page — visit each link
                for link_info in sidebar_links:
                    link_url = link_info["url"]
                    try:
                        await page.goto(link_url, wait_until="networkidle")
                    except PwTimeoutError:
                        logger.warning("Timeout loading %s — skipping", link_url)
                        continue
                    except (OSError, ConnectionError):
                        logger.warning(
                            "Error loading %s — skipping", link_url, exc_info=True
                        )
                        continue

                    text, code_blocks, images = await _extract_page_content(page)
                    pages.append(
                        WorkshopPage(
                            title=link_info["title"],
                            url=link_url,
                            content=text,
                            module_index=link_info["module_index"],
                            step_index=link_info["step_index"],
                            code_blocks=code_blocks,
                            images=images,
                        )
                    )
        finally:
            await browser.close()

    logger.info("Scraped %d pages from %s", len(pages), url)
    return pages
