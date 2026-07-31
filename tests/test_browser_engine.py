import unittest

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
