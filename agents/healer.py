import re
from typing import Dict, Any, Optional, Union
from openai import AsyncOpenAI
from schemas import TestStep
from utils.logger import get_logger
from utils.dom_parser import format_accessibility_tree
import config

logger = get_logger("healer_agent")

HEALER_SYSTEM_PROMPT = """You are an expert Playwright Self-Healing Agent specializing in robust UI element location.

A test step has failed because a browser element could not be located. Your job is to analyze the failure context and the current page state, then propose an updated, resilient Playwright locator to retry the action.

DISAMBIGUATION & AIRLINE BOOKING RULES:
1. Target the main booking card widget under the "Réservation" section, NOT the top header navigation or top bar search icon.
2. Check existing field values: If "Sélectionnez l'origine" is already pre-filled (e.g. "Casablanca, Maroc"), do NOT create a fill step to re-type it unless explicitly asked to change origin.
3. For destination selection, target the combobox/input labeled "Sélectionnez une destination".
4. For departure/return dates, target the "Dates" input picker.
5. The final search submission button on booking forms is typically "Rechercher des vols" — target this specific button inside the booking card.
6. The Keycloak registration form submit button is typically labeled 'Enregistrement' (Sign up/Register in French) — use page.get_by_role('button', name='Enregistrement') to submit the registration form.

DESTINATION COMBOBOX RULE (CRITICAL):
The destination field is a combobox/autocomplete widget — NOT a plain text input.
Do NOT use action_type "fill" on it. Always use this exact two-step sequence:
  Step A — action_type: "click"  → selector: page.get_by_role('combobox', name='Sélectionnez une destination')
  Step B — action_type: "click"  → selector: page.get_by_role('option', name='Paris') OR page.get_by_text('Paris, France')
Never use fill/type on a combobox. It will always fail with an element-type error.

Analysis Process:
1. Examine the failed selector and understand what UI element it was targeting.
2. Study the current accessibility tree carefully to find the most likely matching or equivalent element.
3. Produce a corrected selector using this priority order:
   a. Python Playwright role-based: page.get_by_role('button', name='Submit')
   b. Python Playwright label/placeholder: page.get_by_label('Email') or page.get_by_placeholder('Enter email')
   c. Python Playwright text: page.get_by_text('Sign In')
   d. Semantic CSS using attributes: input[type="email"], [name="username"], #email-field
   e. Avoid: long XPath chains, positional selectors (nth-child), volatile generated class names

Output ONLY the corrected selector string. Nothing else. No explanation. No quotes around it unless part of a Python expression.

Examples of good outputs:
  page.get_by_role('button', name='Create Account')
  page.get_by_placeholder('Email address')
  input[name="email"]
  #signup-form input[type="password"]
"""

def extract_clean_selector(raw_text: str) -> str:
    raw_text = raw_text.strip()
    
    # 1. Match Playwright locator expressions: page.get_by_...(...) or page.locator(...)
    match = re.search(r"(page\.(?:get_by_[a-z]+|locator)\([^)]+\))", raw_text)
    if match:
        return match.group(1)
        
    # 2. Match CSS / ID / Attribute selectors: #id, [name='...'], input[...], etc.
    match = re.search(r"([#\.\[a-zA-Z0-9_-]+(?:\[[^\]]+\])?)", raw_text)
    if match:
        return match.group(1)
        
    # Fallback to the last line of output if it looks like code
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    return lines[-1] if lines else raw_text

class HealerAgent:
    def __init__(self, llm_client: AsyncOpenAI):
        self.llm = llm_client
        logger.info("HealerAgent initialized.")

    async def heal_selector(
        self,
        failed_step: TestStep,
        snapshot: Optional[Union[str, Dict[str, Any]]],
        error: Optional[str]
    ) -> Optional[str]:
        """
        Analyzes a failed TestStep and the current accessibility tree to propose a healed selector.
        Returns the new selector string, or None if healing is not possible.
        If the model returns prose instead of a bare selector (common with reasoning-style
        free models), a follow-up message requests the selector only.
        """
        logger.info(
            f"HealerAgent attempting to heal step {failed_step.step_id} "
            f"(Action: {failed_step.action_type}, Failed Selector: '{failed_step.selector}')"
        )

        # Format the accessibility tree for the prompt and hard-cap to ~1,000 tokens
        # to stay within free/tiered LLM key limits and avoid 402 errors.
        raw_snapshot = format_accessibility_tree(snapshot) if snapshot else "Accessibility snapshot unavailable."
        snapshot_text = raw_snapshot[:2000]

        user_message = f"""Step Failure Report:
Step ID: {failed_step.step_id}
Description: {failed_step.description}
Action Type: {failed_step.action_type.value}
Failed Selector: {failed_step.selector}
Selector Type: {failed_step.selector_type}
Error Message: {error or 'Unknown error — element not found or timeout'}
Retry Attempt: {failed_step.retry_count + 1} of {failed_step.max_retries}

Current Page Accessibility Tree:
{snapshot_text}

Propose the corrected Playwright selector to locate this element."""

        messages = [
            {"role": "system", "content": HEALER_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        def _looks_like_prose(text: str) -> bool:
            """Heuristic: a valid selector is short and single-line; prose is long and multi-sentence."""
            return len(text) > 200 or text.count(".") > 3 or "\n" in text

        try:
            response = await self.llm.chat.completions.create(
                model=config.LLM_MODEL,
                temperature=0.0,  # Deterministic for locator repair
                max_tokens=config.HEALER_MAX_TOKENS,
                messages=messages,
            )

            healed_selector = response.choices[0].message.content.strip()

            # --- Prose-fallback retry ---
            # Reasoning-style free models (Nemotron, Llama) often return an
            # explanation paragraph instead of the bare selector string.
            # Detect this and ask for the selector only.
            if _looks_like_prose(healed_selector):
                logger.warning(
                    f"HealerAgent step {failed_step.step_id}: response looks like prose — "
                    "sending selector-only follow-up."
                )
                messages.append({"role": "assistant", "content": healed_selector})
                messages.append({
                    "role": "user",
                    "content": (
                        "Your response was an explanation, not a selector. "
                        "Output ONLY the single corrected Playwright selector string — "
                        "no prose, no explanation, no quotes around it."
                    ),
                })
                retry_resp = await self.llm.chat.completions.create(
                    model=config.LLM_MODEL,
                    temperature=0.0,
                    max_tokens=config.HEALER_MAX_TOKENS,
                    messages=messages,
                )
                healed_selector = retry_resp.choices[0].message.content.strip()

            healed_selector = extract_clean_selector(healed_selector)

            # Strip any accidental surrounding quotes
            healed_selector = healed_selector.strip('"').strip("'")

            if not healed_selector:
                logger.warning(f"HealerAgent returned empty selector for step {failed_step.step_id}.")
                return None

            logger.info(f"HealerAgent proposed new selector: '{healed_selector}'")
            return healed_selector

        except Exception as e:
            logger.error(f"HealerAgent LLM call failed: {e}")
            return None

    async def analyze_console_errors(self, console_logs: list[str], failed_step: TestStep) -> str:
        """
        Analyzes intercepted console errors to provide a diagnosis alongside the step failure.
        Used to enrich the healing context and reporting.
        """
        if not console_logs:
            return ""

        errors_text = "\n".join(console_logs[-10:])  # Last 10 relevant logs
        prompt = f"""The following console errors were intercepted during a test run. The current step that failed was:
Step: {failed_step.description} (Action: {failed_step.action_type.value})

Console Errors:
{errors_text}

In 1-2 sentences, explain how these console errors might relate to the step failure. 
If unrelated, say "Console errors appear unrelated to step failure."
"""
        try:
            response = await self.llm.chat.completions.create(
                model=config.LLM_MODEL,
                temperature=0.0,
                max_tokens=config.CONSOLE_ANALYSIS_MAX_TOKENS,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            return response.choices[0].message.content.strip()
        except Exception:
            return ""
