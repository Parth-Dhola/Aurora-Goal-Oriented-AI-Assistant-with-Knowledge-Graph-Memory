"""
routes/kg.py — Knowledge Graph API

Endpoints:
  GET  /api/kg/nodes          — all KG nodes for the current user
  GET  /api/kg/edges          — all KG edges for the current user
  GET  /api/kg/export/obsidian — download .zip of Obsidian-compatible .md files
"""

import io
import json
import zipfile
from datetime import datetime
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from models.database import get_db
from services.auth_service import get_current_user

router = APIRouter()

_PRIORITY_ICON = {"urgent": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
_RELATION_READABLE = {
    "COMPLETED":       "Completed",
    "STUDYING":        "Studying",
    "WEAK_AT":         "Weak at",
    "STRUGGLING_WITH": "Struggling with",
    "IMPROVED_AT":     "Improved at",
    "WORKING_ON":      "Working on",
    "STARTED":         "Started",
    "INTERESTED_IN":   "Interested in",
    "SKIPPED":         "Skipped",
    "AVOIDED":         "Avoiding",
    "TARGETS":         "Targets",
    "ACHIEVED":        "Achieved",
}


@router.get("/nodes")
async def get_kg_nodes(user: dict = Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM kg_nodes WHERE user_id=? ORDER BY type, priority, label",
        (user["id"],)
    ).fetchall()
    conn.close()
    return {"nodes": [dict(r) for r in rows]}


@router.get("/edges")
async def get_kg_edges(user: dict = Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute("""
        SELECT e.id, e.relation, e.weight, e.context, e.created_at,
               n1.label AS source_label, n2.label AS target_label
        FROM   kg_edges e
        JOIN   kg_nodes n1 ON e.source_id = n1.id
        JOIN   kg_nodes n2 ON e.target_id = n2.id
        WHERE  e.user_id=?
        ORDER BY e.weight DESC
    """, (user["id"],)).fetchall()
    conn.close()
    return {"edges": [dict(r) for r in rows]}


# ── Obsidian export ────────────────────────────────────────────────────────────
def _safe_filename(label: str) -> str:
    """Make a label safe for use as a filename."""
    return "".join(c if c.isalnum() or c in " _-" else "_" for c in label).strip()


def _build_node_md(node: dict, edges_from: list, edges_to: list) -> str:
    """Generate Obsidian-compatible markdown for one KG node."""
    label    = node["label"]
    ntype    = node["type"]
    priority = node.get("priority", "medium")
    status   = node.get("status", "active")
    source   = node.get("source", "chat")

    try:
        props = json.loads(node.get("properties") or "{}")
    except Exception:
        props = {}

    lines = []
    # YAML frontmatter — Dataview-compatible
    lines += [
        "---",
        f"aurora_type: {ntype}",
        f"priority: {priority}",
        f"status: {status}",
        f"source: {source}",
        f"tags: [aurora, {ntype}, {priority}]",
        f"created: {node.get('created_at', '')}",
        "---",
        "",
        f"# {label}",
        "",
    ]

    # Properties block (for goals)
    if ntype == "goal":
        icon = _PRIORITY_ICON.get(priority, "•")
        lines.append(f"**Priority:** {icon} {priority.capitalize()}")
        if props.get("target"):
            lines.append(f"**Target:** {props['target']}")
        if props.get("deadline"):
            lines.append(f"**Deadline:** {props['deadline']}")
        lines.append(f"**Source:** {'Explicitly set ✓' if source == 'api' else 'Extracted from chat'}")
        lines.append("")

    # Outgoing connections
    if edges_from:
        lines.append("## 🔗 Connections\n")
        for e in edges_from:
            relation  = _RELATION_READABLE.get(e["relation"], e["relation"])
            weight    = e.get("weight", 1.0)
            ctx       = f" — _{e['context']}_" if e.get("context") else ""
            target_fn = _safe_filename(e["target_label"])
            lines.append(f"- [[{target_fn}]] — **{relation}** (strength: {weight:.1f}){ctx}")
        lines.append("")

    # Incoming connections
    if edges_to:
        lines.append("## ↩ Referenced by\n")
        for e in edges_to:
            relation  = _RELATION_READABLE.get(e["relation"], e["relation"])
            source_fn = _safe_filename(e["source_label"])
            lines.append(f"- [[{source_fn}]] — {relation}")
        lines.append("")

    lines.append(f"---\n_Last updated: {node.get('updated_at', node.get('created_at', ''))}_")
    return "\n".join(lines)


def _build_overview_md(nodes: list, edges: list, docs: list = None) -> str:
    """Generate an _Overview.md index for the whole KG."""
    goals   = [n for n in nodes if n["type"] == "goal"  and n.get("status") == "active"]
    topics  = [n for n in nodes if n["type"] == "topic"]
    facts   = [n for n in nodes if n["type"] not in ("goal", "topic", "person", "document")]
    docs    = docs or []

    lines = [
        "# 🌟 Aurora Knowledge Graph\n",
        f"_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_\n",
        f"**{len(nodes)} nodes** · **{len(edges)} connections**\n",
    ]

    if goals:
        lines.append("## 🎯 Active Goals\n")
        for g in sorted(goals, key=lambda x: ["urgent","high","medium","low"].index(x.get("priority","medium")) if x.get("priority","medium") in ["urgent","high","medium","low"] else 99):
            icon = _PRIORITY_ICON.get(g["priority"], "•")
            fn   = _safe_filename(g["label"])
            lines.append(f"- {icon} [[{fn}]]")
        lines.append("")

    if docs:
        lines.append("## 📄 Uploaded Documents & Notes\n")
        for d in docs:
            fn = _safe_filename(d["title"])
            lines.append(f"- 📖 [[{fn}]] — _{d.get('summary', '')}_")
        lines.append("")

    if topics:
        lines.append("## 📚 Topics & Skills\n")
        for t in sorted(topics, key=lambda x: x["label"]):
            fn = _safe_filename(t["label"])
            lines.append(f"- [[{fn}]]")
        lines.append("")

    if facts:
        lines.append("## 🔹 Other Facts\n")
        for f in facts:
            fn = _safe_filename(f["label"])
            lines.append(f"- [[{fn}]]")
        lines.append("")

    lines += [
        "---",
        "## 📊 Dataview Queries\n",
        "### All urgent goals",
        "```dataview",
        'TABLE priority, target, deadline FROM #aurora WHERE aurora_type = "goal" AND priority = "urgent"',
        "```\n",
        "### Recently studied topics",
        "```dataview",
        'TABLE created FROM #aurora WHERE aurora_type = "topic" SORT created DESC LIMIT 10',
        "```",
    ]
    return "\n".join(lines)


@router.get("/export/obsidian")
async def export_obsidian(user: dict = Depends(get_current_user)):
    """
    Download a ZIP of Obsidian-compatible markdown files.

    In Obsidian:
      1. File > Open Vault > select any folder
      2. Unzip the downloaded file into that folder
      3. Open Graph View — nodes and wikilinks appear immediately
      4. Install 'Dataview' plugin to use the query blocks in _Overview.md
    """
    conn  = get_db()
    nodes = [dict(r) for r in conn.execute(
        "SELECT * FROM kg_nodes WHERE user_id=? ORDER BY type, label",
        (user["id"],)
    ).fetchall()]
    edges_raw = [dict(r) for r in conn.execute("""
        SELECT e.*, n1.label AS source_label, n2.label AS target_label
        FROM   kg_edges e
        JOIN   kg_nodes n1 ON e.source_id = n1.id
        JOIN   kg_nodes n2 ON e.target_id = n2.id
        WHERE  e.user_id=?
    """, (user["id"],)).fetchall()]

    docs = [dict(r) for r in conn.execute(
        "SELECT id, filename, title, summary FROM documents WHERE user_id=?",
        (user["id"],)
    ).fetchall()]

    doc_chunks = [dict(r) for r in conn.execute("""
        SELECT c.topic, c.content, d.title as doc_title, d.filename
        FROM document_chunks c
        JOIN documents d ON c.document_id = d.id
        WHERE c.user_id = ?
    """, (user["id"],)).fetchall()]
    conn.close()

    # Index edges by node id
    edges_from: dict = {}  # source_id → [edge]
    edges_to:   dict = {}  # target_id → [edge]
    for e in edges_raw:
        edges_from.setdefault(e["source_id"], []).append(e)
        edges_to.setdefault(e["target_id"], []).append(e)

    # Build ZIP in memory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Overview
        zf.writestr("Aurora KG/_Overview.md", _build_overview_md(nodes, edges_raw, docs))
        # One file per node, organised into subfolders by type
        for node in nodes:
            if node["type"] == "person":
                continue  # skip the root user node
            folder = {
                "goal":  "Goals",
                "topic": "Topics",
            }.get(node["type"], "Facts")
            fn      = _safe_filename(node["label"])
            content = _build_node_md(
                node,
                edges_from=edges_from.get(node["id"], []),
                edges_to=edges_to.get(node["id"], []),
            )
            zf.writestr(f"Aurora KG/{folder}/{fn}.md", content)

        # Include document topic notes
        for dc in doc_chunks:
            doc_folder = _safe_filename(dc["doc_title"])
            topic_fn   = _safe_filename(dc["topic"])
            frontmatter = (
                "---\n"
                f"aurora_type: document_topic\n"
                f"document: \"{dc['doc_title']}\"\n"
                f"tags: [aurora, study, document, {doc_folder.lower()}]\n"
                f"source: \"{dc['filename']}\"\n"
                "---\n\n"
            )
            zf.writestr(f"Aurora KG/Documents/{doc_folder}/{topic_fn}.md", frontmatter + dc["content"])

    buf.seek(0)
    filename = f"aurora_kg_{datetime.now().strftime('%Y%m%d_%H%M')}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
