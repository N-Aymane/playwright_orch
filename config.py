import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

# API Keys (Groq is fully OpenAI-compatible)
OPENAI_API_KEY = os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
GROQ_API_KEY = OPENAI_API_KEY
API_KEY = OPENAI_API_KEY

if not OPENAI_API_KEY:
    raise ValueError("Missing API Key! Please set GROQ_API_KEY in your .env file.")

OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "https://api.groq.com/openai/v1")
BASE_URL = OPENAI_API_BASE

# Model Settings
LLM_MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
MODEL_NAME = LLM_MODEL
LLM_TEMPERATURE = 0.0
TEMPERATURE = 0.0
LLM_MAX_TOKENS = 4096
MAX_TOKENS = 4096
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
    return ChatOpenAI(
        model=LLM_MODEL,
        openai_api_key=OPENAI_API_KEY,
        openai_api_base=OPENAI_API_BASE,
        temperature=LLM_TEMPERATURE,
        max_tokens=LLM_MAX_TOKENS,
    )

class LangChainOpenAIWrapper:
    """
    OpenAI client wrapper around LangChain's ChatOpenAI.
    Ensures backward compatibility with agent classes calling `llm.chat.completions.create()`.
    """
    def __init__(self, langchain_client: ChatOpenAI):
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
            invoke_params["max_tokens"] = max_tokens

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