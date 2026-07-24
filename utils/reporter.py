import json
import os
from datetime import datetime
from typing import List, Dict, Any
from schemas import TestStep

def generate_html_report(
    url: str,
    task_goal: str,
    steps: List[TestStep],
    console_logs: List[str],
    network_errors: List[str],
    test_passed: bool,
    trace_path: str,
    output_path: str
):
    """
    Generates a premium, responsive HTML report showcasing the results of the autonomous test.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    total_steps = len(steps)
    passed_steps = sum(1 for s in steps if s.status == "passed")
    healed_steps = sum(1 for s in steps if s.status == "healed")
    failed_steps = sum(1 for s in steps if s.status == "failed")
    pending_steps = sum(1 for s in steps if s.status == "pending")

    status_class = "status-passed" if test_passed else "status-failed"
    status_text = "PASSED" if test_passed else "FAILED"
    
    # Generate rows for steps
    step_rows_html = ""
    for step in steps:
        badge_class = f"badge-{step.status}"
        error_html = f"<div class='step-error'><strong>Error:</strong> {step.error_message}</div>" if step.error_message else ""
        selector_html = f"<code class='step-selector'>{step.selector}</code>" if step.selector else "<span class='text-muted'>N/A</span>"
        val_html = f"<code class='step-value'>{step.value}</code>" if step.value else "<span class='text-muted'>N/A</span>"
        
        step_rows_html += f"""
        <div class="step-card">
            <div class="step-header">
                <span class="step-title">Step {step.step_id}: {step.description}</span>
                <span class="badge {badge_class}">{step.status.upper()}</span>
            </div>
            <div class="step-body">
                <div class="step-meta">
                    <div><strong>Action Type:</strong> <code>{step.action_type.value}</code></div>
                    <div><strong>Selector Type:</strong> <code>{step.selector_type}</code></div>
                    <div><strong>Retries:</strong> {step.retry_count} / {step.max_retries}</div>
                </div>
                <div class="step-details">
                    <div><strong>Selector:</strong> {selector_html}</div>
                    <div><strong>Value:</strong> {val_html}</div>
                </div>
                {error_html}
            </div>
        </div>
        """

    # Console logs HTML
    console_logs_html = ""
    if console_logs:
        for log in console_logs:
            # Highlight errors
            log_class = "log-error" if "[error]" in log.lower() else "log-warning"
            console_logs_html += f"<div class='log-item {log_class}'>{log}</div>"
    else:
        console_logs_html = "<div class='text-muted'>No console errors or warnings intercepted.</div>"

    # Network errors HTML
    network_errors_html = ""
    if network_errors:
        for err in network_errors:
            network_errors_html += f"<div class='log-item log-error'>{err}</div>"
    else:
        network_errors_html = "<div class='text-muted'>No network errors (status >= 400) intercepted.</div>"

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Autonomous Web Testing & Self-Healing Report</title>
    <style>
        :root {{
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --text-color: #f8fafc;
            --text-muted: #94a3b8;
            --primary: #6366f1;
            --success: #10b981;
            --danger: #ef4444;
            --warning: #f59e0b;
            --healed: #8b5cf6;
            --border-color: #334155;
        }}

        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            margin: 0;
            padding: 20px 40px;
            line-height: 1.6;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}

        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 20px;
            margin-bottom: 30px;
        }}

        h1 {{
            margin: 0;
            font-size: 2.2rem;
            font-weight: 700;
            background: linear-gradient(to right, #818cf8, #a78bfa);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}

        .report-status-badge {{
            padding: 8px 16px;
            border-radius: 9999px;
            font-weight: bold;
            font-size: 1rem;
            letter-spacing: 0.05em;
        }}

        .status-passed {{
            background-color: rgba(16, 185, 129, 0.2);
            color: var(--success);
            border: 1px solid var(--success);
        }}

        .status-failed {{
            background-color: rgba(239, 68, 68, 0.2);
            color: var(--danger);
            border: 1px solid var(--danger);
        }}

        /* Summary Cards */
        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }}

        .summary-card {{
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px;
            text-align: center;
        }}

        .summary-card h3 {{
            margin: 0 0 10px 0;
            color: var(--text-muted);
            font-size: 0.9rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}

        .summary-value {{
            font-size: 1.8rem;
            font-weight: 700;
        }}

        .summary-value.passed {{ color: var(--success); }}
        .summary-value.healed {{ color: var(--healed); }}
        .summary-value.failed {{ color: var(--danger); }}
        .summary-value.total {{ color: var(--primary); }}

        /* Main Sections */
        .section-title {{
            font-size: 1.5rem;
            margin: 0 0 20px 0;
            border-left: 4px solid var(--primary);
            padding-left: 12px;
            font-weight: 600;
        }}

        .meta-info-card {{
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 45px;
        }}

        .meta-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 15px;
        }}

        .meta-item strong {{
            color: var(--text-muted);
            display: block;
            margin-bottom: 4px;
        }}

        /* Steps list */
        .steps-container {{
            margin-bottom: 45px;
        }}

        .step-card {{
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            margin-bottom: 16px;
            overflow: hidden;
            transition: transform 0.2s, border-color 0.2s;
        }}

        .step-card:hover {{
            transform: translateY(-2px);
            border-color: var(--primary);
        }}

        .step-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            background-color: rgba(255, 255, 255, 0.02);
            padding: 16px 20px;
            border-bottom: 1px solid var(--border-color);
        }}

        .step-title {{
            font-weight: 600;
            font-size: 1.1rem;
        }}

        .badge {{
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 700;
            letter-spacing: 0.05em;
        }}

        .badge-passed {{ background-color: var(--success); color: #fff; }}
        .badge-failed {{ background-color: var(--danger); color: #fff; }}
        .badge-healed {{ background-color: var(--healed); color: #fff; }}
        .badge-pending {{ background-color: var(--text-muted); color: #000; }}

        .step-body {{
            padding: 20px;
        }}

        .step-meta {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 15px;
            margin-bottom: 15px;
            font-size: 0.9rem;
            color: var(--text-muted);
        }}

        .step-meta code {{
            color: var(--text-color);
            background-color: rgba(255, 255, 255, 0.05);
            padding: 2px 6px;
            border-radius: 4px;
        }}

        .step-details {{
            display: flex;
            flex-direction: column;
            gap: 8px;
            font-size: 0.95rem;
            background-color: rgba(0, 0, 0, 0.15);
            padding: 12px 16px;
            border-radius: 6px;
        }}

        .step-selector, .step-value {{
            color: #f43f5e;
            word-break: break-all;
        }}

        .step-error {{
            margin-top: 15px;
            background-color: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.2);
            color: #fda4af;
            padding: 12px 16px;
            border-radius: 6px;
            font-size: 0.9rem;
        }}

        /* Logs console */
        .logs-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }}

        .logs-panel {{
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px;
            max-height: 400px;
            overflow-y: auto;
        }}

        .log-item {{
            font-family: 'Courier New', Courier, monospace;
            font-size: 0.85rem;
            padding: 8px 12px;
            border-radius: 4px;
            margin-bottom: 8px;
            background-color: rgba(0, 0, 0, 0.2);
            word-break: break-all;
        }}

        .log-error {{
            color: #fecdd3;
            border-left: 3px solid var(--danger);
        }}

        .log-warning {{
            color: #fef3c7;
            border-left: 3px solid var(--warning);
        }}

        .text-muted {{
            color: var(--text-muted);
            font-style: italic;
        }}

        .trace-btn-container {{
            margin-top: 30px;
            text-align: center;
        }}

        .btn {{
            display: inline-block;
            background-color: var(--primary);
            color: white;
            padding: 12px 24px;
            border-radius: 6px;
            text-decoration: none;
            font-weight: 600;
            transition: background-color 0.2s;
            border: none;
            cursor: pointer;
        }}

        .btn:hover {{
            background-color: #4f46e5;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <h1>Self-Healing Test Run</h1>
                <p style="margin: 5px 0 0 0; color: var(--text-muted);">Executed on {now}</p>
            </div>
            <span class="report-status-badge {status_class}">{status_text}</span>
        </header>

        <!-- Metrics -->
        <div class="summary-grid">
            <div class="summary-card">
                <h3>Total Steps</h3>
                <div class="summary-value total">{total_steps}</div>
            </div>
            <div class="summary-card">
                <h3>Passed</h3>
                <div class="summary-value passed">{passed_steps}</div>
            </div>
            <div class="summary-card">
                <h3>Healed</h3>
                <div class="summary-value healed">{healed_steps}</div>
            </div>
            <div class="summary-card">
                <h3>Failed</h3>
                <div class="summary-value failed">{failed_steps}</div>
            </div>
        </div>

        <!-- Metadata -->
        <div class="meta-info-card">
            <h2 class="section-title" style="margin-top:0;">Test Details</h2>
            <div class="meta-grid">
                <div class="meta-item">
                    <strong>Target URL</strong>
                    <a href="{url}" target="_blank" style="color: #60a5fa; text-decoration:none;">{url}</a>
                </div>
                <div class="meta-item">
                    <strong>Testing Goal</strong>
                    <span>{task_goal}</span>
                </div>
            </div>
            
            <div class="trace-btn-container" style="text-align: left; margin-top:20px;">
                <a class="btn" href="file:///{os.path.abspath(trace_path)}" download>Download Playwright Trace File</a>
                <span style="margin-left: 15px; color: var(--text-muted); font-size:0.9rem;">
                    Load this trace at <a href="https://trace.playwright.dev" target="_blank" style="color: var(--primary);">trace.playwright.dev</a> to review execution steps.
                </span>
            </div>
        </div>

        <!-- Steps list -->
        <div class="steps-container">
            <h2 class="section-title">Execution Steps Graph</h2>
            {step_rows_html}
        </div>

        <!-- Intercepted Errors & Logs -->
        <div class="logs-grid">
            <div>
                <h2 class="section-title">Intercepted Console Errors</h2>
                <div class="logs-panel">
                    {console_logs_html}
                </div>
            </div>
            <div>
                <h2 class="section-title">Failed Network Requests</h2>
                <div class="logs-panel">
                    {network_errors_html}
                </div>
            </div>
        </div>
    </div>
</body>
</html>
"""
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

def save_json_report(
    url: str,
    task_goal: str,
    steps: List[TestStep],
    console_logs: List[str],
    network_errors: List[str],
    test_passed: bool,
    trace_path: str,
    output_path: str
):
    """
    Saves a raw JSON report for programmatic parsers.
    """
    report_data = {
        "url": url,
        "task_goal": task_goal,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "test_passed": test_passed,
        "trace_path": trace_path,
        "metrics": {
            "total_steps": len(steps),
            "passed": sum(1 for s in steps if s.status == "passed"),
            "healed": sum(1 for s in steps if s.status == "healed"),
            "failed": sum(1 for s in steps if s.status == "failed")
        },
        "steps": [s.model_dump() for s in steps],
        "console_logs": console_logs,
        "failed_network_requests": network_errors
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)
