import os
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

# LLM Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.0"))

# Playwright Configuration
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
BROWSER_TIMEOUT = int(os.getenv("BROWSER_TIMEOUT", "10000"))  # ms
DEFAULT_WAIT_TIME = int(os.getenv("DEFAULT_WAIT_TIME", "5000"))  # ms

# Tracing and Reporting
TRACE_PATH = os.getenv("TRACE_PATH", "trace.zip")
REPORT_PATH = os.getenv("REPORT_PATH", "report.html")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
