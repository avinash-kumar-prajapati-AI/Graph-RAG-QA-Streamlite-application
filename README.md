# 🔍 LangGraph SQL Assistant

> Natural language SQL analyst powered by LangGraph · Multi-provider LLM · Multi-database · Read-only · Gradio UI

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2%2B-orange)](https://github.com/langchain-ai/langgraph)
[![Gradio](https://img.shields.io/badge/Gradio-6.x-blueviolet?logo=gradio)](https://gradio.app/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## Overview

LangGraph SQL Assistant lets you query structured databases in plain English. It resolves follow-up questions using conversation history, selects the right database automatically, generates optimised SQL (CTEs, window functions, aggregations), executes it read-only, and returns a natural-language summary alongside the raw SQL used.

Supports **Groq**, **OpenRouter**, **llama.cpp** (local), and **Ollama** (local) — switchable at runtime from the UI without restarting.

### Note i am using miniconda so you can adjust accordingly and make sure to fork(click the star) this project to support.
---

## Demo

```
User:  List all departments with employee headcount and average salary.
Agent: Here are the 6 departments ordered by headcount…
       [SQL: WITH dept_stats AS (SELECT dept_id, AVG(salary)…)]

User:  Now break the highest-budget department down by seniority level.
Agent: Engineering (highest budget) breaks down as follows…  ← follow-up resolved ✓
```

---

## Features

- **Natural language → SQL** — handles multi-step CTEs, window functions, joins, aggregations
- **Follow-up resolution** — pronouns and references resolved from conversation history
- **Multi-database** — company, analytics, inventory SQLite databases
- **Multi-provider LLM** — Groq, OpenRouter, llama.cpp, Ollama; switch from UI at runtime
- **Read-only enforced** — INSERT / UPDATE / DELETE / DROP blocked at prompt and tool level
- **Gradio UI** — chat interface, SQL viewer, schema explorer, raw SQL runner, CSV export
- **LangGraph agent loop** — schema-load → plan → execute → synthesise, with tool-call retries

---

## Architecture

```
User Input
    │
ConversationManager
  ├─ Injects last N turns as context (follow-up resolution)
  └─ LangGraph StateGraph
       ├─ agent_node  (ChatOpenAI → Groq / OpenRouter / llama.cpp / Ollama)
       │    ├─ get_schema()         — loads DDL on demand
       │    ├─ Plans SQL (CTE / window fn / subquery)
       │    └─ Calls query tool
       └─ tool_node
            ├─ query_company()      → company.db    (SQLite)
            ├─ query_analytics()    → analytics.db  (SQLite)
            ├─ query_inventory()    → inventory.db  (SQLite)
            ├─ get_schema()
            ├─ explain_query()
            └─ get_sample_values()
```

---

## Project Structure

```
.
├── src/
│   ├── agent.py          # LangGraph agent, ConversationManager, provider configs
│   ├── app.py            # Gradio UI
│   ├── db_setup.py       # Database initialisation and schema utilities
│   └── tools.py          # LangChain tools wrapping SQLite execution
├── databases/            # Auto-created SQLite databases (gitignored)
├── .env.example
├── requirements.txt
└── README.md
```

---

## Quickstart

### 1. Clone & install

```bash
git clone https://github.com/your-username/langgraph-sql-assistant.git
cd langgraph-sql-assistant
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Provider to use on startup (ollama | llamacpp | groq | openrouter)
LLM_PROVIDER=ollama

# Optional: override the provider's default model.
# Note that the small LLM mean lesser reasioning capacity and migh provide irrelevent results (LLM above 10b param works fine)
# LLM_MODEL=llama3.2:3b

# API keys — only needed for cloud providers
GROQ_API_KEY=gsk_...
OPENROUTER_API_KEY=sk-or-...

# you can change the LLM_provider to groq also but openrouter is better than other
#LLM_PROVIDER='openrouter'

### 3. Run

```bash
python app.py
```

Open [http://localhost:7860](http://localhost:7860).

### you can even just run the last cell of the this jupyter notebook and visit the local web page(the http://localhost:7860) to view in browser.
---

## Provider Setup

| Provider | How to start | Key env var | Default model |
|---|---|---|---|
| **Ollama** | `ollama serve` | — | `llama3.2:3b` |
| **llama.cpp** | `./server -m model.gguf --port 8080` | — | *(ignored)* |
| **Groq** | Cloud API | `GROQ_API_KEY` | `llama-3.3-70b-versatile` |
| **OpenRouter** | Cloud API | `OPENROUTER_API_KEY` | `meta-llama/llama-3.3-70b-instruct` |

> **llama.cpp note:** the model must be a GGUF with tool-call support (e.g. a Llama-3 or Functionary GGUF). Without it, the agent will answer in prose without executing any SQL.

Providers can also be switched at runtime from the **🔌 Provider** tab in the UI — no restart needed.

---

## Databases

| Database | Tables | Contents |
|---|---|---|
| `company` | employees, departments, projects, assignments, performance_reviews | 80 employees, 3 years of reviews |
| `analytics` | user_sessions, page_views, conversion_events, ab_tests | 2 000 sessions, 7 000+ page views |
| `inventory` | products, warehouses, stock_levels, purchase_orders | 5 warehouses, 200 purchase orders |

Databases are created and seeded automatically on first run via `db_setup.init_all()`.

---

## Example Questions

| Category | Question |
|---|---|
| Aggregation | List all departments with headcount and average salary, ordered by headcount desc |
| Window function | Rank employees by salary within each department using RANK(). Show % above/below dept average |
| CTE | Per department: headcount, total salary, active project count, total budget, avg 2024 review score |
| Follow-up | Now break the highest-budget department down by seniority level |
| Time series | Monthly revenue trend for 2024 with cumulative running total |
| A/B testing | For each A/B test and variant: sessions, conversions, conversion rate %, revenue — which variant wins? |
| Inventory | Products where pending POs would push stock above 3× reorder point — flag as overstock risk |

---

## Requirements

```
python >= 3.10
langchain-core
langchain-openai
langchain-ollama
langgraph
gradio >= 4.0
pandas
python-dotenv
```

Full list in `requirements.txt`.

---

## Notebook Usage

The agent can also be driven from a Jupyter notebook without the Gradio UI:

```python
from agent import ConversationManager

conv = ConversationManager(provider="groq")   # or ollama / openrouter / llamacpp

answer, sql = conv.ask("List all departments with headcount and average salary.")
print(answer)

# Follow-up — conversation history is maintained automatically
answer2, sql2 = conv.ask("Now break the highest-budget department down by seniority level.")
print(answer2)
```

---

## Contributing

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m 'Add your feature'`
4. Push: `git push origin feature/your-feature`
5. Open a Pull Request

---

## License

MIT — see [LICENSE](LICENSE) for details.
