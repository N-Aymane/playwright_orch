import os
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

# LLM Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", os.getenv("OPENROUTER_API_KEY", ""))
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "https://openrouter.ai/api/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-4.1-mini")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.0"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1024"))

# Per-agent caps keep output budgets small and predictable.
PLANNER_MAX_TOKENS = int(os.getenv("PLANNER_MAX_TOKENS", "1024"))
EXECUTOR_MAX_TOKENS = int(os.getenv("EXECUTOR_MAX_TOKENS", "128"))
HEALER_MAX_TOKENS = int(os.getenv("HEALER_MAX_TOKENS", "128"))
CONSOLE_ANALYSIS_MAX_TOKENS = int(os.getenv("CONSOLE_ANALYSIS_MAX_TOKENS", "256"))

# Playwright Configuration
HEADLESS = os.getenv("HEADLESS", "false").lower() == "true"
BROWSER_TIMEOUT = int(os.getenv("BROWSER_TIMEOUT", "10000"))  # ms
DEFAULT_WAIT_TIME = int(os.getenv("DEFAULT_WAIT_TIME", "5000"))  # ms

# Tracing and Reporting
TRACE_PATH = os.getenv("TRACE_PATH", "trace.zip")
REPORT_PATH = os.getenv("REPORT_PATH", "report.html")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
