import json
import re
from typing import List, Dict, Any, Optional, Union
from openai import AsyncOpenAI
from schemas import TestStep, ActionType, AgentState
from utils.logger import get_logger
from utils.dom_parser import format_accessibility_tree
import config

logger = get_logger("planner_agent")

PLANNER_SYSTEM_PROMPT = """OUTPUT RULE #1 (NON-NEGOTIABLE): Respond with ONLY a raw JSON array. No prose. No reasoning. No markdown. No explanation. The very first character of your response MUST be `[` and the very last MUST be `]`.

You are an Autonomous QA Planner. Given a target URL and a testing goal, produce a step-by-step test plan as a JSON array of TestStep objects.

SCHEMA (every object must match exactly):
{
  "step_id": <integer, starting at 1>,
  "description": "<short human-readable description>",
  "action_type": "<navigate | click | fill | select | check | assert_text | wait_for_selector>",
  "selector": "<Playwright locator string — see selector rules below — null only for navigate>",
  "value": "<string value for fill/select/navigate/assert_text, null for click/check/wait_for_selector>"
}

SELECTOR RULES:
- Prefer: page.get_by_role('button', name='Submit') or page.get_by_label('Email')
- Acceptable: CSS id/attribute selectors like #email, [name="password"], input[type="date"]
- For password and confirm-password fields always use: #password and #password-confirm
- For plain text matches: text='Sign In'
- NEVER include a separate selector_type field — omit it entirely.

FORBIDDEN (will cause the run to fail):
- Any text before the opening `[`
- Any text after the closing `]`
- Chain-of-thought, reasoning paragraphs, or "let me think…" preamble
- Complex chained CSS :not() pseudo-classes (e.g. button:not([disabled]):not(.foo))
- Markdown code fences (```json)

EXECUTION RULES:
1. Always start with a NAVIGATE step to the target URL.
2. Always end with at least one ASSERT_TEXT step to verify the outcome.
3. For any form field where the user did NOT provide a value, set value: null — the Executor Agent will synthesize realistic mock data.
4. Ignore cookie/consent popups — the framework handles these automatically.
5. Adapt selector text to the site's language (e.g., French labels for French sites).

FORM REGISTRATION RULES:
1. When the goal targets a registration/sign-up form, fill ALL required fields (first name, last name, email, date of birth, phone, password, confirm password).
2. The Keycloak registration submit button is labeled 'Enregistrement' — use: page.get_by_role('button', name='Enregistrement')
3. Password and confirm-password: use selectors #password and #password-confirm to avoid strict-mode collisions.
4. Date of birth fields (e.g. 'Date de naissance') are plain HTML inputs — use action_type "fill", NOT a calendar click sequence.

AIRLINE BOOKING DATE PICKER (calendar widget only):
The airline booking "Dates" widget is an interactive calendar — NOT a plain input. Sequence:
1. CLICK the "Dates" label/button to open the calendar.
2. CLICK an available day cell for departure.
3. CLICK a second day cell for return (round trip only).
Do NOT use fill on the airline booking "Dates" widget.

DESTINATION COMBOBOX RULE:
The destination field is a combobox widget. Never use fill on it. Use:
  Step A: click → page.get_by_role('combobox', name='Sélectionnez une destination')
  Step B: click → page.get_by_role('option', name='Paris')

CALENDAR SELECTORS:
Use only simple selectors for day cells — never complex :not() chains:
- page.get_by_role('button', name='15')  ← preferred
- mat-calendar button, [role='gridcell']  ← acceptable
"""
class PlannerAgent:
    def __init__(self, llm_client: AsyncOpenAI):
        self.llm = llm_client
        logger.info("PlannerAgent initialized.")

    async def generate_plan(self, url: str, task_goal: str, accessibility_snapshot: Optional[Union[str, Dict[str, Any]]] = None) -> List[TestStep]:
        """
        Calls the LLM with the target URL, goal, and (optionally) the page accessibility tree
        to generate a list of TestStep objects representing the full test plan.
        If the model responds with prose/chain-of-thought instead of JSON (common with
        reasoning-style free models), a follow-up message requests the JSON array only.
        """
        logger.info(f"Generating test plan for URL: {url} | Goal: {task_goal}")

        # Cap snapshot to 1,500 chars so reasoning + JSON fit inside PLANNER_MAX_TOKENS
        snapshot_context = ""
        if accessibility_snapshot:
            raw = format_accessibility_tree(accessibility_snapshot)
            snapshot_context = f"\n\nCurrent Page Accessibility Tree:\n{raw[:1500]}"

        user_message = f"""Target URL: {url}
Testing Goal: {task_goal}{snapshot_context}

Generate the complete step-by-step test execution plan as a JSON array."""

        messages = [
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        try:
            response = await self.llm.chat.completions.create(
                model=config.LLM_MODEL,
                temperature=config.LLM_TEMPERATURE,
                max_tokens=config.PLANNER_MAX_TOKENS,
                messages=messages,
            )

            raw_output = response.choices[0].message.content.strip()
            logger.debug(f"Planner raw LLM output:\n{raw_output}")

            # --- JSON extraction with prose-fallback retry ---
            # Some free/reasoning models (Nemotron, Llama) emit chain-of-thought
            # prose and place the JSON at the very end, or omit it entirely when
            # they run out of token budget.  If extraction fails, continue the
            # conversation and ask for the JSON array only.
            try:
                steps_data = self._extract_json(raw_output)
            except ValueError:
                logger.warning(
                    "Planner response contained no JSON array — "
                    "sending JSON-only follow-up to the model."
                )
                messages.append({"role": "assistant", "content": raw_output})
                messages.append({
                    "role": "user",
                    "content": (
                        "Your previous response was reasoning text, not a JSON array. "
                        "Now output ONLY the raw JSON array of TestStep objects — "
                        "no prose, no markdown, no explanation whatsoever."
                    ),
                })
                retry_response = await self.llm.chat.completions.create(
                    model=config.LLM_MODEL,
                    temperature=0.0,
                    max_tokens=config.PLANNER_MAX_TOKENS,
                    messages=messages,
                )
                raw_output = retry_response.choices[0].message.content.strip()
                logger.debug(f"Planner retry output:\n{raw_output}")
                steps_data = self._extract_json(raw_output)  # raises if still no JSON

            steps = []
            for i, step_dict in enumerate(steps_data):
                step_dict["action_type"] = step_dict.get("action_type", "navigate").lower()
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
