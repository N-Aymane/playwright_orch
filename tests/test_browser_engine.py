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


if __name__ == "__main__":
    unittest.main()
