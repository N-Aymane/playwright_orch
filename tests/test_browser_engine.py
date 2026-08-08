import unittest
from types import SimpleNamespace
import asyncio

from browser_engine import PlaywrightBrowserEngine


class DummyConsoleMessage:
    def __init__(self, msg_type, text, location):
        self.type = msg_type
        self.text = text
        self.location = location


class BrowserEngineConsoleHandlingTests(unittest.TestCase):
    def test_handle_console_accepts_string_location(self):
        engine = PlaywrightBrowserEngine()
        msg = DummyConsoleMessage("error", "boom", "https://example.com/app")

        engine._handle_console(msg)

        self.assertEqual(len(engine.console_logs), 1)
        self.assertIn("boom", engine.console_logs[0])
        self.assertIn("https://example.com/app", engine.console_logs[0])


class BrowserEngineNavigationFallbackTests(unittest.TestCase):
    def test_execute_action_falls_back_to_initial_url_for_broken_navigate_step(self):
        engine = PlaywrightBrowserEngine()
        engine.initial_url = "https://example.com/start"

        captured = {}

        async def fake_goto(url, wait_until=None, timeout=None):
            captured["url"] = url
            captured["wait_until"] = wait_until
            captured["timeout"] = timeout

        async def fake_wait_for_load_state(*args, **kwargs):
            return None

        engine.page = SimpleNamespace(goto=fake_goto, wait_for_load_state=fake_wait_for_load_state)

        step = SimpleNamespace(
            step_id=1,
            description="Navigate to target",
            action_type=SimpleNamespace(value="NAVIGATE"),
            value=None,
            selector="button[id*='cookie']",
            error_message=None,
        )

        result = asyncio.run(engine.execute_action(step))

        self.assertTrue(result)
        self.assertEqual(captured["url"], "https://example.com/start")
        self.assertEqual(captured["wait_until"], "domcontentloaded")
        self.assertEqual(captured["timeout"], 15000)


class BrowserEngineInteractionFallbackTests(unittest.TestCase):
    def test_execute_action_check_falls_back_to_label_click(self):
        engine = PlaywrightBrowserEngine()

        events = []

        class FakeLabelLocator:
            async def click(self, force=False, timeout=None):
                events.append(("label_click", force, timeout))

        class FakeLocator:
            def __init__(self):
                self.label = FakeLabelLocator()

            async def check(self, force=False, timeout=None):
                events.append(("check", force, timeout))
                raise Exception("intercepted")

            async def click(self, force=False, timeout=None):
                events.append(("click", force, timeout))
                raise Exception("intercepted")

            def locator(self, query):
                events.append(("locator", query))
                return self.label

        async def fake_wait_for_load_state(*args, **kwargs):
            return None

        engine.page = SimpleNamespace(wait_for_load_state=fake_wait_for_load_state)

        async def fake_resolve_locator(selector):
            return FakeLocator()

        engine.resolve_locator = fake_resolve_locator

        step = SimpleNamespace(
            step_id=3,
            description="Check radio option",
            action_type=SimpleNamespace(value="CHECK"),
            selector="input[type='radio']",
            value=None,
            error_message=None,
        )

        result = asyncio.run(engine.execute_action(step))

        self.assertTrue(result)
        self.assertIn(("check", False, 3000), events)
        self.assertIn(("check", True, 3000), events)
        self.assertIn(("click", True, 3000), events)
        self.assertIn(("label_click", True, 3000), events)

    def test_execute_action_click_uses_force_fallback(self):
        engine = PlaywrightBrowserEngine()

        events = []

        class FakeLocator:
            async def click(self, force=False, timeout=None):
                events.append(("click", force, timeout))
                if not force:
                    raise Exception("intercepted")

        async def fake_wait_for_load_state(*args, **kwargs):
            return None

        engine.page = SimpleNamespace(wait_for_load_state=fake_wait_for_load_state)

        async def fake_resolve_locator(selector):
            return FakeLocator()

        engine.resolve_locator = fake_resolve_locator

        step = SimpleNamespace(
            step_id=4,
            description="Click submit",
            action_type=SimpleNamespace(value="CLICK"),
            selector="button.submit",
            value=None,
            error_message=None,
        )

        result = asyncio.run(engine.execute_action(step))

        self.assertTrue(result)
        self.assertIn(("click", False, 3000), events)
        self.assertIn(("click", True, 3000), events)


class AccessibilityTreeFormattingTests(unittest.TestCase):
    def test_format_accessibility_tree_handles_dict(self):
        from utils.dom_parser import format_accessibility_tree
        snapshot = {
            "role": "button",
            "name": "Submit",
            "children": []
        }
        res = format_accessibility_tree(snapshot)
        self.assertIn("<button 'Submit'>", res)

    def test_format_accessibility_tree_handles_json_string(self):
        from utils.dom_parser import format_accessibility_tree
        import json
        snapshot = json.dumps({
            "role": "textbox",
            "name": "Username",
            "children": []
        })
        res = format_accessibility_tree(snapshot)
        self.assertIn("<textbox 'Username'>", res)

    def test_format_accessibility_tree_handles_plain_string(self):
        from utils.dom_parser import format_accessibility_tree
        snapshot = "Plain text accessibility info"
        res = format_accessibility_tree(snapshot)
        self.assertEqual(res, "Plain text accessibility info")

    def test_format_accessibility_tree_handles_none(self):
        from utils.dom_parser import format_accessibility_tree
        self.assertEqual(format_accessibility_tree(None), "<Empty Accessibility Tree>")


if __name__ == "__main__":
    unittest.main()
