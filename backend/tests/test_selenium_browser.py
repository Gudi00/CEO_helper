"""Tests for SeleniumBrowser using a fake WebDriver.

We never touch a real Chrome — the WebDriver surface used by SeleniumBrowser
(`current_url`, `page_source`, `get`, `find_elements`, `execute_script`,
`quit`) is small enough to fake with plain Python objects.

The two `@classmethod` factories (`attach_cdp`, `launch_new`) import
`undetected_chromedriver` lazily inside the module-private helpers; we
monkey-patch those helpers to verify the wrapper plumbing without
spawning Chrome.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.automation.browser import BrowserError
from src.automation.selenium_browser import SeleniumBrowser


class _FakeElement:
    """Minimal stand-in for selenium.webdriver.remote.webelement.WebElement."""

    def __init__(
        self, *, text: str = "", click_raises: Exception | None = None
    ) -> None:
        self.text = text
        self.click_calls = 0
        self._click_raises = click_raises

    def click(self) -> None:
        self.click_calls += 1
        if self._click_raises is not None:
            raise self._click_raises


class _FakeDriver:
    """Stand-in for selenium.webdriver.Chrome."""

    def __init__(
        self,
        *,
        elements: dict[str, list[_FakeElement]] | None = None,
        current_url: str = "https://example.com",
        page_source: str = "<html></html>",
        quit_raises: Exception | None = None,
    ) -> None:
        self._elements = elements or {}
        self.current_url = current_url
        self.page_source = page_source
        self._quit_raises = quit_raises
        self.quit_calls = 0
        self.get_calls: list[str] = []
        self.scripts: list[tuple[str, tuple[Any, ...]]] = []
        self.find_calls: list[tuple[Any, str]] = []

    def get(self, url: str) -> None:
        self.get_calls.append(url)

    def find_elements(self, by: Any, value: str) -> list[_FakeElement]:
        self.find_calls.append((by, value))
        return list(self._elements.get(value, []))

    def execute_script(self, script: str, *args: Any) -> Any:
        self.scripts.append((script, args))
        return None

    def quit(self) -> None:
        self.quit_calls += 1
        if self._quit_raises is not None:
            raise self._quit_raises


@pytest.mark.asyncio
async def test_current_url_proxies_to_driver():
    driver = _FakeDriver(current_url="https://lms.bsuir.by/mod/quiz")
    browser = SeleniumBrowser(driver)
    assert await browser.current_url() == "https://lms.bsuir.by/mod/quiz"


@pytest.mark.asyncio
async def test_page_source_proxies_to_driver():
    driver = _FakeDriver(page_source="<div class='que'></div>")
    assert (await SeleniumBrowser(driver).page_source()).startswith("<div")


@pytest.mark.asyncio
async def test_navigate_calls_driver_get():
    driver = _FakeDriver()
    await SeleniumBrowser(driver).navigate("https://example.com/quiz")
    assert driver.get_calls == ["https://example.com/quiz"]


@pytest.mark.asyncio
async def test_click_css_clicks_first_matching_element():
    target = _FakeElement()
    other = _FakeElement()
    driver = _FakeDriver(elements={"input.start": [target, other]})

    await SeleniumBrowser(driver).click_css("input.start")

    assert target.click_calls == 1
    assert other.click_calls == 0
    # The wrapper should pass a `By` enum value (not a raw string).
    from selenium.webdriver.common.by import By
    assert driver.find_calls[0][0] == By.CSS_SELECTOR


@pytest.mark.asyncio
async def test_click_css_raises_browser_error_when_no_match():
    driver = _FakeDriver(elements={})
    with pytest.raises(BrowserError) as ei:
        await SeleniumBrowser(driver).click_css("input.missing")
    assert "input.missing" in str(ei.value)


@pytest.mark.asyncio
async def test_click_css_wraps_underlying_click_failure():
    elem = _FakeElement(click_raises=RuntimeError("element stale"))
    driver = _FakeDriver(elements={"button": [elem]})

    with pytest.raises(BrowserError) as ei:
        await SeleniumBrowser(driver).click_css("button")
    assert "button" in str(ei.value)
    assert isinstance(ei.value.__cause__, RuntimeError)


@pytest.mark.asyncio
async def test_find_text_returns_first_element_text():
    elem = _FakeElement(text="Оценка 14,00/20,00")
    driver = _FakeDriver(elements={".score": [elem]})

    text = await SeleniumBrowser(driver).find_text(".score")
    assert text == "Оценка 14,00/20,00"


@pytest.mark.asyncio
async def test_find_text_handles_none_text_attribute():
    # selenium can return None for `.text` if the element is hidden;
    # the wrapper should still produce a str, never None.
    elem = _FakeElement(text="")
    elem.text = None  # type: ignore[assignment]
    driver = _FakeDriver(elements={".x": [elem]})

    text = await SeleniumBrowser(driver).find_text(".x")
    assert text == ""


@pytest.mark.asyncio
async def test_find_text_raises_browser_error_when_no_match():
    with pytest.raises(BrowserError):
        await SeleniumBrowser(_FakeDriver()).find_text(".missing")


@pytest.mark.asyncio
async def test_scroll_into_view_runs_js_with_selector_arg():
    driver = _FakeDriver()
    await SeleniumBrowser(driver).scroll_into_view("div#question-1")

    assert len(driver.scripts) == 1
    script, args = driver.scripts[0]
    assert "scrollIntoView" in script
    assert "behavior:'smooth'" in script
    assert args == ("div#question-1",)


@pytest.mark.asyncio
async def test_scroll_into_view_wraps_script_failures():
    class BoomDriver(_FakeDriver):
        def execute_script(self, script: str, *args: Any) -> Any:
            raise RuntimeError("JS error")

    with pytest.raises(BrowserError):
        await SeleniumBrowser(BoomDriver()).scroll_into_view(".x")


@pytest.mark.asyncio
async def test_quit_calls_driver_quit():
    driver = _FakeDriver()
    await SeleniumBrowser(driver).quit()
    assert driver.quit_calls == 1


@pytest.mark.asyncio
async def test_quit_swallows_driver_exceptions():
    """We never want shutdown noise to bubble — engine.run uses this in
    `finally`, so a raise here would mask the real error.
    """
    driver = _FakeDriver(quit_raises=RuntimeError("already closed"))
    # Should not raise.
    await SeleniumBrowser(driver).quit()
    assert driver.quit_calls == 1


# ---- Factory tests: patch the module-private builder funcs --------------


@pytest.mark.asyncio
async def test_attach_cdp_invokes_builder_with_host_port(monkeypatch):
    called: dict[str, Any] = {}
    sentinel_driver = _FakeDriver(current_url="https://lms")

    def fake_builder(host: str, port: int):
        called["host"] = host
        called["port"] = port
        return sentinel_driver

    monkeypatch.setattr(
        "src.automation.selenium_browser._build_attached_driver", fake_builder
    )

    browser = await SeleniumBrowser.attach_cdp(port=9222)

    assert called == {"host": "127.0.0.1", "port": 9222}
    assert isinstance(browser, SeleniumBrowser)
    assert await browser.current_url() == "https://lms"


@pytest.mark.asyncio
async def test_attach_cdp_accepts_custom_host(monkeypatch):
    captured: list[tuple[str, int]] = []

    def fake_builder(host: str, port: int):
        captured.append((host, port))
        return _FakeDriver()

    monkeypatch.setattr(
        "src.automation.selenium_browser._build_attached_driver", fake_builder
    )

    await SeleniumBrowser.attach_cdp(host="10.0.0.5", port=9333)
    assert captured == [("10.0.0.5", 9333)]


@pytest.mark.asyncio
async def test_launch_new_invokes_fresh_builder(monkeypatch):
    called = 0
    sentinel_driver = _FakeDriver()

    def fake_builder():
        nonlocal called
        called += 1
        return sentinel_driver

    monkeypatch.setattr(
        "src.automation.selenium_browser._build_fresh_driver", fake_builder
    )

    browser = await SeleniumBrowser.launch_new()
    assert called == 1
    assert isinstance(browser, SeleniumBrowser)


@pytest.mark.asyncio
async def test_builder_failures_propagate(monkeypatch):
    def boom(host: str, port: int):
        raise RuntimeError("chrome not listening on port")

    monkeypatch.setattr(
        "src.automation.selenium_browser._build_attached_driver", boom
    )

    with pytest.raises(RuntimeError, match="chrome not listening"):
        await SeleniumBrowser.attach_cdp(port=9222)


# ---- Module-private helpers that import undetected_chromedriver ---------

class _FakeChromeOptions:
    def __init__(self) -> None:
        self.experimental: dict[str, Any] = {}

    def add_experimental_option(self, key: str, value: Any) -> None:
        self.experimental[key] = value


def _install_fake_uc(monkeypatch, *, chrome_calls: list[dict[str, Any]]):
    """Inject a stub `undetected_chromedriver` module so the lazy imports
    inside `_build_attached_driver` / `_build_fresh_driver` resolve.
    """
    import sys
    import types

    fake_uc = types.SimpleNamespace(
        ChromeOptions=_FakeChromeOptions,
        Chrome=lambda **kwargs: chrome_calls.append(kwargs) or "driver_sentinel",
    )
    monkeypatch.setitem(sys.modules, "undetected_chromedriver", fake_uc)


def test_build_attached_driver_sets_debugger_address(monkeypatch):
    from src.automation import selenium_browser as sb

    chrome_calls: list[dict[str, Any]] = []
    _install_fake_uc(monkeypatch, chrome_calls=chrome_calls)

    driver = sb._build_attached_driver("127.0.0.1", 9222)

    assert driver == "driver_sentinel"
    assert len(chrome_calls) == 1
    opts = chrome_calls[0]["options"]
    assert opts.experimental["debuggerAddress"] == "127.0.0.1:9222"
    assert chrome_calls[0]["use_subprocess"] is False


def test_build_fresh_driver_passes_blank_options(monkeypatch):
    from src.automation import selenium_browser as sb

    chrome_calls: list[dict[str, Any]] = []
    _install_fake_uc(monkeypatch, chrome_calls=chrome_calls)

    driver = sb._build_fresh_driver()

    assert driver == "driver_sentinel"
    assert len(chrome_calls) == 1
    opts = chrome_calls[0]["options"]
    # Fresh driver: no experimental options set.
    assert opts.experimental == {}
    assert chrome_calls[0]["use_subprocess"] is False
