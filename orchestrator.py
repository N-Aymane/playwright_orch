import asyncio
from typing import Any
from langgraph.graph import StateGraph, END
from openai import AsyncOpenAI
from schemas import AgentState, TestStep, ActionType
from agents.planner import PlannerAgent
from agents.executor import ExecutorAgent
from agents.healer import HealerAgent
from browser_engine import PlaywrightBrowserEngine
from utils.logger import get_logger
import config

logger = get_logger("orchestrator")


def create_orchestrator_graph(browser_engine: PlaywrightBrowserEngine, llm_client: AsyncOpenAI):
    """
    Builds and compiles the LangGraph state machine that routes execution between the
    Planner, Executor, and Healer agents.
    """
    planner = PlannerAgent(llm_client)
    executor = ExecutorAgent(llm_client)
    healer = HealerAgent(llm_client)

    # -------------------------------------------------------------------
    # NODE: plan_node
    # Runs the Planner Agent to generate all test steps from the goal + URL.
    # -------------------------------------------------------------------
    async def plan_node(state: AgentState) -> AgentState:
        logger.info("[ORCHESTRATOR] >> Entering PLAN node")

        # First navigate to the page to grab an initial accessibility snapshot
        logger.info(f"Pre-navigating to {state['url']} to snapshot page structure...")
        await browser_engine.navigate(state["url"])
        snapshot = await browser_engine.get_accessibility_tree()

        steps = await planner.generate_plan(
            url=state["url"],
            task_goal=state["task_goal"],
            accessibility_snapshot=snapshot
        )

        return {
            **state,
            "steps": steps,
            "accessibility_snapshot": snapshot,
            "current_step_index": 0,
        }

    # -------------------------------------------------------------------
    # NODE: execute_node
    # Executes the current test step. Generates form data if needed.
    # -------------------------------------------------------------------
    async def execute_node(state: AgentState) -> AgentState:
        current_index = state["current_step_index"]
        steps = list(state["steps"])  # Make mutable copy
        current_step = steps[current_index]

        logger.info(
            f"[ORCHESTRATOR] >> Entering EXECUTE node "
            f"[Step {current_step.step_id}/{len(steps)}]: {current_step.description}"
        )

        # Synthesize form data for fill or select actions with no value
        if current_step.action_type in (ActionType.FILL, ActionType.SELECT) and not current_step.value:
            logger.info(f"No value set for step {current_step.step_id}. Invoking ExecutorAgent...")
            generated_value = await executor.generate_form_data(
                step=current_step,
                accessibility_snapshot=state.get("accessibility_snapshot")
            )
            # Ensure we never pass an empty string to Playwright
            if not generated_value or not generated_value.strip():
                logger.warning(
                    f"ExecutorAgent returned empty value for step {current_step.step_id}. "
                    "Using fallback."
                )
                generated_value = executor._fallback_value(current_step)
            current_step = current_step.model_copy(update={"value": generated_value})
            steps[current_index] = current_step

        # Execute the step
        success = await browser_engine.execute_action(current_step)

        # Refresh accessibility snapshot after each action
        snapshot = await browser_engine.get_accessibility_tree()

        if success:
            current_step = current_step.model_copy(update={"status": "passed"})
            steps[current_index] = current_step
            next_index = current_index + 1
            is_complete = next_index >= len(steps)

            logger.info(f"Step {current_step.step_id} PASSED")

            return {
                **state,
                "steps": steps,
                "current_step_index": next_index,
                "is_complete": is_complete,
                "accessibility_snapshot": snapshot,
                "last_error": None,
                "console_logs": browser_engine.console_logs[:],
                "failed_network_requests": browser_engine.network_errors[:],
            }
        else:
            current_step = current_step.model_copy(update={"status": "failed"})
            steps[current_index] = current_step

            logger.warning(f"Step {current_step.step_id} FAILED - Error: {current_step.error_message}")

            return {
                **state,
                "steps": steps,
                "current_step_index": current_index,
                "is_complete": False,
                "accessibility_snapshot": snapshot,
                "last_error": current_step.error_message,
                "console_logs": browser_engine.console_logs[:],
                "failed_network_requests": browser_engine.network_errors[:],
            }

    # -------------------------------------------------------------------
    # NODE: heal_node
    # Runs the Healer Agent to propose an updated selector for a failed step.
    # -------------------------------------------------------------------
    async def heal_node(state: AgentState) -> AgentState:
        current_index = state["current_step_index"]
        steps = list(state["steps"])
        failed_step = steps[current_index]

        logger.info(f"[ORCHESTRATOR] >> Entering HEAL node for step {failed_step.step_id}")

        # Max retries exceeded → mark as permanently failed and abort
        if failed_step.retry_count >= failed_step.max_retries:
            logger.error(
                f"Step {failed_step.step_id} exceeded max retries "
                f"({failed_step.max_retries}). Marking test as FAILED."
            )
            failed_step = failed_step.model_copy(update={"status": "failed"})
            steps[current_index] = failed_step
            return {
                **state,
                "steps": steps,
                "is_complete": True,
                "test_passed": False,
            }

        # Ask HealerAgent for a corrected selector
        new_selector = await healer.heal_selector(
            failed_step=failed_step,
            snapshot=state.get("accessibility_snapshot"),
            error=state.get("last_error")
        )

        if new_selector:
            logger.info(
                f"HealerAgent provided new selector for step {failed_step.step_id}: '{new_selector}'"
            )
            healed_step = failed_step.model_copy(update={
                "selector": new_selector,
                "retry_count": failed_step.retry_count + 1,
                "status": "healed",
                "error_message": None,
            })
            steps[current_index] = healed_step

            return {
                **state,
                "steps": steps,
                "is_complete": False,
                "last_error": None,
            }
        else:
            logger.error(f"HealerAgent could not suggest a fix for step {failed_step.step_id}. Aborting.")
            failed_step = failed_step.model_copy(update={"status": "failed"})
            steps[current_index] = failed_step
            return {
                **state,
                "steps": steps,
                "is_complete": True,
                "test_passed": False,
            }

    # -------------------------------------------------------------------
    # CONDITIONAL ROUTER: Determines next node after execute_node
    # -------------------------------------------------------------------
    def route_after_execution(state: AgentState) -> str:
        if state.get("is_complete"):
            logger.info("[ORCHESTRATOR] Execution complete. Routing to END.")
            return END

        current_index = state["current_step_index"]
        steps = state["steps"]

        # Check if we are still on the same step (i.e. it failed)
        if current_index < len(steps):
            current_step = steps[current_index]
            if current_step.status == "failed":
                logger.info(f"[ORCHESTRATOR] Step {current_step.step_id} failed. Routing to HEAL node.")
                return "heal"

        return "execute"

    # -------------------------------------------------------------------
    # CONDITIONAL ROUTER: Determines next node after heal_node
    # -------------------------------------------------------------------
    def route_after_healing(state: AgentState) -> str:
        if state.get("is_complete"):
            logger.info("[ORCHESTRATOR] Healing complete or aborted. Routing to END.")
            return END
        return "execute"

    # -------------------------------------------------------------------
    # BUILD THE GRAPH
    # -------------------------------------------------------------------
    graph = StateGraph(AgentState)

    graph.add_node("plan", plan_node)
    graph.add_node("execute", execute_node)
    graph.add_node("heal", heal_node)

    graph.set_entry_point("plan")
    graph.add_edge("plan", "execute")

    graph.add_conditional_edges(
        "execute",
        route_after_execution,
        {
            "execute": "execute",
            "heal": "heal",
            END: END,
        }
    )

    graph.add_conditional_edges(
        "heal",
        route_after_healing,
        {
            "execute": "execute",
            END: END,
        }
    )

    compiled = graph.compile()
    logger.info("Orchestrator graph compiled successfully.")
    return compiled
