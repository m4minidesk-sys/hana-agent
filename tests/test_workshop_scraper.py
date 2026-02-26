"""Tests for yui.workshop.scraper (AC-70)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yui.workshop.models import WorkshopPage
from yui.workshop.scraper import (
    _extract_code_blocks,
    normalise_workshop_url,
    scrape_workshop,
    validate_workshop_url,
)


# =========================================================================
# URL helpers
# =========================================================================


class TestNormaliseWorkshopUrl:
    """normalise_workshop_url tests."""

    def test_strips_trailing_slash(self) -> None:
        assert normalise_workshop_url("https://catalog.workshops.aws/foo/") == (
            "https://catalog.workshops.aws/foo"
        )

    def test_strips_whitespace(self) -> None:
        assert normalise_workshop_url("  https://catalog.workshops.aws/foo  ") == (
            "https://catalog.workshops.aws/foo"
        )

    def test_upgrades_http_to_https(self) -> None:
        assert normalise_workshop_url("http://catalog.workshops.aws/foo").startswith("https://")

    def test_empty_url_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            normalise_workshop_url("")

    def test_unsupported_scheme_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported URL scheme"):
            normalise_workshop_url("ftp://example.com")

    def test_preserves_path(self) -> None:
        url = "https://catalog.workshops.aws/a/b/c"
        assert normalise_workshop_url(url) == url


class TestValidateWorkshopUrl:
    """validate_workshop_url tests."""

    def test_valid_catalog_url(self) -> None:
        url = "https://catalog.workshops.aws/myworkshop"
        assert validate_workshop_url(url) == url

    def test_valid_custom_domain(self) -> None:
        url = "https://my-ws.workshop.aws/en"
        assert validate_workshop_url(url) == url

    def test_valid_us_east_1_catalog(self) -> None:
        url = "https://catalog.us-east-1.workshops.aws/myworkshop"
        assert validate_workshop_url(url) == url

    def test_invalid_domain_raises(self) -> None:
        with pytest.raises(ValueError, match="does not look like"):
            validate_workshop_url("https://example.com/foo")

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            validate_workshop_url("")


# =========================================================================
# Code-block extraction
# =========================================================================


class TestExtractCodeBlocks:
    """_extract_code_blocks tests."""

    def test_single_fenced_block(self) -> None:
        text = "hello\n```\naws s3 ls\n```\nbye"
        assert _extract_code_blocks(text) == ["aws s3 ls"]

    def test_multiple_blocks(self) -> None:
        text = "```\nfoo\n```\ntext\n```\nbar\n```"
        assert _extract_code_blocks(text) == ["foo", "bar"]

    def test_language_annotation(self) -> None:
        text = "```bash\necho hi\n```"
        assert _extract_code_blocks(text) == ["echo hi"]

    def test_no_blocks(self) -> None:
        assert _extract_code_blocks("just plain text") == []

    def test_unclosed_block(self) -> None:
        text = "```\naws s3 ls"
        blocks = _extract_code_blocks(text)
        assert len(blocks) == 1
        assert "aws s3 ls" in blocks[0]


# =========================================================================
# Playwright import guard
# =========================================================================


class TestPlaywrightGuard:
    """Verify clear error when Playwright is missing."""

    def test_missing_playwright_raises_runtime_error(self) -> None:
        import builtins

        real_import = builtins.__import__

        def _no_pw(name: str, *args, **kwargs):  # type: ignore[no-untyped-def]
            if "playwright" in name:
                raise ImportError("no playwright")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_no_pw):
            from yui.workshop.scraper import _require_playwright

            with pytest.raises(RuntimeError, match="pip install yui-agent"):
                _require_playwright()


# =========================================================================
# Mock Playwright helpers
# =========================================================================


def _make_mock_page(
    title: str = "Workshop",
    body_text: str = "Welcome to the workshop",
    code_elements: list[str] | None = None,
    img_srcs: list[str] | None = None,
    sidebar_links: list[dict] | None = None,
    url: str = "https://catalog.workshops.aws/myworkshop",
) -> AsyncMock:
    """Build a mock Playwright Page object."""
    page = AsyncMock()
    page.url = url

    # set_default_timeout is synchronous
    page.set_default_timeout = MagicMock()

    # title()
    page.title = AsyncMock(return_value=title)

    # query_selector for main element
    main_el = AsyncMock()
    main_el.inner_text = AsyncMock(return_value=body_text)
    page.query_selector = AsyncMock(return_value=main_el)

    # inner_text fallback
    page.inner_text = AsyncMock(return_value=body_text)

    # code elements
    if code_elements is None:
        code_elements = []
    mock_code_els = []
    for code in code_elements:
        el = AsyncMock()
        el.inner_text = AsyncMock(return_value=code)
        mock_code_els.append(el)

    # img elements
    if img_srcs is None:
        img_srcs = []
    mock_img_els = []
    for src in img_srcs:
        el = AsyncMock()
        el.get_attribute = AsyncMock(return_value=src)
        mock_img_els.append(el)

    # sidebar link elements
    if sidebar_links is None:
        sidebar_links = []
    mock_sidebar_els = []
    for link in sidebar_links:
        el = AsyncMock()
        el.get_attribute = AsyncMock(return_value=link["href"])
        el.inner_text = AsyncMock(return_value=link["title"])
        mock_sidebar_els.append(el)

    async def _query_selector_all(selector: str) -> list:
        if "pre" in selector or "code" in selector:
            return mock_code_els
        if "img" in selector:
            return mock_img_els
        if "a[href]" in selector:
            return mock_sidebar_els
        return []

    page.query_selector_all = _query_selector_all
    return page


class _FakePwTimeoutError(Exception):
    """Stand-in for playwright.async_api.TimeoutError."""


def _build_pw_mocks(
    mock_page: AsyncMock,
    capture: dict | None = None,
) -> tuple:
    """Build mock objects for Playwright and return (patches_list, browser_mock).

    *capture*: if provided, ``chromium.launch`` kwargs are stored here.
    """
    browser = AsyncMock()
    browser.close = AsyncMock()
    context = AsyncMock()
    context.new_page = AsyncMock(return_value=mock_page)
    browser.new_context = AsyncMock(return_value=context)

    pw_instance = AsyncMock()

    if capture is not None:
        async def _launch(**kw):  # type: ignore[no-untyped-def]
            capture.update(kw)
            return browser
        pw_instance.chromium.launch = _launch
    else:
        pw_instance.chromium.launch = AsyncMock(return_value=browser)

    class _FakeAsyncPW:
        async def __aenter__(self):  # type: ignore[no-untyped-def]
            return pw_instance

        async def __aexit__(self, *args):  # type: ignore[no-untyped-def]
            pass

    fake_async_pw_fn = MagicMock(return_value=_FakeAsyncPW())

    patches = [
        patch("yui.workshop.scraper._require_playwright"),
        patch("yui.workshop.scraper._get_async_playwright", return_value=fake_async_pw_fn),
        patch("yui.workshop.scraper._get_pw_timeout_error", return_value=_FakePwTimeoutError),
    ]
    return patches, browser


async def _run_scrape(
    mock_page: AsyncMock,
    url: str = "https://catalog.workshops.aws/ws",
    headed: bool = False,
    capture: dict | None = None,
) -> list[WorkshopPage]:
    """Run scrape_workshop with a fully mocked Playwright."""
    patches, _ = _build_pw_mocks(mock_page, capture=capture)
    with patches[0], patches[1], patches[2]:
        return await scrape_workshop(url, headed=headed)


# =========================================================================
# scrape_workshop — mocked Playwright
# =========================================================================


class TestScrapeWorkshop:
    """Integration-level tests with mocked Playwright."""

    async def test_single_page_workshop(self) -> None:
        mock_page = _make_mock_page(
            title="My Workshop",
            body_text="Step 1: do something",
        )
        pages = await _run_scrape(mock_page)
        assert len(pages) == 1
        assert pages[0].title == "My Workshop"
        assert "Step 1" in pages[0].content

    async def test_multi_page_workshop(self) -> None:
        sidebar = [
            {"href": "/page1", "title": "Introduction"},
            {"href": "/page2", "title": "Setup"},
        ]
        mock_page = _make_mock_page(
            title="Workshop",
            body_text="Page content",
            sidebar_links=sidebar,
            url="https://catalog.workshops.aws/ws",
        )
        pages = await _run_scrape(mock_page)
        assert len(pages) == 2
        assert pages[0].title == "Introduction"
        assert pages[1].title == "Setup"

    async def test_headed_mode_flag(self) -> None:
        mock_page = _make_mock_page()
        capture: dict = {}
        await _run_scrape(mock_page, headed=True, capture=capture)
        assert capture.get("headless") is False

    async def test_code_blocks_extracted(self) -> None:
        mock_page = _make_mock_page(
            body_text="Run the command",
            code_elements=["aws s3 ls", "echo hello"],
        )
        pages = await _run_scrape(mock_page)
        assert len(pages) == 1
        assert "aws s3 ls" in pages[0].code_blocks
        assert "echo hello" in pages[0].code_blocks

    async def test_images_extracted(self) -> None:
        mock_page = _make_mock_page(
            body_text="See the diagram",
            img_srcs=["/img/arch.png", "https://cdn.example.com/pic.jpg"],
        )
        pages = await _run_scrape(mock_page)
        assert len(pages) == 1
        assert len(pages[0].images) == 2

    async def test_empty_url_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            await scrape_workshop("")

    async def test_timeout_on_root_raises(self) -> None:
        """When the root page times out, TimeoutError is raised."""
        mock_page = _make_mock_page()
        mock_page.goto = AsyncMock(side_effect=_FakePwTimeoutError("timed out"))

        patches, browser = _build_pw_mocks(mock_page)
        with patches[0], patches[1], patches[2]:
            with pytest.raises(TimeoutError, match="Timed out"):
                await scrape_workshop("https://catalog.workshops.aws/ws")

    async def test_module_step_indices(self) -> None:
        sidebar = [
            {"href": "/mod1/step1", "title": "Module 1 Step 1"},
            {"href": "/mod1/step2", "title": "Module 1 Step 2"},
        ]
        mock_page = _make_mock_page(
            body_text="Content",
            sidebar_links=sidebar,
            url="https://catalog.workshops.aws/ws",
        )
        pages = await _run_scrape(mock_page)
        assert pages[0].module_index == 0
        assert pages[0].step_index == 0
        assert pages[1].module_index == 0
        assert pages[1].step_index == 1

    async def test_page_content_is_stripped(self) -> None:
        mock_page = _make_mock_page(body_text="  hello world  \n  ")
        pages = await _run_scrape(mock_page)
        assert pages[0].content == pages[0].content.strip()

    async def test_returns_workshop_page_type(self) -> None:
        mock_page = _make_mock_page()
        pages = await _run_scrape(mock_page)
        assert all(isinstance(p, WorkshopPage) for p in pages)

    async def test_headless_by_default(self) -> None:
        mock_page = _make_mock_page()
        capture: dict = {}
        await _run_scrape(mock_page, headed=False, capture=capture)
        assert capture.get("headless") is True

    async def test_page_url_stored(self) -> None:
        mock_page = _make_mock_page(url="https://catalog.workshops.aws/myws")
        pages = await _run_scrape(mock_page, url="https://catalog.workshops.aws/myws")
        assert pages[0].url is not None

    async def test_empty_sidebar_returns_single_page(self) -> None:
        """When no sidebar links are found, current page is scraped."""
        mock_page = _make_mock_page(
            title="Solo Page",
            body_text="Only page",
            sidebar_links=[],
        )
        pages = await _run_scrape(mock_page)
        assert len(pages) == 1
        assert pages[0].title == "Solo Page"

    async def test_generic_error_on_root_raises_runtime(self) -> None:
        """Network errors on root navigation become RuntimeError."""
        mock_page = _make_mock_page()
        mock_page.goto = AsyncMock(side_effect=ConnectionError("DNS failed"))

        patches, browser = _build_pw_mocks(mock_page)
        with patches[0], patches[1], patches[2]:
            with pytest.raises(RuntimeError, match="Failed to load"):
                await scrape_workshop("https://catalog.workshops.aws/ws")

    async def test_skips_timed_out_subpages(self) -> None:
        """Sub-page timeouts are logged and skipped, not raised."""
        sidebar = [
            {"href": "/ok", "title": "Good Page"},
            {"href": "/slow", "title": "Slow Page"},
        ]
        mock_page = _make_mock_page(
            body_text="Content",
            sidebar_links=sidebar,
            url="https://catalog.workshops.aws/ws",
        )

        call_count = 0

        async def _goto(url: str, **kw):  # type: ignore[no-untyped-def]
            nonlocal call_count
            call_count += 1
            # First call is root (OK), second is /ok (OK), third is /slow (timeout)
            if call_count == 3:
                raise _FakePwTimeoutError("timed out")

        mock_page.goto = _goto

        patches, _ = _build_pw_mocks(mock_page)
        with patches[0], patches[1], patches[2]:
            pages = await scrape_workshop("https://catalog.workshops.aws/ws")

        # Only the non-timed-out page should be returned
        assert len(pages) == 1
        assert pages[0].title == "Good Page"
