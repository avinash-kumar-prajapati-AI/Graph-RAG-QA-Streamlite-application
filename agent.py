"""
agent.py — DBReadAgent: LangGraph + Ollama (local LLM) + conversation memory
"""

from __future__ import annotations

import logging
import operator
import os
import re
from dataclasses import dataclass, field
from typing import Annotated, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI   # pip install langchain-openai
# from langchain_ollama import ChatOllama   # keep for pure Ollama fallback



from tools import ALL_TOOLS

load_dotenv()
log = logging.getLogger(__name__)


PROVIDER_CONFIGS = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
        "default_model": "llama-3.3-70b-versatile",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "default_model": "meta-llama/llama-3.3-70b-instruct",
    },
    "llamacpp": {
        "base_url": "http://localhost:8080/v1",   # llama.cpp server default
        "api_key_env": None,
        "default_model": "local",                 # llama.cpp ignores this
    },
    # "ollama": {
    #     "base_url": "http://localhost:11434/v1",
    #     "api_key_env": None,
    #     "default_model": "llama3.2:3b",
    # },
}
# ── LLM (Ollama) ──────────────────────────────────────────────────────────────
def build_llm(provider: str | None = None) -> ChatOpenAI:
    provider = (provider or os.getenv("LLM_PROVIDER", "openrouter")).lower()
    cfg      = PROVIDER_CONFIGS.get(provider)
    if cfg is None:
        raise ValueError(f"Unknown provider '{provider}'. Choose: {list(PROVIDER_CONFIGS)}")

    api_key = (
        os.getenv(cfg["api_key_env"]) if cfg["api_key_env"] else "not-needed"
    )
    if cfg["api_key_env"] and not api_key:
        raise EnvironmentError(
            f"Provider '{provider}' needs {cfg['api_key_env']} in your .env"
        )

    model = os.getenv("LLM_MODEL", cfg["default_model"])

    log.info("LLM provider=%s  model=%s  base_url=%s", provider, model, cfg["base_url"])
    return ChatOpenAI(
        model=model,
        base_url=cfg["base_url"],
        api_key=api_key,
        temperature=0,
        max_tokens=4096,
    )

# ── System prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are DBReadAgent, an expert read-only SQL analyst assistant running locally.

## Available databases
- **company**   — employees, departments, projects, assignments, performance_reviews
- **analytics** — user_sessions, page_views, conversion_events, ab_tests
- **inventory** — products, warehouses, stock_levels, purchase_orders

## Workflow for EVERY question
1. **Resolve context** — If this is a follow-up ("those employees", "same filter", "break it down by"),
   resolve all pronouns and references from the conversation history provided.
2. **Load schema first** — Call `get_schema` if you don't yet know the table structure.
   Pass only the database(s) you need, not all.
3. **Plan before executing** — For complex queries think: Which tables? Which JOINs?
   Do I need a CTE? Window function? Subquery?
4. **Write optimal SQL** — Use CTEs for multi-step logic. Window functions for ranking/running totals.
   Qualify columns with table aliases in multi-table queries.
5. **Execute** — Use the correct `query_*` tool for the target database.
6. **Synthesise** — Give a clear natural-language summary: highlight key numbers, anomalies, trends.

## SQL best practices
- CTEs: `WITH cte AS (SELECT ...)` for 3+ step queries
- Ranking: `RANK() OVER (PARTITION BY dept_id ORDER BY salary DESC)`
- Running totals: `SUM(revenue) OVER (ORDER BY month)`
- Time series: `strftime('%Y-%m', date_col)` for monthly grouping
- Text lists: `GROUP_CONCAT(name, ', ')` to aggregate strings
- Nulls: `COALESCE(value, 0)`, decimals: `ROUND(x, 2)`
- Default LIMIT 100 unless user asks for more
- NEVER generate INSERT / UPDATE / DELETE / DROP / CREATE / ALTER

## Follow-up resolution examples
- "now break that down by department" → same filters, add GROUP BY dept
- "who are those employees?" → add name column to previous query
- "show me the top 5" → add ORDER BY + LIMIT 5 to previous logic
- "compare with last quarter" → extend date range or add period column

Be precise, data-driven, and concise. Explain complex SQL choices briefly."""


# ── LangGraph state ───────────────────────────────────────────────────────────
class GraphState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]


# ── Nodes ─────────────────────────────────────────────────────────────────────
def make_agent_node(llm_with_tools):
    def agent_node(state: GraphState) -> dict:
        msgs = state["messages"]
        if not any(isinstance(m, SystemMessage) for m in msgs):
            msgs = [SystemMessage(content=SYSTEM_PROMPT)] + msgs
        response = llm_with_tools.invoke(msgs)
        return {"messages": [response]}
    return agent_node


def should_continue(state: GraphState) -> str:
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return END


def build_graph(provider: str | None = None):
    llm             = build_llm(provider)
    llm_with_tools  = llm.bind_tools(ALL_TOOLS)
    agent_node_fn   = make_agent_node(llm_with_tools)
    tool_node       = ToolNode(ALL_TOOLS)

    g = StateGraph(GraphState)
    g.add_node("agent", agent_node_fn)
    g.add_node("tools", tool_node)
    g.set_entry_point("agent")
    g.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    g.add_edge("tools", "agent")
    return g.compile()


# ── Conversation manager ──────────────────────────────────────────────────────
@dataclass
class ConversationManager:
    provider:        str  = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "openrouter"))

    max_turns: int = int(os.getenv("MAX_HISTORY_TURNS", "12"))
    history:   list[dict] = field(default_factory=list)   # [{role, content}]
    _graph:    object = field(default=None, repr=False)
    recursion_limit: int = int(os.getenv("AGENT_RECURSION_LIMIT", "30"))

    def __post_init__(self):
        self._graph = build_graph(self.provider)
        log.info("DBReadAgent compiled  provider=%s", self.provider)

    # ── context injection ─────────────────────────────────────────────────────
    def _context_block(self) -> str:
        if not self.history:
            return ""
        recent = self.history[-(self.max_turns * 2):]
        lines  = ["## Conversation history (resolve follow-up references from this):"]
        for i, turn in enumerate(recent, 1):
            role    = "User" if turn["role"] == "user" else "Assistant"
            snippet = turn["content"][:700] + "…" if len(turn["content"]) > 700 else turn["content"]
            lines.append(f"[Turn {i}] {role}: {snippet}")
        return "\n".join(lines)

    # ── public API ────────────────────────────────────────────────────────────
    def ask(self, question: str) -> tuple[str, list[str]]:
        """Submit a question → (answer, sql_queries_used)."""
        ctx     = self._context_block()
        payload = f"{ctx}\n\n## Current question:\n{question}" if ctx else question

        # Build LangGraph message list from history
        lc_msgs: list[BaseMessage] = []
        for t in self.history[-(self.max_turns * 2):]:
            cls = HumanMessage if t["role"] == "user" else AIMessage
            lc_msgs.append(cls(content=t["content"]))
        lc_msgs.append(HumanMessage(content=payload))

        result = self._graph.invoke(
            {"messages": lc_msgs},
            config={"recursion_limit": self.recursion_limit},
        )

        # Extract final answer
        ai_msgs = [m for m in result["messages"] if isinstance(m, AIMessage)]
        answer  = ai_msgs[-1].content if ai_msgs else "(no response)"

        # Extract SQL used from tool messages
        sql_used: list[str] = []
        for m in result["messages"]:
            if isinstance(m, ToolMessage):
                for match in re.findall(r"```sql\n(.*?)\n```", str(m.content), re.DOTALL):
                    sql_used.append(match.strip())

        # Update history (trim to window)
        self.history.append({"role": "user",      "content": question})
        self.history.append({"role": "assistant",  "content": answer})
        if len(self.history) > self.max_turns * 2 + 4:
            self.history = self.history[-(self.max_turns * 2):]

        return answer, sql_used

    def reset(self) -> None:
        self.history.clear()
        log.info("Conversation reset.")

    @property
    def turn_count(self) -> int:
        return len(self.history) // 2
