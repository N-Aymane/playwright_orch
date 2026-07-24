import json
import re
from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI
from schemas import TestStep, ActionType, AgentState
from utils.logger import get_logger
from utils.dom_parser import format_accessibility_tree
import config

logger = get_logger("planner_agent")

PLANNER_SYSTEM_PROMPT = """You are an expert QA Automation Planner specializing in end-to-end web testing.

Given a target URL and a high-level testing goal, you will examine the provided page accessibility tree and generate a precise, step-by-step test execution plan.

Your output MUST be a valid JSON array of TestStep objects matching exactly this schema:
[
  {
    "step_id": <integer starting at 1>,
    "description": "<human readable description of what this step does>",
    "action_type": "<one of: navigate, click, fill, select, check, assert_text, wait_for_selector>",
    "selector": "<CSS selector, XPath, or Python Playwright locator expression. Required for all actions except navigate>",
    "selector_type": "<one of: css, xpath, role>",
    "value": "<the value to use for fill/select/navigate/assert_text actions. Null for click/check/wait_for_selector>"
  }
]

IMPORTANT RULES:
- Always start with a NAVIGATE step to the target URL.
- For form fill steps where you don't know the value (e.g., email, password), set "value" to null — the Executor Agent will synthesize it.
- Prefer role-based Playwright locator expressions for robustness (e.g., page.get_by_role('button', name='Sign Up')).
- For CSS selectors, use semantic attributes: #id, [name="field"], [type="email"] over brittle positional selectors.
- Always end with at least one ASSERT_TEXT step to verify the outcome (e.g., success message, next page heading).
- Output ONLY the raw JSON array. No explanation, no markdown fences, no extra text.
"""

class PlannerAgent:
    def __init__(self, llm_client: AsyncOpenAI):
        self.llm = llm_client
        logger.info("PlannerAgent initialized.")

    async def generate_plan(self, url: str, task_goal: str, accessibility_snapshot: Optional[Dict[str, Any]] = None) -> List[TestStep]:
        """
        Calls the LLM with the target URL, goal, and (optionally) the page accessibility tree
        to generate a list of TestStep objects representing the full test plan.
        """
        logger.info(f"Generating test plan for URL: {url} | Goal: {task_goal}")

        # Format snapshot for prompt if available
        snapshot_context = ""
        if accessibility_snapshot:
            snapshot_context = f"\n\nCurrent Page Accessibility Tree:\n{format_accessibility_tree(accessibility_snapshot)}"

        user_message = f"""Target URL: {url}
Testing Goal: {task_goal}{snapshot_context}

Generate the complete step-by-step test execution plan as a JSON array."""

        try:
            response = await self.llm.chat.completions.create(
                model=config.LLM_MODEL,
                temperature=config.LLM_TEMPERATURE,
                messages=[
                    {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message}
                ]
            )

            raw_output = response.choices[0].message.content.strip()
            logger.debug(f"Planner raw LLM output:\n{raw_output}")

            # Extract JSON array from response
            steps_data = self._extract_json(raw_output)
            steps = []
            for i, step_dict in enumerate(steps_data):
                # Normalize action_type case
                step_dict["action_type"] = step_dict.get("action_type", "navigate").lower()
                # Ensure step_id is correct
                step_dict["step_id"] = i + 1
                step = TestStep(**step_dict)
                steps.append(step)
            
            logger.info(f"Planner generated {len(steps)} test steps.")
            return steps

        except Exception as e:
            logger.error(f"PlannerAgent failed to generate plan: {e}")
            raise

    def _extract_json(self, raw_text: str) -> List[Dict[str, Any]]:
        """
        Robustly extracts a JSON array from LLM output, even if surrounded by prose or markdown.
        """
        # Try direct parse first
        try:
            result = json.loads(raw_text)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

        # Strip markdown code fences
        cleaned = re.sub(r"```(?:json)?", "", raw_text).strip().rstrip("```").strip()
        try:
            result = json.loads(cleaned)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

        # Find JSON array with regex
        match = re.search(r"\[.*\]", raw_text, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group(0))
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                pass

        raise ValueError(f"Could not extract a valid JSON array from planner output:\n{raw_text}")
