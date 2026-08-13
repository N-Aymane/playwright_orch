import re
from typing import Dict, Any, Optional, Union
from openai import AsyncOpenAI
from schemas import TestStep
from utils.logger import get_logger
from utils.dom_parser import format_accessibility_tree
import config

logger = get_logger("executor_agent")

EXECUTOR_FORM_PROMPT = """You are an intelligent form data synthesizer for automated web testing.

You will be given the details of a single form field (description and DOM/accessibility context).
Your task is to generate a single, realistic, syntactically valid input or selection value for that field.

Contextual Rules for LLM Synthesis:
- Date fields -> Output valid future dates (e.g., departure next month 20/09/2026).
- Email fields -> test.user@example.com
- Phone -> Valid international format +212600000000
- Names / Text -> Standard realistic values matching the site language.
- Select/Dropdown fields -> Output a valid option matching one of the options described in the context.

Output ONLY the raw value string. No quotes. No explanation. No extra characters.
"""

class ExecutorAgent:
    def __init__(self, llm_client: AsyncOpenAI):
        self.llm = llm_client
        logger.info("ExecutorAgent initialized.")

    async def synthesize_form_value(self, field_description: str, element_context: str) -> str:
        """
        Calls the LLM to generate a valid form/select value based on context and description.
        """
        logger.info(f"Synthesizing form value for: {field_description}")
        user_message = f"""Field Description: {field_description}
Element Context: {element_context}

Generate the input/selection value for this field."""

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
        logger.info(f"Synthesized value: '{generated_value}'")
        return generated_value

    async def generate_form_data(
        self,
        step: TestStep,
        accessibility_snapshot: Optional[Union[str, Dict[str, Any]]] = None
    ) -> str:
        """
        Calls the LLM to synthesize contextually appropriate mock data for a form fill or select step.
        Returns the generated value string.
        """
        logger.info(f"Generating form data for step {step.step_id}: selector='{step.selector}'")

        # Build context from accessibility snapshot if available
        snapshot_context = ""
        if accessibility_snapshot:
            snapshot_context = format_accessibility_tree(accessibility_snapshot)

        field_description = f"Step ID: {step.step_id}, Selector: {step.selector}, Description: {step.description}, Action: {step.action_type.value}"

        try:
            return await self.synthesize_form_value(field_description, snapshot_context)
        except Exception as e:
            logger.error(f"ExecutorAgent failed to generate form data: {e}")
            return self._fallback_value(step)

    def _fallback_value(self, step: TestStep) -> str:
        """
        Provides a simple keyword-based fallback when LLM call fails.
        """
        desc_lower = step.description.lower()
        sel_lower = (step.selector or "").lower()
        context = desc_lower + " " + sel_lower

        if "email" in context:
            return "test.user@example.com"
        elif "password" in context:
            return "SecureP@ss123!"
        elif "phone" in context or "tel" in context:
            return "+212600000000"
        elif "first" in context and "name" in context:
            return "Alex"
        elif "last" in context and "name" in context:
            return "Johnson"
        elif "name" in context:
            return "Alex Johnson"
        elif "date" in context:
            return "20/09/2026"
        elif "number" in context or "age" in context:
            return "28"
        else:
            return "Test Input Value"
