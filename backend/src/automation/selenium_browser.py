"""undetected-chromedriver wrapper implementing the Browser Protocol.

Lives behind the `[engine]` extras — heavy deps (selenium, undetected-
chromedriver) are imported lazily so the rest of the backend boots without
them.

See ADR 0004 for the access strategies (CDP attach is the default).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.automation.browser import Browser, BrowserError

logger = logging.getLogger(__name__)


class SeleniumBrowser(Browser):
    def __init__(self, driver: Any) -> None:
        # `driver` is selenium.webdriver.Chrome (typically undetected variant).
        self._driver = driver

    @classmethod
    async def attach_cdp(
        cls, *, port: int, host: str = "127.0.0.1"
    ) -> SeleniumBrowser:
        """Connect to an already-running Chrome started with
        `--remote-debugging-port=<port>`.
        """
        driver = await asyncio.to_thread(_build_attached_driver, host, port)
        return cls(driver)

    @classmethod
    async def launch_new(cls) -> SeleniumBrowser:
        """Launch a fresh undetected-chromedriver Chromium instance.

        Used for the `manual_login` access strategy.
        """
        driver = await asyncio.to_thread(_build_fresh_driver)
        return cls(driver)

    async def current_url(self) -> str:
        return await asyncio.to_thread(lambda: self._driver.current_url)

    async def page_source(self) -> str:
        return await asyncio.to_thread(lambda: self._driver.page_source)

    async def navigate(self, url: str) -> None:
        await asyncio.to_thread(self._driver.get, url)

    async def click_css(self, selector: str) -> None:
        try:
            await asyncio.to_thread(self._sync_click_css, selector)
        except Exception as exc:  # noqa: BLE001
            raise BrowserError(f"click {selector!r} failed: {exc}") from exc

    async def find_text(self, selector: str) -> str:
        try:
            return await asyncio.to_thread(self._sync_find_text, selector)
        except Exception as exc:  # noqa: BLE001
            raise BrowserError(f"find_text {selector!r} failed: {exc}") from exc

    async def scroll_into_view(self, selector: str) -> None:
        script = (
            "const el=document.querySelector(arguments[0]);"
            "if(el)el.scrollIntoView({behavior:'smooth',block:'center'});"
        )
        try:
            await asyncio.to_thread(self._driver.execute_script, script, selector)
        except Exception as exc:  # noqa: BLE001
            raise BrowserError(f"scroll {selector!r} failed: {exc}") from exc

    async def quit(self) -> None:
        try:
            await asyncio.to_thread(self._driver.quit)
        except Exception:  # noqa: BLE001
            logger.debug("driver.quit raised; ignoring", exc_info=True)

    def _sync_click_css(self, selector: str) -> None:
        from selenium.webdriver.common.by import By

        elements = self._driver.find_elements(By.CSS_SELECTOR, selector)
        if not elements:
            raise BrowserError(f"no element matches {selector!r}")
        elements[0].click()

    def _sync_find_text(self, selector: str) -> str:
        from selenium.webdriver.common.by import By

        elements = self._driver.find_elements(By.CSS_SELECTOR, selector)
        if not elements:
            raise BrowserError(f"no element matches {selector!r}")
        return str(elements[0].text or "")


def _build_attached_driver(host: str, port: int) -> Any:
    import undetected_chromedriver as uc

    opts = uc.ChromeOptions()
    opts.add_experimental_option("debuggerAddress", f"{host}:{port}")
    # When attaching, undetected-chromedriver should not patch the binary —
    # we are joining a real Chrome already running.
    return uc.Chrome(options=opts, use_subprocess=False)


def _build_fresh_driver() -> Any:
    import undetected_chromedriver as uc

    opts = uc.ChromeOptions()
    return uc.Chrome(options=opts, use_subprocess=False)
