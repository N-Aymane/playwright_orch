#!/usr/bin/env python3
"""
main.py — CLI entry point for the Multi-Agent Autonomous Web Testing & Self-Healing Framework.

Usage:
    python main.py --url "https://example.com/register" --goal "Test user registration form"

Options:
    --url       Target URL to test (required)
    --goal      Plain-English description of the testing goal (required)
    --headless  Run browser in headless mode (default: True)
    --model     LLM model name to use (default: from config.py)
    --trace     Output path for Playwright trace file (default: trace.zip)
    --report    Output path for HTML report (default: report.html)
    --json-report  Output path for JSON report (default: report.json)
"""

import asyncio
import argparse
import sys
import os
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from openai import AsyncOpenAI

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from browser_engine import PlaywrightBrowserEngine
from orchestrator import create_orchestrator_graph
from utils.logger import get_logger
from utils.reporter import generate_html_report, save_json_report

console = Console()
logger = get_logger("main")


async def run_test(
    url: str,
    goal: str,
    trace_path: str,
    report_path: str,
    json_report_path: str
):
    """
    Main async entry point that initializes all components, runs the agent graph,
    and generates all reports.
    """
    console.print(Panel(
        Text.from_markup(
            f"[bold cyan]Autonomous Web Testing Framework[/bold cyan]\n\n"
            f"[white]Target URL:[/white] [yellow]{url}[/yellow]\n"
            f"[white]Goal:[/white]       [green]{goal}[/green]\n"
            f"[white]LLM Model:[/white]  [blue]{config.LLM_MODEL}[/blue]\n"
            f"[white]Headless:[/white]   [magenta]{config.HEADLESS}[/magenta]"
        ),
        title="[bold]Test Run Starting[/bold]",
        border_style="cyan"
    ))

    # --- Validate API Key ---
    if not config.OPENAI_API_KEY:
        console.print("[bold red]ERROR: OPENAI_API_KEY is not set.[/bold red]")
        console.print("Set it in a [yellow].env[/yellow] file or as an environment variable:")
        console.print("  [dim]OPENAI_API_KEY=sk-...[/dim]")
        sys.exit(1)

    # --- Initialize LLM Client ---
    llm_client = AsyncOpenAI(
        api_key=config.OPENAI_API_KEY,
        base_url=config.OPENAI_API_BASE
    )

    # --- Initialize Browser Engine ---
    browser_engine = PlaywrightBrowserEngine()
    await browser_engine.initialize()

    # --- Build Initial Agent State ---
    initial_state = {
        "url": url,
        "task_goal": goal,
        "current_step_index": 0,
        "steps": [],
        "accessibility_snapshot": None,
        "last_error": None,
        "console_logs": [],
        "failed_network_requests": [],
        "is_complete": False,
        "test_passed": True,
    }

    final_state = None
    try:
        # --- Build & Run the Orchestrator Graph ---
        graph = create_orchestrator_graph(browser_engine, llm_client)
        logger.info("Starting agent execution graph...")
        console.print("\n[bold]> Launching Multi-Agent Execution Graph...[/bold]\n")

        async for state_update in graph.astream(initial_state):
            # Log incremental state updates from graph nodes
            for node_name, node_state in state_update.items():
                if isinstance(node_state, dict):
                    step_index = node_state.get("current_step_index", 0)
                    steps = node_state.get("steps", [])
                    step_count = len(steps)
                    if steps and step_index > 0:
                        last_executed = steps[step_index - 1] if step_index > 0 else None
                        if last_executed:
                            status_icon = {
                                "passed": "[PASS]",
                                "failed": "[FAIL]",
                                "healed": "[HEAL]",
                                "pending": "[PEND]"
                            }.get(last_executed.status, "-")
                            console.print(
                                f"  {status_icon} [{node_name.upper()}] "
                                f"Step {last_executed.step_id}/{step_count}: "
                                f"{last_executed.description[:70]}"
                            )
                final_state = node_state

    except KeyboardInterrupt:
         console.print("\n[yellow]Test run interrupted by user.[/yellow]")
    except Exception as e:
         logger.error(f"Fatal error during graph execution: {e}")
         console.print(f"\n[bold red]Fatal error: {e}[/bold red]")
    finally:
        # --- Always stop browser and save trace ---
        await browser_engine.stop(trace_path=trace_path)

    # --- Collect final state ---
    if final_state is None:
        console.print("[bold red]No final state captured. Check logs for errors.[/bold red]")
        return

    # Handle both dict and model outputs from LangGraph
    if isinstance(final_state, dict):
        steps = final_state.get("steps", [])
        console_logs = final_state.get("console_logs", [])
        network_errors = final_state.get("failed_network_requests", [])
        test_passed = final_state.get("test_passed", False)
    else:
        steps = getattr(final_state, "steps", [])
        console_logs = getattr(final_state, "console_logs", [])
        network_errors = getattr(final_state, "failed_network_requests", [])
        test_passed = getattr(final_state, "test_passed", False)

    # --- Print Summary ---
    total = len(steps)
    passed = sum(1 for s in steps if s.status == "passed")
    healed = sum(1 for s in steps if s.status == "healed")
    failed = sum(1 for s in steps if s.status == "failed")

    result_color = "green" if test_passed else "red"
    result_label = "PASSED" if test_passed else "FAILED"

    console.print(Panel(
        Text.from_markup(
            f"[bold {result_color}]{result_label}[/bold {result_color}]\n\n"
            f"[white]Total Steps: [cyan]{total}[/cyan]   "
            f"Passed: [green]{passed}[/green]   "
            f"Healed: [magenta]{healed}[/magenta]   "
            f"Failed: [red]{failed}[/red][/white]\n\n"
            f"[white]Trace saved to:[/white] [yellow]{trace_path}[/yellow]\n"
            f"[white]HTML Report:[/white]   [yellow]{report_path}[/yellow]\n"
            f"[white]JSON Report:[/white]   [yellow]{json_report_path}[/yellow]"
        ),
        title="[bold]Test Run Complete[/bold]",
        border_style=result_color
    ))

    # --- Generate Reports ---
    if steps:
        generate_html_report(
            url=url,
            task_goal=goal,
            steps=steps,
            console_logs=console_logs,
            network_errors=network_errors,
            test_passed=test_passed,
            trace_path=trace_path,
            output_path=report_path
        )
        save_json_report(
            url=url,
            task_goal=goal,
            steps=steps,
            console_logs=console_logs,
            network_errors=network_errors,
            test_passed=test_passed,
            trace_path=trace_path,
            output_path=json_report_path
        )
        console.print(f"\n[bold green]Reports generated successfully![/bold green]")
        console.print(f"  -> Open [link=file://{os.path.abspath(report_path)}]{report_path}[/link] in your browser to view the full test report.")
        console.print(f"  -> Load [bold]{trace_path}[/bold] at [link=https://trace.playwright.dev]trace.playwright.dev[/link] to inspect execution traces.")
    else:
        console.print("[yellow]No steps were executed — no reports generated.[/yellow]")


def main():
    parser = argparse.ArgumentParser(
        description="🤖 Multi-Agent Autonomous Web Testing & Self-Healing Framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --url "https://demoqa.com/automation-practice-form" --goal "Fill out and submit the practice automation form"
  python main.py --url "https://example.com/register" --goal "Test user registration with valid inputs" --headless false
        """
    )
    parser.add_argument("--url", required=True, help="Target URL to test")
    parser.add_argument("--goal", required=True, help="Plain-English testing goal")
    parser.add_argument("--headless", default=None, help="Run headless (true/false)")
    parser.add_argument("--model", default=None, help="Override LLM model (e.g. gpt-4o)")
    parser.add_argument("--trace", default=config.TRACE_PATH, help="Playwright trace output path")
    parser.add_argument("--report", default=config.REPORT_PATH, help="HTML report output path")
    parser.add_argument("--json-report", default="report.json", help="JSON report output path")

    args = parser.parse_args()

    # Apply CLI overrides to config
    if args.headless is not None:
        config.HEADLESS = args.headless.lower() == "true"
    if args.model is not None:
        config.LLM_MODEL = args.model

    asyncio.run(run_test(
        url=args.url,
        goal=args.goal,
        trace_path=args.trace,
        report_path=args.report,
        json_report_path=args.json_report
    ))


if __name__ == "__main__":
    main()
