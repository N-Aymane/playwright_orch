# 🤖 Autonomous Web Testing & Self-Healing Multi-Agent Framework

> **Production-grade AI-powered web testing framework built with LangGraph + Playwright.**
>
> Autonomously explores web applications, generates intelligent test plans, fills forms with AI-generated mock data, executes browser actions, and automatically repairs broken locators using a self-healing multi-agent architecture.

---

# ✨ Features

| Feature | Description |
|----------|-------------|
| 🧠 **Planner Agent** | Converts natural language goals into structured browser test plans |
| ⚡ **Executor Agent** | Executes Playwright actions with AI-generated mock form data |
| 🔧 **Self-Healing Agent** | Repairs broken locators by analyzing the live DOM and retrying failed steps |
| 🎭 **Playwright Tracing** | Records screenshots, network activity, DOM snapshots, and execution timeline |
| 📊 **Rich HTML Reports** | Interactive execution reports with logs, failures, and trace links |
| 📡 **Error Monitoring** | Captures browser console errors and failed network requests |
| 🔌 **OpenAI Compatible** | Works with OpenAI, Azure OpenAI, Ollama, LM Studio, and compatible APIs |

---

# 🏗️ Architecture

```text
                User Goal
                    │
                    ▼
        ┌─────────────────────┐
        │   Planner Agent     │
        │   (LangGraph)       │
        └──────────┬──────────┘
                   │
                   ▼
        ┌─────────────────────┐
        │  Executor Agent     │
        │  (Playwright)       │
        └──────────┬──────────┘
                   │
           Success?│
             │     │
            Yes    No
             │     ▼
             │ ┌──────────────────┐
             │ │  Healer Agent    │
             │ │ Repairs Locators │
             │ └────────┬─────────┘
             └──────────┘
                    │
                    ▼
        HTML Report • JSON • Trace
```

---

# 📁 Project Structure

```text
agentic_web_tester/
│
├── agents/
│   ├── __init__.py
│   ├── planner.py
│   ├── executor.py
│   └── healer.py
│
├── utils/
│   ├── __init__.py
│   ├── dom_parser.py
│   ├── logger.py
│   └── reporter.py
│
├── scratch/
│   └── test_server.py
│
├── browser_engine.py
├── config.py
├── orchestrator.py
├── schemas.py
├── main.py
├── requirements.txt
└── .env.example
```

---

# 📋 Requirements

- Python **3.11+**
- Chromium (installed through Playwright)
- OpenAI API key (or compatible endpoint)

---

# ⚡ Installation

## 1. Clone the repository

```bash
git clone https://github.com/yourusername/agentic-web-tester.git
cd agentic-web-tester
```

---

## 2. Create a virtual environment

### Windows PowerShell

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

If execution is blocked:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.venv\Scripts\Activate.ps1
```

### Windows CMD

```cmd
.venv\Scripts\activate.bat
```

---

## 3. Install dependencies

```powershell
pip install -r requirements.txt
python -m playwright install chromium
```

---

## 4. Configure environment

Copy

```text
.env.example
```

to

```text
.env
```

Then edit:

```env
OPENAI_API_KEY=sk-your-key-here

HEADLESS=true

LLM_MODEL=gpt-4o-mini
```

---

# 🚀 Running the Framework

## Run against a live website

```powershell
python main.py ^
--url "https://demoqa.com/automation-practice-form" ^
--goal "Fill out the practice automation form with valid personal information"
```

---

## Run the local demo

Start the demo server:

```powershell
python scratch/test_server.py
```

Open another terminal:

```powershell
python main.py ^
--url http://localhost:8765 ^
--goal "Register a new user account"
```

---

## Test the self-healing system

Run the intentionally mutated version:

```powershell
python main.py ^
--url http://localhost:8765/mutated ^
--goal "Register a new user account"
```

The mutated application intentionally breaks element locators so the **Healer Agent** can repair them automatically.

---

# ⚙️ CLI Options

```text
python main.py [OPTIONS]

Required:
  --url             Target URL
  --goal            Natural language testing goal

Optional:
  --headless        true / false
  --model           Override LLM model
  --trace           Playwright trace output path
  --report          HTML report path
  --json-report     JSON report path
```

---

# 🔧 Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | Required | OpenAI API key |
| `OPENAI_API_BASE` | https://api.openai.com/v1 | OpenAI compatible endpoint |
| `LLM_MODEL` | gpt-4o-mini | LLM model |
| `LLM_TEMPERATURE` | 0.0 | Model temperature |
| `HEADLESS` | true | Run browser headless |
| `BROWSER_TIMEOUT` | 10000 | Browser timeout (ms) |
| `DEFAULT_WAIT_TIME` | 5000 | Locator timeout (ms) |
| `TRACE_PATH` | trace.zip | Trace output |
| `REPORT_PATH` | report.html | HTML report output |

---

# 📊 Generated Output

After each execution the framework generates:

| File | Description |
|------|-------------|
| `report.html` | Interactive HTML report |
| `report.json` | JSON execution summary |
| `trace.zip` | Playwright trace |
| `logs/execution.log` | Text log |
| `logs/execution.json.log` | Structured JSON log |

### View the Playwright Trace

```powershell
npx playwright show-trace trace.zip
```

Or upload `trace.zip` to:

https://trace.playwright.dev

---

# 🎯 Supported Actions

| Action | Description |
|--------|-------------|
| `navigate` | Open a URL |
| `click` | Click an element |
| `fill` | Fill text/email/password inputs |
| `select` | Select dropdown option |
| `check` | Toggle checkbox |
| `assert_text` | Verify page text |
| `wait_for_selector` | Wait for an element |

---

# 🖥️ Using Local LLMs

### Ollama

```env
OPENAI_API_BASE=http://localhost:11434/v1
OPENAI_API_KEY=ollama
LLM_MODEL=llama3.1
```

### LM Studio

```env
OPENAI_API_BASE=http://localhost:1234/v1
OPENAI_API_KEY=lmstudio
LLM_MODEL=your-model-name
```

---

# 📄 License

MIT License — Free to use, modify, and distribute.