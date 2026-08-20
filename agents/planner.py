import json
import re
from typing import List, Dict, Any, Optional, Union
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

AUTONOMOUS EXECUTION RULES:
1. Focus ONLY on the user's primary goal. Ignore cookie popups, consent banners, or privacy overlays (the environment handles these automatically).
2. For any form field where specific data wasn't provided in the prompt, set value: null — the Executor Agent will synthesize valid mock data automatically.
3. Dynamically adapt selector matching and text assertions to the primary language of the target website (e.g., French for French sites).
4. Maintain standard JSON array structure for TestStep outputs.

IMPORTANT GUIDELINES:
- Always start with a NAVIGATE step to the target URL.
- Always end with at least one ASSERT_TEXT step to verify the outcome.
- Output ONLY the raw JSON array. No explanation, no markdown fences, no extra text.

FORM DISAMBIGUATION & AIRLINE BOOKING RULES:
1. Target the main booking card widget under the "Réservation" section, NOT the top header navigation or top bar search icon.
2. Check existing field values: If "Sélectionnez l'origine" is already pre-filled (e.g. "Casablanca, Maroc"), do NOT create a fill step to re-type it unless explicitly asked to change origin.
3. For destination selection, target the combobox/input labeled "Sélectionnez une destination".
4. For departure/return dates, target the "Dates" input picker.
5. The final search submission button on booking forms is typically "Rechercher des vols" — target this specific button inside the booking card.
6. To ensure registration/form submission succeeds, always generate steps to fill all required fields (marked with * or having labels like First Name/Prénom, Last Name/Nom) even if the goal prompt only lists a subset of fields.
7. The Keycloak registration form submit button is typically labeled 'Enregistrement' (Sign up/Register in French) — use page.get_by_role('button', name='Enregistrement') to submit the registration form.


CALENDAR & DATE PICKERS:
Date pickers are interactive widgets, not plain text inputs. To choose dates follow this exact sequence:
1. CLICK the date picker button or label (e.g. "Dates") to open the calendar dialog.
2. CLICK an available day cell or button inside the calendar dialog for the departure date.
3. CLICK a second day cell for the return date if the flow requires a round trip.
Do NOT use action_type "fill" on date labels, span elements, or any non-input date trigger — they will always raise an element-type error.

SELECTOR STYLE FOR CALENDARS:
When targeting calendar day cells, use ONLY simple selectors — never complex chained :not() CSS:
- Preferred: page.get_by_role('button', name='15') or text matching like text='15'
- Acceptable: mat-calendar button, [role='gridcell']
- FORBIDDEN: any selector containing ":not()" with arguments or chained pseudo-classes like "button:not([disabled]):not(.foo)"
  These are frequently malformed by LLMs and will cause a CSS parse crash.

DESTINATION COMBOBOX RULE (CRITICAL):
The destination field is a combobox/autocomplete widget — NOT a plain text input.
Do NOT use action_type "fill" on it. Always use this exact two-step sequence:
  Step A — action_type: "click"  → selector: page.get_by_role('combobox', name='Sélectionnez une destination')
  Step B — action_type: "click"  → selector: page.get_by_role('option', name='Paris') OR page.get_by_text('Paris, France')
Never use fill/type on a combobox — it will always raise an element-type error.

FOR FORM REGISTRATION FIELDS: When password and confirmation password fields both exist on the page, use exact IDs or names like #password / [name='password'] and #password-confirm / [name='password-confirm'] to avoid strict mode collisions.
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
