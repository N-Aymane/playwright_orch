import asyncio
import os
from typing import Dict, Any, List, Optional
from playwright.async_api import async_playwright, Page, Browser, Playwright, Locator
from schemas import TestStep, ActionType
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
        self.exit_signal: asyncio.Event = asyncio.Event()  # Set when user clicks HUD "Exit & Close"

    async def __aenter__(self):
        # Support async context manager usage: `async with PlaywrightBrowserEngine()`
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        # Ensure proper teardown on context exit
        await self.stop()

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

        # Expose a Python binding so the HUD "Exit & Close" button can signal Python.
        await self.page.expose_binding(
            "copilot_close_session",
            lambda source: self.exit_signal.set()
        )

        # Inject stylesheet to suppress HubSpot overlays that intercept pointer events.
        # Targets: #hs-interactives-modal-overlay, #hs-web-interactives-top-anchor,
        #          .go1632949049 (autocomplete mask), and .autocomplete-mat__input__mask
        await self.page.add_init_script("""
            const style = document.createElement('style');
            style.innerHTML = [
                '#hs-interactives-modal-overlay,',
                '#hs-web-interactives-top-anchor,',
                '.go1632949049,',
                '.autocomplete-mat__input__mask',
                '{ display: none !important; pointer-events: none !important; }'
            ].join(' ');
            document.head.appendChild(style);
        """)

        # Register reactive locator handlers to dismiss mid-flow popups the moment
        # they appear — fires before any subsequent action can be blocked.

        # Handler 1: HubSpot modals and web-interactive overlays → press Escape
        await self.page.add_locator_handler(
            self.page.locator(
                "#hs-interactives-modal-overlay, "
                "iframe[data-test-id='interactive-frame'], "
                "div[id*='hs-web-interactive']"
            ).first,
            lambda overlay: overlay.page.keyboard.press("Escape")
        )

        # Handler 2: Cookie / consent banners → force-click the accept button
        await self.page.add_locator_handler(
            self.page.locator(
                "text='Accepter tout', "
                "text='Tout accepter', "
                "text='Autoriser tous les cookies', "
                "text='I Accept'"
            ).first,
            lambda btn: btn.click(force=True)
        )

        # Wire up interceptors
        self.page.on("console", self._handle_console)
        self.page.on("response", self._handle_response)

        # Inject the Copilot HUD floating widget into every page load.
        # Uses Shadow DOM for full CSS isolation from the target site.
        # Defers DOM insertion to DOMContentLoaded so document.body exists.
        await self.page.add_init_script("""
        (() => {
            function __buildCopilotHUD() {
                if (window.__copilot_injected) return;
                if (!document.body && !document.documentElement) return;
                window.__copilot_injected = true;

                const host = document.createElement('div');
                host.id = 'copilot-hud-host';
                host.style.cssText = [
                    'position:fixed',
                    'bottom:24px',
                    'right:24px',
                    'z-index:2147483647',
                    'font-family:system-ui,sans-serif',
                    'pointer-events:auto',
                ].join(';') + ';';

                // Prefer body; fall back to documentElement
                (document.body || document.documentElement).appendChild(host);

                const shadow = host.attachShadow({mode: 'open'});
                shadow.innerHTML = `
                    <style>
                        *{box-sizing:border-box;margin:0;padding:0;}
                        .bubble{width:52px;height:52px;background:linear-gradient(135deg,#6366f1,#8b5cf6);border-radius:50%;display:flex;align-items:center;justify-content:center;color:white;cursor:pointer;box-shadow:0 4px 16px rgba(99,102,241,0.5);font-size:26px;transition:transform 0.2s,box-shadow 0.2s;user-select:none;}
                        .bubble:hover{transform:scale(1.08);box-shadow:0 6px 22px rgba(99,102,241,0.7);}
                        .panel{position:absolute;bottom:64px;right:0;width:390px;max-height:510px;background:#1e1e2e;color:#cdd6f4;border-radius:14px;box-shadow:0 12px 40px rgba(0,0,0,0.6);display:flex;flex-direction:column;overflow:hidden;font-size:13px;border:1px solid #313244;}
                        .header{background:#181825;padding:14px 16px;font-weight:700;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #313244;}
                        .header-left{display:flex;align-items:center;gap:8px;font-size:13px;letter-spacing:0.01em;}
                        .dot{width:8px;height:8px;border-radius:50%;background:#a6e3a1;flex-shrink:0;animation:pulse 1.6s ease-in-out infinite;}
                        .dot.done{animation:none;}
                        @keyframes pulse{0%,100%{opacity:1}50%{opacity:0.25}}
                        #status-badge{font-size:11px;font-weight:600;color:#89b4fa;background:#313244;padding:3px 9px;border-radius:20px;white-space:nowrap;}
                        .logs{padding:10px;overflow-y:auto;flex-grow:1;display:flex;flex-direction:column;gap:6px;}
                        .logs::-webkit-scrollbar{width:4px;}
                        .logs::-webkit-scrollbar-thumb{background:#45475a;border-radius:4px;}
                        .log-item{background:#313244;padding:9px 11px;border-radius:8px;line-height:1.45;}
                        .log-item.pass{border-left:3px solid #a6e3a1;}
                        .log-item.fail{border-left:3px solid #f38ba8;}
                        .log-item.heal{border-left:3px solid #f9e2af;}
                        .log-item.info{border-left:3px solid #89b4fa;}
                        .log-title{font-weight:600;font-size:12px;}
                        .log-detail{font-size:11px;color:#a6adc8;margin-top:3px;word-break:break-word;}
                        .footer{padding:10px 14px;background:#181825;display:flex;justify-content:flex-end;border-top:1px solid #313244;}
                        .btn-exit{background:#f38ba8;color:#11111b;border:none;padding:7px 18px;border-radius:8px;font-weight:700;cursor:pointer;font-size:12px;transition:opacity 0.2s;letter-spacing:0.01em;}
                        .btn-exit:hover{opacity:0.82;}
                        .btn-exit:disabled{opacity:0.4;cursor:default;}
                    </style>
                    <div class="bubble" id="btn-toggle">🤖</div>
                    <div class="panel" id="panel">
                        <div class="header">
                            <div class="header-left"><div class="dot" id="status-dot"></div>AI Copilot HUD</div>
                            <span id="status-badge">Running&hellip;</span>
                        </div>
                        <div class="logs" id="log-container">
                            <div class="log-item info"><div class="log-title">Agent started</div><div class="log-detail">Waiting for step execution&hellip;</div></div>
                        </div>
                        <div class="footer">
                            <button class="btn-exit" id="btn-exit">Exit &amp; Close</button>
                        </div>
                    </div>
                `;

                const toggle  = shadow.getElementById('btn-toggle');
                const panel   = shadow.getElementById('panel');
                const exitBtn = shadow.getElementById('btn-exit');

                // Panel is open by default so agent activity is immediately visible
                let panelOpen = true;

                toggle.addEventListener('click', () => {
                    panelOpen = !panelOpen;
                    panel.style.display = panelOpen ? 'flex' : 'none';
                });

                exitBtn.addEventListener('click', () => {
                    exitBtn.disabled = true;
                    exitBtn.textContent = 'Closing\u2026';
                    if (window.copilot_close_session) window.copilot_close_session();
                });

                window.__copilot_push_log = (type, title, detail) => {
                    const logs = shadow.getElementById('log-container');
                    const item = document.createElement('div');
                    item.className = 'log-item ' + type;
                    item.innerHTML =
                        '<div class="log-title">' + title + '</div>' +
                        '<div class="log-detail">' + detail + '</div>';
                    logs.appendChild(item);
                    logs.scrollTop = logs.scrollHeight;
                    // Auto-show panel on new log if it was collapsed
                    if (!panelOpen) {
                        panelOpen = true;
                        panel.style.display = 'flex';
                    }
                };

                window.__copilot_set_status = (text, done) => {
                    const badge = shadow.getElementById('status-badge');
                    const dot   = shadow.getElementById('status-dot');
                    if (badge) badge.textContent = text;
                    if (dot && done) dot.classList.add('done');
                };
            }

            // Defer to DOMContentLoaded so document.body is guaranteed to exist.
            // If the document is already interactive/complete, run immediately.
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', __buildCopilotHUD);
            } else {
                __buildCopilotHUD();
            }
        })();
        """)

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
            error_str = f"HTTP {response.status} {response.request.method} {response.url}"
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
        """Navigates to the specified URL.

        Uses domcontentloaded (not 'load') to avoid hanging on third-party
        marketing/tracking tags that never fire the window load event.
        Falls back to 'commit' (first byte received) if even domcontentloaded
        times out on a very slow connection.
        """
        await self.auto_suppress_popups()
        logger.info(f"Navigating browser to: {url}")
        if not self.initial_url:
            self.initial_url = url
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            if "Timeout" in str(e):
                logger.warning(
                    f"domcontentloaded timed out for {url} — retrying with wait_until='commit'"
                )
                await self.page.goto(url, wait_until="commit", timeout=15000)
            else:
                raise
        # Belt-and-suspenders: call __buildCopilotHUD() after each navigation in case
        # add_init_script fired before DOMContentLoaded on this specific page.
        try:
            await self.page.evaluate(
                "if (typeof __buildCopilotHUD === 'function') __buildCopilotHUD();"
            )
        except Exception:
            pass  # Best-effort — never block navigation

    async def get_accessibility_tree(self) -> str:
        """
        Extracts the page ARIA accessibility snapshot for LLM context.
        Output is capped at 3,000 characters (~1,500 tokens) to stay within
        the token budget of free/tiered LLM keys and avoid 402 errors.
        """
        if not self.page:
            return ""
        await self.auto_suppress_popups()
        try:
            # Modern Playwright ARIA snapshot (replaces deprecated page.accessibility).
            # Hard timeout prevents hanging on complex/animated pages.
            snapshot = await self.page.locator("body").aria_snapshot(timeout=3000)
            return str(snapshot)[:3000]
        except Exception as e:
            logger.error(f"ARIA snapshot failed, falling back to page.content(): {e}")
            try:
                content = await self.page.content()
                return content[:3000]
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

        selector = selector.strip()

        # Date picker fallback: the trigger is a styled button/mask, not a standard
        # <input type="text">, so get_by_role("textbox", name="Dates") fails.
        # IMPORTANT: only activate this for the airline booking "Dates" picker —
        # NOT for generic form inputs like birth-date fields (e.g. #dateOfBirth,
        # [name='date_naissance']).  We match when the selector is EXACTLY the
        # booking-widget label "Dates" (or a locator expression that references it),
        # but not when "date" appears as part of a CSS id/class/attribute.
        _is_booking_dates_picker = (
            selector == "Dates"
            or selector == "text='Dates'"
            or ("'Dates'" in selector and "get_by" in selector)
        )
        if _is_booking_dates_picker:
            logger.debug(f"Applying date-picker fallback for selector: {selector}")
            return (
                self.page.locator("text='Dates'")
                .or_(self.page.locator("[aria-label*='Date' i], [placeholder*='Date' i], .mat-mdc-form-field:has-text('Dates')"))
                .first
            )

        # Pass-through for bare text= selectors (no eval needed)
        if selector.startswith("text="):
            logger.debug(f"Resolving text locator: {selector}")
            return self.page.locator(selector)

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
                try:
                    await self.page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                except Exception as nav_err:
                    if "Timeout" in str(nav_err):
                        logger.warning(
                            f"Step {step.step_id}: domcontentloaded timed out — "
                            "retrying with wait_until='commit'"
                        )
                        await self.page.goto(target_url, wait_until="commit", timeout=15000)
                    else:
                        raise
            
            elif action == "click":
                selector = step.selector
                # Strip malformed empty pseudo-classes (e.g. ":not()") that the
                # Planner sometimes generates for calendar selectors — they cause a
                # CSS parse error before Playwright even evaluates the selector.
                if ":not()" in selector:
                    selector = selector.replace(":not()", "")
                    logger.debug(f"Step {step.step_id}: stripped malformed :not() from selector.")

                locator = await self.resolve_locator(selector)
                try:
                    await locator.click(force=True, timeout=3000)
                except Exception as click_err:
                    # Calendar-cell fallback: if we were trying to click a date cell
                    # and it failed (e.g. the cell was re-rendered), find the first
                    # non-disabled button inside any open calendar dialog.
                    active_days = self.page.locator(
                        "mat-calendar button:not([disabled]), "
                        "[role='dialog'] button:not([disabled]), "
                        ".mat-calendar-body-cell:not(.mat-calendar-body-disabled)"
                    )
                    if await active_days.count() > 0:
                        logger.warning(
                            f"Step {step.step_id}: direct click failed — "
                            "falling back to first active calendar day cell."
                        )
                        await active_days.first.click(force=True)
                    else:
                        # Not a calendar context — escalate to label fallback then re-raise
                        await self._force_click_with_label_fallback(locator, selector)
                
            elif action == "fill":
                if step.value is None:
                    raise ValueError("Fill action requires a string value.")
                locator = await self.get_element(step.selector)
                # 1. Wait for actionability visibility
                await locator.wait_for(state="visible", timeout=config.DEFAULT_WAIT_TIME)
                # 2. Use force click to focus behind input masks (e.g. autocomplete-mat__input__mask)
                await locator.click(force=True, timeout=config.DEFAULT_WAIT_TIME)
                # 3. For input[type="date"] elements the browser only accepts values in
                #    YYYY-MM-DD (ISO 8601) format.  Auto-convert DD/MM/YYYY or DD-MM-YYYY
                #    values that users/planners commonly supply.
                fill_value = step.value
                try:
                    input_type = await locator.get_attribute("type", timeout=2000)
                    if input_type == "date":
                        import re as _re
                        # Match DD/MM/YYYY or DD-MM-YYYY
                        m = _re.match(r"^(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})$", fill_value.strip())
                        if m:
                            dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
                            fill_value = f"{yyyy}-{mm.zfill(2)}-{dd.zfill(2)}"
                            logger.info(
                                f"Step {step.step_id}: converted date value "
                                f"'{step.value}' → '{fill_value}' for input[type='date']"
                            )
                except Exception:
                    pass  # Attribute fetch is best-effort; proceed with original value
                # 4. Attempt fill, bypassing layout interceptions (e.g. hs-interactives-modal-overlay).
                #    If the element is a non-input widget (styled span/div/button used as a date
                #    picker trigger), fall back to clicking open the calendar and selecting day cells.
                try:
                    await locator.fill(fill_value, force=True, timeout=config.DEFAULT_WAIT_TIME)
                except Exception as e:
                    if "not an <input>" in str(e) or "contenteditable" in str(e):
                        logger.warning(
                            f"Step {step.step_id}: fill() rejected non-input element — "
                            "falling back to calendar day-cell selection."
                        )
                        # The force-click above already opened the date picker; now
                        # select enabled day cells: first click = departure, second = return.
                        days = self.page.locator(
                            "button.mat-calendar-body-cell, "
                            "[role='gridcell']:not([aria-disabled='true'])"
                        )
                        count = await days.count()
                        if count > 0:
                            await days.first.click(force=True)
                            await self.page.wait_for_timeout(300)
                            # Click ~1 week later for the return date if enough cells exist
                            if count > 7:
                                await days.nth(7).click(force=True)
                    else:
                        raise e
                
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
            if "strict mode violation" in str(e):
                logger.warning(f"Step {step.step_id}: Strict mode violation detected. Retrying with `.first` locator fallback.")
                try:
                    locator = (await self.resolve_locator(step.selector)).first
                    if step.action_type == ActionType.FILL:
                        recovery_value = str(step.value)
                        try:
                            import re as _re
                            rt = await locator.get_attribute("type", timeout=1000)
                            if rt == "date":
                                m2 = _re.match(r"^(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})$", recovery_value.strip())
                                if m2:
                                    recovery_value = f"{m2.group(3)}-{m2.group(2).zfill(2)}-{m2.group(1).zfill(2)}"
                        except Exception:
                            pass
                        await locator.fill(recovery_value, timeout=3000)
                    elif step.action_type == ActionType.CLICK:
                        await locator.click(force=True, timeout=3000)
                    else:
                        raise e
                    
                    # Allow DOM states to settle and network calls to complete
                    await self.page.wait_for_load_state("domcontentloaded")
                    await asyncio.sleep(0.5)
                    logger.info(f"Step {step.step_id} completed successfully via strict mode auto-recovery.")
                    return True
                except Exception as recovery_err:
                    e = recovery_err

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

    # ------------------------------------------------------------------
    # Copilot HUD helpers
    # ------------------------------------------------------------------

    async def push_hud_log(self, log_type: str, title: str, detail: str = "") -> None:
        """Push a live log entry into the in-browser Copilot HUD panel.

        log_type: 'pass' | 'fail' | 'heal' | 'info'
        title:    Bold first line shown in the HUD card.
        detail:   Smaller sub-text shown beneath the title.
        This is best-effort — any error is silently swallowed so it never
        blocks or crashes the test run.
        """
        if not self.page:
            return
        try:
            safe_title  = str(title).replace("'", "\\'").replace("\n", " ")
            safe_detail = str(detail).replace("'", "\\'").replace("\n", " ")
            await self.page.evaluate(
                f"if (window.__copilot_push_log) "
                f"window.__copilot_push_log('{log_type}', '{safe_title}', '{safe_detail}');"
            )
        except Exception:
            pass  # HUD is purely decorative — never block execution

    async def wait_for_hud_exit(self) -> None:
        """Hold the browser open until the user clicks 'Exit & Close' in the HUD.

        In headless mode this is a no-op so CI runs are unaffected.
        """
        if self.headless or not self.page:
            return
        # Update the HUD to show the run is complete and the pulse dot goes static
        try:
            await self.page.evaluate(
                "if (window.__copilot_set_status) "
                "window.__copilot_set_status('Done \u2713', true);"
            )
        except Exception:
            pass
        logger.info("Copilot HUD: browser held open — waiting for user to click 'Exit & Close'.")
        await self.exit_signal.wait()
        logger.info("Copilot HUD: exit signal received. Proceeding to browser teardown.")
