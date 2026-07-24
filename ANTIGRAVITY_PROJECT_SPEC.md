# Autonomous Web Testing & Self-Healing Multi-Agent System: Technical Specification & Implementation Architecture

## 1. Executive Summary & Vision

This project defines an autonomous, multi-agent web automation and testing system designed to dynamically explore web applications, fill out forms based on real-time DOM inspection, assert complex visual/state transitions, and self-heal whenever UI updates or locator changes break expected action paths.

The orchestrator operates using **LangGraph** (or pure AsyncIO state routing), managing three specialized sub-agents that share state via a unified Execution Context:
1. **Planner Agent**: Performs exploratory navigation, breaks down user intents into discrete test steps, and builds execution graphs.
2. **Executor Agent**: Inspects interactive form controls, synthesizes contextually valid input data (Pydantic-validated), and executes Playwright browser actions.
3. **Healer Agent**: Intercepts locator timeouts, DOM morphing, or runtime exceptions, analyzes page accessibility trees and visual states, generates alternative Playwright locators, and patches execution steps dynamically.

---

## 2. Project Architecture & Directory Layout

To ensure modularity and ease of maintenance, Antigravity must structure the project as follows:

```
agentic_web_tester/
│
├── config.py                 # System configuration, LLM parameters, Playwright browser settings
├── schemas.py                # Pydantic data models for state, steps, tools, and test results
├── browser_engine.py         # Async Playwright wrapper with accessibility snapshotting & tracing
├── orchestrator.py           # LangGraph state machine & multi-agent routing graph
│
├── agents/
│   ├── __init__.py
│   ├── planner.py            # Plan generation & goal breakdown
│   ├── executor.py           # Action execution & dynamic form-data synthesis
│   └── healer.py             # Self-healing locator repair & fallback engine
│
├── utils/
│   ├── __init__.py
│   ├── dom_parser.py         # Accessibility snapshot parsing & token reduction
│   ├── logger.py             # Structured JSON & console logging
│   └── reporter.py           # HTML / JSON test summary report generator
│
├── main.py                   # CLI entry point to run test flows against target URLs
├── requirements.txt          # Python dependency specifications
└── README.md                 # Setup, configuration, and execution guidelines
```

---

## 3. Core Module Specifications

### 3.1 `schemas.py` (Data Models & State Definition)

```python
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class ActionType(str, Enum):
    NAVIGATE = "navigate"
    CLICK = "click"
    FILL = "fill"
    SELECT = "select"
    CHECK = "check"
    ASSERT_TEXT = "assert_text"
    WAIT_FOR_SELECTOR = "wait_for_selector"

class TestStep(BaseModel):
    step_id: int
    description: str
    action_type: ActionType
    selector: Optional[str] = None
    selector_type: Optional[str] = "css"  # css, xpath, role, text
    value: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    status: str = "pending"  # pending, passed, failed, healed
    error_message: Optional[str] = None

class AgentState(BaseModel):
    url: str
    task_goal: str
    current_step_index: int = 0
    steps: List[TestStep] = []
    accessibility_snapshot: Optional[Dict[str, Any]] = None
    last_error: Optional[str] = None
    console_logs: List[str] = []
    failed_network_requests: List[str] = []
    is_complete: bool = False
    test_passed: bool = True
```

---

### 3.2 `browser_engine.py` (Playwright Integration)

The browser engine encapsulates Playwright within an async class, handling page lifecycle, DOM parsing, network monitoring, and tracing.

```python
import asyncio
from typing import Dict, Any, List, Optional
from playwright.async_api import async_playwright, Page, Browser, Playwright

class PlaywrightBrowserEngine:
    def __init__(self, headless: bool = False):
        self.headless = headless
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.console_logs: List[str] = []
        self.network_errors: List[str] = []

    async def initialize(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=["--disable-dev-shm-usage"]
        )
        context = await self.browser.new_context(viewport={"width": 1280, "height": 720})
        
        # Start tracing
        await context.tracing.start(screenshots=True, snapshots=True, sources=True)
        self.page = await context.new_page()

        # Listen for console errors & failed requests
        self.page.on("console", lambda msg: self.console_logs.append(f"[{msg.type}] {msg.text}") if msg.type in ["error", "warning"] else None)
        self.page.on("response", lambda resp: self.network_errors.append(f"{resp.status} {resp.url}") if resp.status >= 400 else None)

    async def navigate(self, url: str):
        await self.page.goto(url, wait_until="networkidle")

    async def get_accessibility_tree(self) -> Dict[str, Any]:
        # Extract accessibility tree
        return await self.page.accessibility.snapshot()

    async def execute_action(self, step) -> bool:
        try:
            if step.action_type == "navigate":
                await self.navigate(step.value)
            elif step.action_type == "click":
                await self.page.click(step.selector, timeout=5000)
            elif step.action_type == "fill":
                await self.page.fill(step.selector, step.value, timeout=5000)
            elif step.action_type == "select":
                await self.page.select_option(step.selector, step.value, timeout=5000)
            elif step.action_type == "assert_text":
                content = await self.page.content()
                assert step.value in content, f"Expected text '{step.value}' not found on page."
            
            await self.page.wait_for_load_state("domcontentloaded")
            return True
        except Exception as e:
            step.error_message = str(e)
            return False

    async def stop(self, trace_path: str = "trace.zip"):
        if self.page and self.page.context:
            await self.page.context.tracing.stop(path=trace_path)
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
```

---

### 3.3 `orchestrator.py` (LangGraph State Machine)

The orchestrator routes state between Planner, Executor, and Healer nodes.

```python
from langgraph.graph import StateGraph, END
from schemas import AgentState, TestStep
from agents.planner import PlannerAgent
from agents.executor import ExecutorAgent
from agents.healer import HealerAgent

def create_orchestrator_graph(browser_engine, llm_client):
    planner = PlannerAgent(llm_client)
    executor = ExecutorAgent(browser_engine, llm_client)
    healer = HealerAgent(browser_engine, llm_client)

    graph = StateGraph(AgentState)

    # Define Nodes
    async def plan_node(state: AgentState):
        state.steps = await planner.generate_plan(state.url, state.task_goal)
        return state

    async def execute_node(state: AgentState):
        current_step = state.steps[state.current_step_index]
        
        # Ingest dynamic form requirements if action is FILL and value is empty
        if current_step.action_type == "fill" and not current_step.value:
            current_step.value = await executor.generate_form_data(current_step, state.accessibility_snapshot)

        success = await browser_engine.execute_action(current_step)
        
        if success:
            current_step.status = "passed"
            state.current_step_index += 1
            if state.current_step_index >= len(state.steps):
                state.is_complete = True
        else:
            current_step.status = "failed"
            state.last_error = current_step.error_message

        # Refresh page snapshot
        state.accessibility_snapshot = await browser_engine.get_accessibility_tree()
        return state

    async def heal_node(state: AgentState):
        failed_step = state.steps[state.current_step_index]
        
        if failed_step.retry_count >= failed_step.max_retries:
            state.is_complete = True
            state.test_passed = False
            return state

        # Request Healer Agent to propose new selector
        new_selector = await healer.heal_selector(
            failed_step=failed_step,
            snapshot=state.accessibility_snapshot,
            error=state.last_error
        )
        
        if new_selector:
            failed_step.selector = new_selector
            failed_step.retry_count += 1
            failed_step.status = "healed"
        else:
            state.is_complete = True
            state.test_passed = False

        return state

    # Conditional Router
    def route_execution(state: AgentState):
        if state.is_complete:
            return END
        current_step = state.steps[state.current_step_index]
        if current_step.status == "failed":
            return "heal"
        return "execute"

    # Build Graph Structure
    graph.add_node("plan", plan_node)
    graph.add_node("execute", execute_node)
    graph.add_node("heal", heal_node)

    graph.set_entry_point("plan")
    graph.add_edge("plan", "execute")
    graph.add_conditional_edges("execute", route_execution, {"execute": "execute", "heal": "heal", END: END})
    graph.add_edge("heal", "execute")

    return graph.compile()
```

---

## 4. Agent Prompts & Strategies

### 4.1 Planner Agent System Prompt
```
You are an expert QA Automation Planner. 
Given a target URL and testing goal, examine the provided page accessibility tree.
Break down the task into sequential atomic actions (NAVIGATE, CLICK, FILL, SELECT, ASSERT_TEXT).
Output ONLY a JSON array matching the TestStep schema. Always start with NAVIGATE to the target URL.
```

### 4.2 Executor Form Data Generation Prompt
```
You are an intelligent form executor. 
Examine the form field described by selector '{selector}' and DOM context '{context}'.
Generate a realistic, syntactically correct input value based on field type and attributes:
- If email: produce a valid mock email address (e.g. user_test_99@example.com)
- If password: produce a complex 12-char password meeting standard criteria
- If phone: produce a standard 10-digit phone number
- If text: generate contextually appropriate short string
Return strictly the unquoted string value.
```

### 4.3 Healer Agent System Prompt
```
You are an expert Playwright Self-Healing Agent.
A step failed with error: '{error}'
Failed step details: Selector: '{failed_selector}', Action: '{action_type}'
Current Accessibility Tree: {accessibility_snapshot}

Analyze why the element failed to locate. Inspect the accessibility tree to find the newly updated or equivalent UI target.
Generate a resilient updated Playwright selector:
- Prefer role-based locators (e.g., getByRole('button', { name: 'Submit' })) or CSS class combinations.
- Avoid volatile IDs or long rigid XPaths.
Return strictly the updated selector string.
```

---

## 5. Dependencies (`requirements.txt`)

```
playwright>=1.42.0
langgraph>=0.0.25
langchain-core>=0.1.30
pydantic>=2.6.0
openai>=1.14.0
python-dotenv>=1.0.1
rich>=13.7.0
```

---

## 6. Execution Flow Checklist for Antigravity

1. **Environment Setup**: Initialize Python virtual environment, run `pip install -r requirements.txt`, and execute `playwright install chromium`.
2. **Configuration**: Set `OPENAI_API_KEY` (or local LLM endpoints) in `.env` or `config.py`.
3. **Run CLI**: Execute `python main.py --url "https://example-form-site.com" --goal "Test user registration form with valid inputs"`.
4. **Inspect Trace**: Open generated `trace.zip` using `npx playwright show-trace trace.zip` to review execution snapshots, network calls, and healed actions.
