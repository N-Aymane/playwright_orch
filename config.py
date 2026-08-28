import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

# API Keys & Provider Config
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
GOOGLE_API_KEY = GEMINI_API_KEY
OPENAI_API_KEY = GEMINI_API_KEY  # Kept for backward compatibility with existing main.py checks
API_KEY = GEMINI_API_KEY

if not GEMINI_API_KEY:
    raise ValueError("Missing Gemini API Key! Please set GEMINI_API_KEY or GOOGLE_API_KEY in your .env file.")

# Model & Parameter Settings
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.0-flash")
MODEL_NAME = LLM_MODEL
LLM_TEMPERATURE = 0.0
TEMPERATURE = 0.0
LLM_MAX_TOKENS = 4096
MAX_TOKENS = 4096

# Expected variables for backward compatibility
OPENAI_API_BASE = None
PLANNER_MAX_TOKENS = int(os.getenv("PLANNER_MAX_TOKENS", "4096"))
EXECUTOR_MAX_TOKENS = int(os.getenv("EXECUTOR_MAX_TOKENS", "128"))
HEALER_MAX_TOKENS = int(os.getenv("HEALER_MAX_TOKENS", "256"))
CONSOLE_ANALYSIS_MAX_TOKENS = int(os.getenv("CONSOLE_ANALYSIS_MAX_TOKENS", "256"))
DEFAULT_WAIT_TIME = int(os.getenv("DEFAULT_WAIT_TIME", "5000"))
BROWSER_TIMEOUT = int(os.getenv("BROWSER_TIMEOUT", "10000"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Playwright & Reporting Paths
TRACE_PATH = "trace.zip"
REPORT_PATH = "report.html"
HTML_REPORT_PATH = "report.html"
JSON_REPORT_PATH = "report.json"
HEADLESS = False
TIMEOUT = 30000

def get_llm_client():
    return ChatGoogleGenerativeAI(
        model=LLM_MODEL,
        google_api_key=GEMINI_API_KEY,
        temperature=LLM_TEMPERATURE,
        max_output_tokens=LLM_MAX_TOKENS,
    )

class LangChainOpenAIWrapper:
    """
    OpenAI client wrapper around LangChain's ChatGoogleGenerativeAI.
    Ensures backward compatibility with agent classes calling `llm.chat.completions.create()`.
    """
    def __init__(self, langchain_client: ChatGoogleGenerativeAI):
        self.langchain_client = langchain_client
        self.chat = self
        self.completions = self

    async def create(self, model=None, messages=None, temperature=None, max_tokens=None, **kwargs):
        from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
        lc_messages = []
        if messages:
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "system":
                    lc_messages.append(SystemMessage(content=content))
                elif role == "user":
                    lc_messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    lc_messages.append(AIMessage(content=content))

        invoke_params = {}
        if temperature is not None:
            invoke_params["temperature"] = temperature
        if max_tokens is not None:
            invoke_params["max_output_tokens"] = max_tokens

        response = await self.langchain_client.ainvoke(lc_messages, **invoke_params)

        raw_content = response.content
        if isinstance(raw_content, list):
            parts = []
            for part in raw_content:
                if isinstance(part, dict):
                    if "text" in part:
                        parts.append(part["text"])
                    elif part.get("type") == "text":
                        parts.append(part.get("text", ""))
                elif isinstance(part, str):
                    parts.append(part)
                else:
                    parts.append(str(part))
            text_content = "".join(parts)
        else:
            text_content = str(raw_content)

        class Choice:
            class Message:
                def __init__(self, content):
                    self.content = content
            def __init__(self, content):
                self.message = Choice.Message(content)

        class Response:
            def __init__(self, content):
                self.choices = [Choice(content)]

        return Response(text_content)