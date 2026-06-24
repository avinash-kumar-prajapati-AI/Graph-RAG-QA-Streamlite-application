from __future__ import annotations
"""
app.py — Gradio UI for DBReadAgent (local Ollama)
Run: python src/app.py
"""
"""
app.py — Gradio UI for DBReadAgent (multi-provider)
Run: python src/app.py
"""


import logging
import os
import sys
import tempfile
from pathlib import Path

import gradio as gr
import pandas as pd
from dotenv import load_dotenv

_src = Path(__file__).parent
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

load_dotenv()
logging.basicConfig(level=logging.WARNING)

from db_setup import get_schema_text, init_all
from agent import ConversationManager, PROVIDER_CONFIGS
from tools import execute_read_sql, format_result

init_all()

# ── Mutable app state ─────────────────────────────────────────────────────────
_state: dict = {"conv": ConversationManager()}


def _active_conv() -> ConversationManager:
    return _state["conv"]


def _rebuild_conv(provider: str, model_override: str) -> str:
    """Rebuild ConversationManager with new provider. Returns status string."""
    if model_override.strip():
        os.environ["LLM_MODEL"] = model_override.strip()
    elif "LLM_MODEL" in os.environ:
        del os.environ["LLM_MODEL"]
    try:
        _state["conv"] = ConversationManager(provider=provider)
        cfg = PROVIDER_CONFIGS[provider]
        model = os.getenv("LLM_MODEL", cfg["default_model"])
        return f"✅ Switched to **{provider}** · model: `{model}`"
    except Exception as exc:
        return f"❌ Failed to init provider `{provider}`: {exc}"


# ── Stats ─────────────────────────────────────────────────────────────────────
def _stats() -> str:
    conv = _active_conv()
    cfg  = PROVIDER_CONFIGS.get(conv.provider, {})
    model = os.getenv("LLM_MODEL", cfg.get("default_model", "unknown"))
    return (
        f"**Provider:** `{conv.provider}` · "
        f"**Model:** `{model}` · "
        f"**Turn:** {conv.turn_count} · "
        f"**History:** {len(conv.history)} msgs"
    )


# ── Examples ──────────────────────────────────────────────────────────────────
EXAMPLES: list[tuple[str, str]] = [
    ("👥 Dept headcount + avg salary",
     "List all departments with employee headcount and average salary, ordered by headcount desc."),
    ("📊 Salary ranking (window fn)",
     "Rank employees by salary within each department using RANK(). Show % above/below dept average."),
    ("🏆 Top performers 2024",
     "Show the top 10 employees by average performance review score in 2024. Include their department."),
    ("🔗 Employees on 3+ projects",
     "Find employees assigned to 3 or more projects. Show name, department, project list, and total weekly hours."),
    ("📈 Monthly revenue trend",
     "Build a monthly revenue trend for 2024 from conversion_events. Include cumulative running total."),
    ("🧪 A/B test winner",
     "Analyse all A/B tests: for each test + variant show sessions, conversions, conversion rate %, and revenue. Which variant wins each test?"),
    ("⚠️ Reorder alerts",
     "Which products have total stock on hand below their reorder point across all warehouses? Show the shortfall per warehouse."),
    ("🏭 Warehouse value",
     "Rank warehouses by total inventory value (qty_on_hand × unit_price). Break down by product category."),
    ("📋 Dept productivity CTE",
     "Using CTEs: per department show headcount, total salary, active projects count, total project budget, and avg 2024 review score."),
    ("🔄 Follow-up: break by level",
     "Now break the previous result down by seniority level."),
    ("🔍 Channel conversion rates",
     "What is the conversion rate (signups/sessions) by acquisition channel? Show sessions, signups, rate %."),
    ("📦 Pending POs overstock risk",
     "Find products where total pending purchase orders would push stock above 3× reorder point — flag as overstock risk."),
]


# ── Handlers ──────────────────────────────────────────────────────────────────
def on_send(user_msg: str, chat_history: list) -> tuple[list, str, str]:
    if not user_msg.strip():
        return chat_history, "", _stats()
    try:
        answer, sql_used = _active_conv().ask(user_msg)
    except Exception as exc:
        answer   = f"❌ Agent error: {exc}"
        sql_used = []

    chat_history.append({"role": "user",      "content": user_msg})
    chat_history.append({"role": "assistant",  "content": answer})
    sql_display = "\n\n---\n\n".join(sql_used) if sql_used else "*(no SQL this turn)*"
    return chat_history, sql_display, _stats()


def on_reset() -> tuple[list, str, str]:
    _active_conv().reset()
    return [], "*(conversation reset)*", _stats()


def on_provider_apply(provider: str, model_override: str) -> str:
    return _rebuild_conv(provider, model_override)


def on_load_schema(db_choice: str) -> str:
    name = db_choice.lower().split()[0]
    targets = None if name == "all" else [name]
    return get_schema_text(targets)


def on_run_quick_sql(db: str, sql: str) -> str:
    r = execute_read_sql(db, sql)
    return format_result(r, max_rows=150)


def on_export():
    conv = _active_conv()
    if not conv.history:
        return None
    rows = []
    for i in range(0, len(conv.history) - 1, 2):
        rows.append({
            "turn":     i // 2 + 1,
            "question": conv.history[i]["content"],
            "answer":   conv.history[i + 1]["content"],
        })
    df  = pd.DataFrame(rows)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="w", newline="")
    df.to_csv(tmp.name, index=False)
    return tmp.name


# ── CSS ───────────────────────────────────────────────────────────────────────
CSS = """
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=Inter:wght@400;500;600&display=swap');

body, .gradio-container {
    font-family: 'Inter', sans-serif !important;
    background: #0f1117 !important;
    color: #e2e8f0 !important;
}
.gradio-container { max-width: 1440px !important; margin: 0 auto !important; }

#hdr { padding: 18px 0 10px; border-bottom: 1px solid #1e2433; margin-bottom: 16px; }
#hdr h1 { font-family: 'IBM Plex Mono', monospace !important;
          font-size: 1.7rem !important; color: #58a6ff !important;
          margin: 0 0 4px !important; }
#hdr p  { color: #8b949e !important; font-size: 0.88rem !important; margin: 0 !important; }

.message.user { background: #1c2333 !important; border-radius: 10px !important; }
.message.bot  { background: #161b22 !important; border-radius: 10px !important; }

#sql-panel textarea {
    font-family: 'IBM Plex Mono', monospace !important; font-size: 11.5px !important;
    background: #0d1117 !important; color: #79c0ff !important;
    border: 1px solid #21262d !important; border-radius: 6px !important;
}
#schema-panel textarea {
    font-family: 'IBM Plex Mono', monospace !important; font-size: 11px !important;
    background: #0d1117 !important; color: #adbac7 !important;
}
#provider-status { font-size: 13px !important; padding: 6px 0 !important; }

.ex-btn { font-size: 11.5px !important; padding: 4px 8px !important;
          background: #1c2333 !important; border: 1px solid #30363d !important;
          color: #c9d1d9 !important; border-radius: 5px !important; margin: 2px 0 !important; }
.ex-btn:hover { background: #21262d !important; border-color: #58a6ff !important; color: #58a6ff !important; }

#send-btn  { background: #238636 !important; border: none !important; font-weight: 600 !important; }
#send-btn:hover { background: #2ea043 !important; }
#reset-btn { background: #21262d !important; border: 1px solid #30363d !important; }
#stats     { font-size: 12px !important; color: #8b949e !important; padding: 4px 0 !important; }
.tab-nav button { font-family: 'IBM Plex Mono', monospace !important; font-size: 13px !important; }
"""


# ── UI ────────────────────────────────────────────────────────────────────────
def build_ui() -> gr.Blocks:
    with gr.Blocks(css=CSS, title="DBReadAgent") as demo:

        with gr.Column(elem_id="hdr"):
            gr.HTML("""
            <h1>🔍 DBReadAgent</h1>
            <p>Natural language SQL analyst · Follow-up questions · Multi-database · Read-only · Multi-provider LLM</p>
            """)

        with gr.Tabs():

            # ── Tab 1: Chat ──────────────────────────────────────────────────
            with gr.TabItem("💬 Chat"):
                with gr.Row(equal_height=True):

                    with gr.Column(scale=6):
                        chatbot = gr.Chatbot(
                            label="", height=520, render_markdown=True,
                            # type="messages",
                            avatar_images=(
                                None,
                                "https://api.dicebear.com/7.x/bottts-neutral/svg?seed=dbreader",
                            ),
                        )
                        with gr.Row():
                            msg_in    = gr.Textbox(
                                placeholder="Ask anything… e.g. 'Show top 3 earning departments, then break by level'",
                                label="", lines=2, scale=5, show_label=False,
                            )
                            send_btn  = gr.Button("▶ Send",  variant="primary",   scale=1, elem_id="send-btn")
                            reset_btn = gr.Button("↺ Reset", variant="secondary", scale=1, elem_id="reset-btn")

                        stats_md = gr.Markdown(_stats(), elem_id="stats")
                        with gr.Row():
                            export_btn  = gr.Button("⬇ Export History CSV", size="sm")
                            export_file = gr.File(label="Download", visible=False)

                    with gr.Column(scale=4):
                        sql_out = gr.Textbox(
                            label="📋 SQL Executed", lines=13, max_lines=22,
                            interactive=False, elem_id="sql-panel",
                        )
                        gr.Markdown("### 💡 Example Questions")
                        for label, question in EXAMPLES:
                            btn = gr.Button(label, size="sm", elem_classes="ex-btn")
                            btn.click(lambda q=question: q, outputs=[msg_in])

            # ── Tab 2: Provider ──────────────────────────────────────────────
            with gr.TabItem("🔌 Provider"):
                gr.Markdown("Switch LLM provider without restarting the app. Resets conversation context.")
                with gr.Row():
                    provider_dd = gr.Dropdown(
                        choices=list(PROVIDER_CONFIGS.keys()),
                        value=_active_conv().provider,
                        label="Provider", scale=1,
                    )
                    model_in = gr.Textbox(
                        label="Model override (blank = provider default)",
                        placeholder="e.g. llama-3.1-8b-instant",
                        scale=2,
                    )
                    apply_btn = gr.Button("Apply", variant="primary", scale=1)

                provider_status = gr.Markdown(
                    f"Current: **{_active_conv().provider}**", elem_id="provider-status"
                )

                gr.Markdown("""
### Provider reference

| Provider | Base URL | Key env var | Example model |
|---|---|---|---|
| `ollama` | `http://localhost:11434/v1` | — | `llama3.2:3b` |
| `llamacpp` | `http://localhost:8080/v1` | — | `local` |
| `groq` | `https://api.groq.com/openai/v1` | `GROQ_API_KEY` | `llama-3.3-70b-versatile` |
| `openrouter` | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` | `meta-llama/llama-3.3-70b-instruct` |

Add API keys to `.env` in project root. Changes apply after clicking **Apply**.

> ⚠️ Switching provider rebuilds the agent and **clears conversation history**.
""")

            # ── Tab 3: Schema Explorer ───────────────────────────────────────
            with gr.TabItem("🗄️ Schema Explorer"):
                gr.Markdown("Browse DDL and row counts for any database.")
                with gr.Row():
                    db_pick    = gr.Dropdown(
                        choices=["All databases", "Company", "Analytics", "Inventory"],
                        value="All databases", label="Database", scale=1,
                    )
                    schema_btn = gr.Button("Load Schema", variant="primary", scale=1)
                schema_out = gr.Textbox(
                    label="Schema DDL", lines=42, interactive=False, elem_id="schema-panel",
                )
                schema_btn.click(on_load_schema, inputs=[db_pick], outputs=[schema_out])

            # ── Tab 4: Quick SQL ─────────────────────────────────────────────
            with gr.TabItem("⚡ Quick SQL"):
                gr.Markdown("Run raw SQL directly against any database (read-only).")
                with gr.Row():
                    qs_db  = gr.Dropdown(
                        choices=["company", "analytics", "inventory"],
                        value="company", label="Database", scale=1,
                    )
                    qs_run = gr.Button("▶ Run", variant="primary", scale=1)
                qs_sql = gr.Textbox(
                    label="SQL", lines=7,
                    value=(
                        "WITH dept_stats AS (\n"
                        "    SELECT dept_id, AVG(salary) avg_sal, COUNT(*) n\n"
                        "    FROM employees GROUP BY dept_id\n"
                        ")\n"
                        "SELECT d.dept_name, ds.n headcount, ROUND(ds.avg_sal,0) avg_salary\n"
                        "FROM dept_stats ds JOIN departments d ON ds.dept_id = d.dept_id\n"
                        "ORDER BY ds.avg_sal DESC;"
                    ),
                )
                qs_out = gr.Textbox(label="Result", lines=24, interactive=False)
                qs_run.click(on_run_quick_sql, inputs=[qs_db, qs_sql], outputs=[qs_out])

            # ── Tab 5: Setup / Info ──────────────────────────────────────────
            with gr.TabItem("⚙️ Setup"):
                gr.Markdown(f"""
## Architecture

```
User Input
    │
ConversationManager
  ├─ Injects last {os.getenv("MAX_HISTORY_TURNS","12")} turns as context block
  └─ LangGraph StateGraph
       ├─ agent_node  (Ollama LLM via langchain-ollama)
       │    ├─ Reads schema if needed
       │    ├─ Plans SQL
       │    └─ Calls tool(s)
       └─ tool_node
            ├─ query_company()     → company.db   (SQLite, read-only)
            ├─ query_analytics()   → analytics.db
            ├─ query_inventory()   → inventory.db
            ├─ get_schema()
            ├─ explain_query()
            └─ get_sample_values()
```

## Databases
| DB | Tables | Scale |
|---|---|---|
| company | employees, departments, projects, assignments, performance_reviews | 80 employees, 3-yr reviews |
| analytics | user_sessions, page_views, conversion_events, ab_tests | 2000 sessions, 7000+ views |
| inventory | products, warehouses, stock_levels, purchase_orders | 5 warehouses, 200 POs |
""")

        # ── Event wiring ──────────────────────────────────────────────────────
        send_btn.click(
            on_send, inputs=[msg_in, chatbot], outputs=[chatbot, sql_out, stats_md]
        ).then(lambda: "", outputs=[msg_in])

        msg_in.submit(
            on_send, inputs=[msg_in, chatbot], outputs=[chatbot, sql_out, stats_md]
        ).then(lambda: "", outputs=[msg_in])

        reset_btn.click(on_reset, outputs=[chatbot, sql_out, stats_md])

        apply_btn.click(
            on_provider_apply,
            inputs=[provider_dd, model_in],
            outputs=[provider_status],
        ).then(_stats, outputs=[stats_md])

        export_btn.click(
            lambda: (on_export(), gr.update(visible=True)),
            outputs=[export_file, export_file],
        )

    return demo


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port  = int(os.getenv("GRADIO_SERVER_PORT", 7860))
    host  = os.getenv("GRADIO_SERVER_NAME", "127.0.0.1")
    share = os.getenv("GRADIO_SHARE", "false").lower() == "true"

    ui = build_ui()
    print(f"\n🚀  DBReadAgent running → http://{host}:{port}\n")
    ui.launch(server_name=host, server_port=port, share=share, show_error=True)


# # ── Entry point ───────────────────────────────────────────────────────────────
# if __name__ == "__main__":
#     port  = int(os.getenv("GRADIO_SERVER_PORT", 7860))
#     host  = os.getenv("GRADIO_SERVER_NAME", "127.0.0.1")
#     share = os.getenv("GRADIO_SHARE", "false").lower() == "true"

#     ui = build_ui()
#     print(f"\n🚀  DBReadAgent running → http://{host}:{port}\n")
#     ui.launch(server_name=host, server_port=port, share=share, show_error=True)
