"""
context_builder.py — Builds a structured markdown context brief from the KG.

This brief is injected into every Gemini prompt so the model reasons over
structured, goal-aware facts instead of raw chat history.
"""

import json
from services.kg_service import get_user_context

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
}


def build_context_md(user_id: int) -> tuple:
    """
    Build a markdown context brief from the user's knowledge graph.

    Returns:
        (context_md: str, node_count: int)
        context_md  — formatted markdown string ready for prompt injection
        node_count  — total KG items used (for MLflow tracking)
    """
    data       = get_user_context(user_id)
    goals      = data["goals"]
    facts      = data["facts"]
    node_count = 0

    if not goals and not facts:
        return "", 0

    lines = ["# Your Personal Context\n"]

    # ── Goals section ──────────────────────────────────────────────────────────
    if goals:
        lines.append("## Active Goals\n")
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
                # Mark explicitly-set goals with a checkmark
                if g.get("source") == "api":
                    line += " ✓"
                lines.append(line)
                node_count += 1
            lines.append("")

    # ── Facts section ──────────────────────────────────────────────────────────
    if facts:
        lines.append("## What I Know About You\n")
        # Group by relation type
        grouped: dict = {}
        for f in facts:
            grouped.setdefault(f["relation"], []).append(f["object"])

        for relation, objects in grouped.items():
            readable = _RELATION_READABLE.get(relation, relation.replace("_", " ").capitalize())
            # Deduplicate and cap at 6 items per relation
            unique_objects = list(dict.fromkeys(objects))[:6]
            lines.append(f"- **{readable}**: {', '.join(unique_objects)}")
            node_count += len(unique_objects)

    return "\n".join(lines), node_count

