import asyncio
import os
from typing import Dict, Any, List, Optional
from playwright.async_api import async_playwright, Page, Browser, Playwright, Locator
from schemas import TestStep
from utils.logger import get_logger
import config

logger = get_logger("browser_engine")

class PlaywrightBrowserEngine:
    def __init__(self):
        self.headless = config.HEADLESS
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[Any] = None
        self.page: Optional[Page] = None
        self.initial_url: Optional[str] = None
        self.console_logs: List[str] = []
        self.network_errors: List[str] = []

    async def initialize(self):
        logger.info("Initializing Playwright Browser Engine...")
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=["--disable-dev-shm-usage"]
        )
        self.context = await self.browser.new_context(
            viewport={"width": 1280, "height": 720},
            ignore_https_errors=True
        )
        
        # Start Playwright Tracing
        logger.info("Starting browser trace recorder...")
        await self.context.tracing.start(
            screenshots=True,
            snapshots=True,
            sources=True
        )
        self.page = await self.context.new_page()

        # Wire up interceptors
        self.page.on("console", self._handle_console)
        self.page.on("response", self._handle_response)
        
        logger.info("Browser initialized successfully.")

    def _handle_console(self, msg):
        if msg.type in ["error", "warning"]:
            location = msg.location
            if isinstance(location, dict):
                url = location.get("url", "unknown")
                line = location.get("lineNumber", 0)
            else:
                url = str(location) if location else "unknown"
                line = 0
            log_str = f"[{msg.type}] {msg.text} ({url}:{line})"
            self.console_logs.append(log_str)
            logger.warning(f"Browser Console Intercepted: {log_str}")

    def _handle_response(self, response):
        if response.status >= 400:
            error_str = f"HTTP {response.status} {response.method} {response.url}"
            self.network_errors.append(error_str)
            logger.error(f"Browser Network Error Intercepted: {error_str}")

    async def auto_suppress_popups(self):
        """Silently detects and dismisses common overlays/cookie banners."""
        common_selectors = [
            "text='Accepter tout'", "text='Tout accepter'", "text='Autoriser tous les cookies'",
            "text='I Accept'", "text='Accept All'", "#onetrust-accept-btn-handler",
            "button[id*='cookie']", "button[class*='cookie']", "[aria-label*='cookie']"
        ]
        for selector in common_selectors:
            try:
                locator = self.page.locator(selector).first
                if await locator.is_visible(timeout=300):
                    await locator.click(force=True, timeout=1000)
                    await self.page.wait_for_timeout(300)
                    break
            except Exception:
                continue

    async def navigate(self, url: str):
        await self.auto_suppress_popups()
        logger.info(f"Navigating browser to: {url}")
        if not self.initial_url:
            self.initial_url = url
        await self.page.goto(url, wait_until="load", timeout=config.BROWSER_TIMEOUT)

    async def get_accessibility_tree(self) -> str:
        """
        Extracts the page ARIA accessibility snapshot for LLM context.
        Uses the modern Playwright aria_snapshot() API; falls back to the full
        DOM HTML if the ARIA snapshot is unavailable.
        """
        if not self.page:
            return ""
        await self.auto_suppress_popups()
        try:
            # Modern Playwright ARIA snapshot (replaces deprecated page.accessibility)
            return await self.page.locator("body").aria_snapshot()
        except Exception as e:
            logger.error(f"ARIA snapshot failed, falling back to page.content(): {e}")
            try:
                return await self.page.content()
            except Exception as inner_e:
                logger.error(f"page.content() fallback also failed: {inner_e}")
                return ""


    async def resolve_locator(self, selector: str) -> Locator:
        """
        Resolves a selector string into a Playwright Locator.
        Supports both standard CSS/XPath selectors and evaluated Python Playwright expressions.
        """
        if not selector:
            raise ValueError("Selector cannot be empty")
        
        # Determine if selector is a Playwright Python evaluator expression
        # E.g. "page.get_by_role('button', name='Submit')"
        if selector.startswith("page.") or "get_by_" in selector:
            logger.debug(f"Evaluating Python locator expression: {selector}")
            try:
                # Evaluate expression with self.page in context
                locator = eval(selector, {"page": self.page})
                if not isinstance(locator, Locator):
                    raise ValueError("Evaluated expression did not return a Playwright Locator.")
                return locator
            except Exception as e:
                raise ValueError(f"Failed to evaluate locator expression '{selector}': {e}")
        else:
            logger.debug(f"Resolving standard locator selector: {selector}")
            return self.page.locator(selector)

    async def get_element(self, selector: str) -> Locator:
        """Backward-compatible alias for locator resolution."""
        return await self.resolve_locator(selector)

    async def _force_click_with_label_fallback(self, locator: Locator, selector: Optional[str] = None) -> None:
        """Try a forced click on the locator, then fall back to a related label."""
        try:
            await locator.click(force=True, timeout=3000)
            return
        except Exception:
            if selector and self.page:
                try:
                    await locator.locator("xpath=ancestor::label[1]").click(force=True, timeout=3000)
                    return
                except Exception:
                    pass

            raise

    async def execute_action(self, step: TestStep) -> bool:
        """
        Executes a TestStep using the browser engine.
        Returns True on success, False if an error occurred.
        """
        await self.auto_suppress_popups()
        logger.info(f"Executing step {step.step_id}: {step.description} (Action: {step.action_type})")
        try:
            action = step.action_type.value.lower()
            
            if action == "navigate":
                target_url = step.value or step.selector
                if not target_url or not target_url.startswith("http"):
                    target_url = self.initial_url
                if not target_url:
                    raise ValueError("Navigation action requires a URL value.")
                await self.page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
            
            elif action == "click":
                locator = await self.resolve_locator(step.selector)
                try:
                    await locator.click(timeout=3000)
                except Exception:
                    await self._force_click_with_label_fallback(locator, step.selector)
                
            elif action == "fill":
                if not step.value:
                    raise ValueError("Fill action requires a non-empty string value.")
                locator = await self.get_element(step.selector)
                # 1. Wait for element to be visible before interacting
                await locator.wait_for(state="visible", timeout=5000)
                # 2. Focus the field and clear any pre-existing content so React/Vue/Angular
                #    synthetic input events fire correctly on a fresh value
                await locator.click()
                await locator.fill("")
                # 3. Simulate human keystroke-by-keystroke typing (delay=30 ms) so JS
                #    onChange/oninput handlers receive individual key events
                await locator.type(step.value, delay=30)
                
            elif action == "select":
                if step.value is None:
                    raise ValueError("Select action requires an option value.")
                locator = await self.get_element(step.selector)
                await locator.select_option(step.value, timeout=config.DEFAULT_WAIT_TIME)
                
            elif action == "check":
                locator = await self.resolve_locator(step.selector)
                try:
                    await locator.check(timeout=3000)
                except Exception:
                    try:
                        await locator.check(force=True, timeout=3000)
                    except Exception:
                        await self._force_click_with_label_fallback(locator, step.selector)
                
            elif action == "wait_for_selector":
                locator = await self.get_element(step.selector)
                await locator.wait_for(state="visible", timeout=config.DEFAULT_WAIT_TIME)
                
            elif action == "assert_text":
                if not step.value:
                    raise ValueError("Assert text action requires an assertion value.")
                
                # Check visible text first
                body = self.page.locator("body")
                body_text = await body.inner_text()
                if step.value not in body_text:
                    # Fallback to general page source content search
                    content = await self.page.content()
                    assert step.value in content, f"Expected text '{step.value}' not found in page body or DOM source."
            
            else:
                raise ValueError(f"Unsupported action type: {step.action_type}")
            
            # Allow DOM states to settle and network calls to complete
            await self.page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(0.5)
            logger.info(f"Step {step.step_id} completed successfully.")
            return True
            
        except Exception as e:
            step.error_message = str(e)
            logger.error(f"Step {step.step_id} execution failed: {e}")
            return False

    async def stop(self, trace_path: str = "trace.zip"):
        logger.info("Stopping Browser Engine...")
        try:
            if self.context:
                logger.info(f"Saving Playwright trace file to: {trace_path}")
                await self.context.tracing.stop(path=trace_path)
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            logger.info("Browser Engine stopped successfully.")
        except Exception as e:
            logger.error(f"Error during Browser Engine teardown: {e}")
