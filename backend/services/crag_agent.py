"""
crag_agent.py — LangGraph Corrective RAG (CRAG) StateGraph

Flow:
  extract_entities → retrieve_context → grade_context
       ├─ relevant / empty KG ──► generate → check_groundedness
       │                               ├─ grounded ──► END
       │                               └─ not grounded ──► web_search → generate_from_web → END
       └─ not relevant ──────────────► web_search → generate_from_web → END

Persistent memory: LangGraph SqliteSaver checkpoints the full AgentState
per thread_id (= session_id) in aurora.db, surviving server restarts.
"""

import os
import time
from typing import TypedDict, Literal

import google.generativeai as genai
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END

from services.context_builder import build_context_md
from services.kg_service import extract_and_update_kg
from services.llm_provider import get_llm_provider
from models.database import DB_PATH

load_dotenv()


# ── Prompts ────────────────────────────────────────────────────────────────────
_BASE_SYSTEM = """You are Aurora, a personal AI assistant.
You help users achieve their goals across any life domain — career, health, skills, projects.
You are calm, direct, and actionable. Use bullet points for lists. Keep replies concise."""

_GRADE_PROMPT = """You are evaluating whether a context brief is sufficient to answer a question.

Context:
{context}

Question: {question}

Is this context sufficient and relevant to give a personalised, helpful answer?
Answer with ONLY "YES" or "NO"."""

_GROUNDEDNESS_PROMPT = """You are checking if an answer is actually grounded in the provided context.

Context:
{context}

Answer:
{answer}

Is this answer meaningfully supported by the context (not just general knowledge)?
Answer with ONLY "YES" or "NO"."""

_COT_GENERATE_PROMPT = """{system}

{context}

---
Think step by step before answering:
1. What does the user's context tell me about their current situation and goals?
2. What is the user specifically asking?
3. What is the most helpful, actionable response given their goals?

User: {query}

Answer:"""

_WEB_GENERATE_PROMPT = """{system}

{context}

Additional information retrieved from the web:
{web_results}

---
Think step by step before answering:
1. What from the user's context and the web results is relevant here?
2. What is the user specifically asking?
3. Synthesise a concise, actionable answer.

User: {query}

Answer:"""


# ── State ──────────────────────────────────────────────────────────────────────
class AgentState(TypedDict):
    user_id:          int
    session_id:       str
    query:            str
    context_md:       str
    context_relevant: bool
    web_results:      str
    answer:           str
    strategy:         str
    kg_nodes_used:    int
    latency_ms:       float


# ── Node helpers ───────────────────────────────────────────────────────────────
def _gemini(prompt: str) -> str:
    """Universal LLM call wrapper — supports Gemini, OpenAI, Claude, Groq, and Local models."""
    try:
        provider = get_llm_provider()
        return provider.generate(prompt).strip()
    except Exception as e:
        print(f"[CRAG] LLM error: {e}")
        return ""


# ── Graph nodes ────────────────────────────────────────────────────────────────
def extract_entities_node(state: AgentState) -> AgentState:
    """Extract facts/goals from the user message and write them into the KG."""
    extract_and_update_kg(state["query"], state["user_id"])
    return state


def retrieve_context_node(state: AgentState) -> AgentState:
    """Build a hybrid markdown context brief from the KG + Document Knowledge Base."""
    context_md, node_count = build_context_md(state["user_id"], query=state.get("query", ""))
    return {**state, "context_md": context_md, "kg_nodes_used": node_count}


def grade_context_node(state: AgentState) -> AgentState:
    """
    Gemini evaluator: is the KG context relevant to this query?
    If the KG is empty (first-time user) we still pass through to generate
    so the user gets a direct answer rather than an unnecessary web search.
    """
    if not state["context_md"]:
        # Empty KG → go to generate (direct strategy)
        return {**state, "context_relevant": True}

    verdict = _gemini(_GRADE_PROMPT.format(
        context=state["context_md"][:2000],
        question=state["query"],
    ))
    return {**state, "context_relevant": "YES" in verdict.upper()}


def generate_node(state: AgentState) -> AgentState:
    """Generate an answer using KG context with ReAct / Chain-of-Thought prompting."""
    strategy = "direct" if state["kg_nodes_used"] == 0 else "graph_hit"
    answer   = _gemini(_COT_GENERATE_PROMPT.format(
        system=_BASE_SYSTEM,
        context=state["context_md"] or "(No personal context yet.)",
        query=state["query"],
    ))
    if not answer:
        answer = "I couldn't generate a response right now. Please try again."
    return {**state, "answer": answer, "strategy": strategy}


def check_groundedness_node(state: AgentState) -> AgentState:
    """
    Self-reflection evaluator: is the answer actually grounded in the context?
    Only runs when context was used (not direct strategy).
    """
    if state["strategy"] == "direct" or not state["context_md"]:
        return state  # nothing to verify

    verdict = _gemini(_GROUNDEDNESS_PROMPT.format(
        context=state["context_md"][:2000],
        answer=state["answer"][:1500],
    ))
    if "NO" in verdict.upper():
        # Answer wasn't grounded — flag for web search
        return {**state, "strategy": "needs_web"}
    return state


def web_search_node(state: AgentState) -> AgentState:
    """Fallback: DuckDuckGo search, no API key required."""
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(state["query"], max_results=3))
        web_text = "\n\n".join(
            f"**{r['title']}**\n{r['body']}" for r in results
        )
    except Exception as e:
        print(f"[CRAG] Web search error: {e}")
        web_text = ""
    return {**state, "web_results": web_text, "strategy": "web_fallback"}


def generate_from_web_node(state: AgentState) -> AgentState:
    """Generate answer combining KG context and web search results."""
    answer = _gemini(_WEB_GENERATE_PROMPT.format(
        system=_BASE_SYSTEM,
        context=state["context_md"] or "(No personal context yet.)",
        web_results=state["web_results"][:3000] or "(No web results.)",
        query=state["query"],
    ))
    if not answer:
        answer = "I couldn't generate a response right now. Please try again."
    return {**state, "answer": answer}


# ── Conditional routing ────────────────────────────────────────────────────────
def route_after_grade(state: AgentState) -> Literal["generate", "web_search"]:
    return "generate" if state["context_relevant"] else "web_search"


def route_after_groundedness(state: AgentState) -> Literal["end", "web_search"]:
    return "web_search" if state.get("strategy") == "needs_web" else "end"


# ── Graph assembly ─────────────────────────────────────────────────────────────
def _build_graph():
    wf = StateGraph(AgentState)

    wf.add_node("extract_entities",    extract_entities_node)
    wf.add_node("retrieve_context",    retrieve_context_node)
    wf.add_node("grade_context",       grade_context_node)
    wf.add_node("generate",            generate_node)
    wf.add_node("check_groundedness",  check_groundedness_node)
    wf.add_node("web_search",          web_search_node)
    wf.add_node("generate_from_web",   generate_from_web_node)

    wf.set_entry_point("extract_entities")
    wf.add_edge("extract_entities",   "retrieve_context")
    wf.add_edge("retrieve_context",   "grade_context")

    wf.add_conditional_edges("grade_context", route_after_grade, {
        "generate":   "generate",
        "web_search": "web_search",
    })

    wf.add_edge("generate", "check_groundedness")
    wf.add_conditional_edges("check_groundedness", route_after_groundedness, {
        "end":        END,
        "web_search": "web_search",
    })

    wf.add_edge("web_search",        "generate_from_web")
    wf.add_edge("generate_from_web", END)

    # SQLite checkpointer — persists full AgentState per thread_id across restarts
    # Uses a separate file (checkpoints.db) to avoid FK conflicts with aurora.db
    try:
        import sqlite3
        from langgraph.checkpoint.sqlite import SqliteSaver
        _ckpt_path = os.path.join(os.path.dirname(DB_PATH), "checkpoints.db") \
                     if os.path.dirname(DB_PATH) else "checkpoints.db"
        _ckpt_conn = sqlite3.connect(_ckpt_path, check_same_thread=False)
        _ckpt_conn.execute("PRAGMA foreign_keys = OFF")
        _ckpt_conn.execute("PRAGMA journal_mode = WAL")
        checkpointer = SqliteSaver(_ckpt_conn)
        print("[CRAG] SqliteSaver checkpointer active.")
        return wf.compile(checkpointer=checkpointer)
    except Exception as e:
        print(f"[CRAG] Checkpointer unavailable ({e}), running without persistence.")
        return wf.compile()


# Singleton — built once on first import
_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = _build_graph()
    return _graph


# ── Public entry point ─────────────────────────────────────────────────────────
def run_agent(message: str, user_id: int, session_id: str) -> dict:
    """
    Run the CRAG agent for one user message.

    Returns a dict with at minimum:
      answer, strategy, kg_nodes_used, context_relevant, latency_ms
    """
    start = time.time()

    initial_state: AgentState = {
        "user_id":          user_id,
        "session_id":       session_id,
        "query":            message,
        "context_md":       "",
        "context_relevant": False,
        "web_results":      "",
        "answer":           "",
        "strategy":         "direct",
        "kg_nodes_used":    0,
        "latency_ms":       0.0,
    }

    config = {"configurable": {"thread_id": session_id}}

    try:
        result = get_graph().invoke(initial_state, config=config)
    except Exception as e:
        print(f"[CRAG] Graph error: {e}")
        result = {**initial_state, "answer": "Something went wrong. Please try again."}

    result["latency_ms"] = (time.time() - start) * 1000
    return result
