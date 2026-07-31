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
        """
        logger.info(
            f"HealerAgent attempting to heal step {failed_step.step_id} "
            f"(Action: {failed_step.action_type}, Failed Selector: '{failed_step.selector}')"
        )

        # Format the accessibility tree for the prompt
        snapshot_text = format_accessibility_tree(snapshot) if snapshot else "Accessibility snapshot unavailable."

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

        try:
            response = await self.llm.chat.completions.create(
                model=config.LLM_MODEL,
                temperature=0.0,  # Deterministic for locator repair
                max_tokens=config.HEALER_MAX_TOKENS,
                messages=[
                    {"role": "system", "content": HEALER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message}
                ]
            )

            healed_selector = response.choices[0].message.content.strip()
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
