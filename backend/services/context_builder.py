"""
context_builder.py — Builds a structured markdown context brief from the KG and Document Knowledge Base.

This brief is injected into every Gemini prompt so the model reasons over
structured, goal-aware facts AND uploaded document knowledge instead of raw chat history.
"""

import json
from typing import Tuple
from services.kg_service import get_user_context
from services.document_service import search_document_chunks

_PRIORITY_ICON = {
    "urgent": "🔴",
    "high":   "🟠",
    "medium": "🟡",
    "low":    "🟢",
}

_RELATION_READABLE = {
    "COMPLETED":       "Completed",
    "STUDYING":        "Currently studying",
    "WEAK_AT":         "Weak at",
    "STRUGGLING_WITH": "Struggling with",
    "IMPROVED_AT":     "Improved at",
    "WORKING_ON":      "Working on",
    "STARTED":         "Started",
    "INTERESTED_IN":   "Interested in",
    "SKIPPED":         "Skipped",
    "AVOIDED":         "Avoiding",
    "TARGETS":         "Targeting",
    "ACHIEVED":        "Achieved",
    "COVERS":          "Covers",
    "PREREQUISITE_FOR":"Prerequisite for",
    "PART_OF":         "Part of",
    "RELATED_TO":      "Related to",
}


def build_context_md(user_id: int, query: str = "") -> Tuple[str, int]:
    """
    Build a hybrid markdown context brief from:
      1. User's Personal Knowledge Graph (goals, weaknesses, habits)
      2. Uploaded Document Knowledge Base (matching document sections/topic notes)

    Returns:
        (context_md: str, node_count: int)
    """
    data       = get_user_context(user_id)
    goals      = data.get("goals", [])
    facts      = data.get("facts", [])
    node_count = 0

    lines = []

    # ── 1. Personal Context: Goals ─────────────────────────────────────────────
    if goals:
        lines.append("# Active Goals\n")
        by_priority: dict = {}
        for g in goals:
            by_priority.setdefault(g["priority"], []).append(g)

        for priority in ["urgent", "high", "medium", "low"]:
            if priority not in by_priority:
                continue
            icon = _PRIORITY_ICON.get(priority, "•")
            lines.append(f"### {icon} {priority.capitalize()} Priority")
            for g in by_priority[priority]:
                try:
                    props = json.loads(g.get("properties") or "{}")
                except Exception:
                    props = {}
                line = f"- **{g['label']}**"
                if props.get("target"):
                    line += f" — target: {props['target']}"
                if props.get("deadline"):
                    line += f" (by {props['deadline']})"
                if g.get("source") == "api":
                    line += " ✓"
                lines.append(line)
                node_count += 1
            lines.append("")

    # ── 2. Personal Context: Facts & Topics ───────────────────────────────────
    if facts:
        lines.append("# What I Know About You\n")
        grouped: dict = {}
        for f in facts:
            grouped.setdefault(f["relation"], []).append(f["object"])

        for relation, objects in grouped.items():
            readable = _RELATION_READABLE.get(relation, relation.replace("_", " ").capitalize())
            unique_objects = list(dict.fromkeys(objects))[:6]
            lines.append(f"- **{readable}**: {', '.join(unique_objects)}")
            node_count += len(unique_objects)
        lines.append("")

    # ── 3. Document Knowledge Base (Hybrid GraphRAG) ──────────────────────────
    if query:
        doc_chunks = search_document_chunks(query, user_id, top_k=2)
        if doc_chunks:
            lines.append("# Relevant Study Material & Documents\n")
            for chunk in doc_chunks:
                doc_title = chunk.get("doc_title") or "Uploaded Document"
                topic = chunk.get("topic") or "Topic"
                content = chunk.get("content", "").strip()
                # Truncate content to avoid overwhelming context window
                preview = content[:800] + ("..." if len(content) > 800 else "")
                lines.append(f"### 📄 [{doc_title}] > {topic}")
                lines.append(f"{preview}\n")
                node_count += 1

    if not lines:
        return "", 0

    return "\n".join(lines), node_count
