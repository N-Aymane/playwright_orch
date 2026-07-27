import re
from typing import Dict, Any, Optional
from openai import AsyncOpenAI
from schemas import TestStep
from utils.logger import get_logger
from utils.dom_parser import format_accessibility_tree
import config

logger = get_logger("executor_agent")

EXECUTOR_FORM_PROMPT = """You are an intelligent form data synthesizer for automated web testing.

You will be given the details of a single form field (selector, type attributes, labels, placeholder text, and DOM context).
Your task is to generate a single, realistic, syntactically valid input value for that field.

Rules:
- If the field is type="email" or has 'email' in its name/placeholder: produce a valid mock email (e.g. test_user_42@devmail.io)
- If the field is type="password" or has 'password' in its name/placeholder: produce a secure 12-character password mixing upper, lower, digits, and symbols (e.g. Tr0ub4dor&3xP)
- If the field is type="tel" or has 'phone'/'tel' in its name/placeholder: produce a valid 10-digit US phone number (e.g. 555-867-5309)
- If the field has 'first' and 'name' in its attributes: produce a realistic first name (e.g. Jordan)
- If the field has 'last' and 'name' in its attributes: produce a realistic last name (e.g. Mitchell)
- If the field has 'name' in its name/placeholder (not first/last): produce a realistic full name (e.g. Alex Rivera)
- If the field is type="date": produce a valid date in YYYY-MM-DD format (e.g. 1990-06-15)
- If the field is type="number": produce a sensible numeric value (e.g. 25)
- If the field is a general text field: produce a short, contextually appropriate sentence or word

Output ONLY the raw value string. No quotes. No explanation. No extra characters.
"""

class ExecutorAgent:
    def __init__(self, llm_client: AsyncOpenAI):
        self.llm = llm_client
        logger.info("ExecutorAgent initialized.")

    async def generate_form_data(
        self,
        step: TestStep,
        accessibility_snapshot: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Calls the LLM to synthesize contextually appropriate mock data for a form fill step.
        Returns the generated value string.
        """
        logger.info(f"Generating form data for step {step.step_id}: selector='{step.selector}'")

        # Build context from accessibility snapshot if available
        snapshot_context = ""
        if accessibility_snapshot:
            snapshot_context = f"\nPage Accessibility Context:\n{format_accessibility_tree(accessibility_snapshot)}"

        user_message = f"""Form Field Details:
Selector: {step.selector}
Selector Type: {step.selector_type}
Step Description: {step.description}
{snapshot_context}

Generate the input value for this field."""

        try:
            response = await self.llm.chat.completions.create(
                model=config.LLM_MODEL,
                temperature=0.3,  # Slight creativity for realistic mock data
                max_tokens=config.EXECUTOR_MAX_TOKENS,
                messages=[
                    {"role": "system", "content": EXECUTOR_FORM_PROMPT},
                    {"role": "user", "content": user_message}
                ]
            )

            generated_value = response.choices[0].message.content.strip()
            # Strip any accidental surrounding quotes
            generated_value = generated_value.strip('"').strip("'")
            logger.info(f"Generated form value: '{generated_value}' for step {step.step_id}")
            return generated_value

        except Exception as e:
            logger.error(f"ExecutorAgent failed to generate form data: {e}")
            # Fallback to sensible defaults based on description keywords
            return self._fallback_value(step)

    def _fallback_value(self, step: TestStep) -> str:
        """
        Provides a simple keyword-based fallback when LLM call fails.
        """
        desc_lower = step.description.lower()
        sel_lower = (step.selector or "").lower()
        context = desc_lower + " " + sel_lower

        if "email" in context:
            return "test_user@example.com"
        elif "password" in context:
            return "SecureP@ss123!"
        elif "phone" in context or "tel" in context:
            return "555-123-4567"
        elif "first" in context and "name" in context:
            return "Alex"
        elif "last" in context and "name" in context:
            return "Johnson"
        elif "name" in context:
            return "Alex Johnson"
        elif "date" in context:
            return "1990-01-01"
        elif "number" in context or "age" in context:
            return "28"
        else:
            return "Test Input Value"
