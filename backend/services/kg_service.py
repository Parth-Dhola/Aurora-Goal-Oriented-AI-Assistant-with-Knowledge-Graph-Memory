"""
kg_service.py — Knowledge Graph operations

Handles:
  - Entity / goal extraction from chat messages (via Gemini)
  - Creating / updating KG nodes and edges in SQLite
  - Querying the graph to retrieve user context
"""

import os
import json
from dotenv import load_dotenv
from models.database import get_db
from services.llm_provider import get_llm_provider

load_dotenv()

# ── Extraction prompt ──────────────────────────────────────────────────────────
EXTRACTION_PROMPT = '''Analyze the following message and extract structured information.

Message: "{message}"

Return ONLY valid JSON (no markdown, no explanation) with this exact structure:
{{
  "facts": [
    {{
      "relation": "RELATION_TYPE",
      "object": "short label for what the subject did/has/is",
      "context": "optional brief context string"
    }}
  ],
  "goals": [
    {{
      "label": "concise goal name (3-6 words max)",
      "priority": "low|medium|high|urgent",
      "confidence": 0.1,
      "target": "optional measurable target or null",
      "deadline": "optional deadline string or null"
    }}
  ]
}}

Valid relations:
  COMPLETED, STUDYING, WEAK_AT, TARGETS, SKIPPED, ACHIEVED,
  STARTED, STRUGGLING_WITH, WORKING_ON, INTERESTED_IN, AVOIDED, IMPROVED_AT

Extraction rules:
- "I finished the Docker module"   → fact: relation=COMPLETED, object="Docker Module"
- "I keep struggling with DP"      → fact: relation=STRUGGLING_WITH, object="Dynamic Programming"
- "I want to lose 10kg by December"→ goal: label="Lose Weight", priority=medium, target="10kg", deadline="December"
- "placement is very important"    → goal: label="Placement Prep", priority=urgent, confidence=0.9
- "I want to eventually learn guitar" → goal: label="Learn Guitar", priority=low, confidence=0.6
- "ok thanks" / small talk         → return {{"facts": [], "goals": []}}
- Extract only what THIS message states — do not invent background knowledge.
'''

# ── JSON helpers ───────────────────────────────────────────────────────────────
def _parse_json(text: str) -> dict:
    text = text.strip()
    # Strip markdown code fences
    if "```" in text:
        parts = text.split("```")
        for p in parts:
            p = p.strip()
            if p.startswith("json"):
                p = p[4:]
            p = p.strip()
            if p.startswith("{"):
                text = p
                break
    # Find first JSON object
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        text = match.group()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"facts": [], "goals": []}


# ── Node / edge helpers ────────────────────────────────────────────────────────
def get_or_create_user_node(user_id: int) -> int:
    """Return the root 'person' node id for this user, creating it if needed."""
    conn = get_db()
    row = conn.execute(
        "SELECT id FROM kg_nodes WHERE user_id=? AND type='person' AND label='user'",
        (user_id,)
    ).fetchone()
    if row:
        nid = row["id"]
        conn.close()
        return nid
    cur = conn.execute(
        "INSERT INTO kg_nodes (user_id, type, label, properties) VALUES (?, 'person', 'user', '{}')",
        (user_id,)
    )
    conn.commit()
    nid = cur.lastrowid
    conn.close()
    return nid


def get_or_create_node(user_id: int, type_: str, label: str) -> int:
    """Return existing node id or create a new one (case-insensitive label match)."""
    conn = get_db()
    row = conn.execute(
        "SELECT id FROM kg_nodes WHERE user_id=? AND type=? AND LOWER(label)=LOWER(?)",
        (user_id, type_, label)
    ).fetchone()
    if row:
        nid = row["id"]
        conn.close()
        return nid
    cur = conn.execute(
        "INSERT INTO kg_nodes (user_id, type, label, properties) VALUES (?, ?, ?, '{}')",
        (user_id, type_, label)
    )
    conn.commit()
    nid = cur.lastrowid
    conn.close()
    return nid


def add_or_strengthen_edge(user_id: int, source_id: int, target_id: int,
                           relation: str, context: str = "") -> None:
    """Add edge between nodes, or increase its weight if it already exists."""
    conn = get_db()
    existing = conn.execute(
        "SELECT id, weight FROM kg_edges WHERE user_id=? AND source_id=? AND target_id=? AND relation=?",
        (user_id, source_id, target_id, relation)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE kg_edges SET weight=weight+0.1, context=? WHERE id=?",
            (context or "", existing["id"])
        )
    else:
        conn.execute(
            "INSERT INTO kg_edges (user_id, source_id, target_id, relation, context) VALUES (?,?,?,?,?)",
            (user_id, source_id, target_id, relation, context)
        )
    conn.commit()
    conn.close()


def create_goal_node(user_id: int, label: str, priority: str,
                     source: str = "chat",
                     target: str = None, deadline: str = None) -> int:
    """Create or update a goal node. Returns the node id."""
    props = json.dumps({"target": target, "deadline": deadline})
    conn = get_db()
    existing = conn.execute(
        "SELECT id FROM kg_nodes WHERE user_id=? AND type='goal' AND LOWER(label)=LOWER(?)",
        (user_id, label)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE kg_nodes SET priority=?, properties=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (priority, props, existing["id"])
        )
        conn.commit()
        nid = existing["id"]
        conn.close()
        return nid
    cur = conn.execute(
        "INSERT INTO kg_nodes (user_id, type, label, priority, source, properties) VALUES (?,?,?,?,?,?)",
        (user_id, "goal", label, priority, source, props)
    )
    conn.commit()
    nid = cur.lastrowid
    conn.close()
    return nid


# ── Main extraction function ───────────────────────────────────────────────────
_RELATION_TYPE_MAP = {
    "COMPLETED":       "topic",
    "STUDYING":        "topic",
    "WEAK_AT":         "topic",
    "STRUGGLING_WITH": "topic",
    "IMPROVED_AT":     "topic",
    "WORKING_ON":      "topic",
    "STARTED":         "topic",
    "INTERESTED_IN":   "topic",
    "SKIPPED":         "topic",
    "AVOIDED":         "topic",
    "TARGETS":         "goal",
    "ACHIEVED":        "goal",
}


def extract_and_update_kg(message: str, user_id: int) -> dict:
    """
    Call Gemini to extract facts/goals from a message,
    then persist them into the knowledge graph.
    Returns the raw extracted dict for logging.
    """
    try:
        provider = get_llm_provider()
        prompt = EXTRACTION_PROMPT.format(message=message)
        extracted = provider.generate_json(prompt)
        if not extracted:
            extracted = _parse_json(provider.generate(prompt))
    except Exception as e:
        print(f"[KG] Extraction error: {e}")
        return {"facts": [], "goals": []}

    user_node = get_or_create_user_node(user_id)

    # Persist facts as edges
    for fact in extracted.get("facts", []):
        relation = str(fact.get("relation", "")).upper().strip()
        obj      = str(fact.get("object", "")).strip()
        ctx      = str(fact.get("context", "")).strip()
        if not relation or not obj:
            continue
        node_type = _RELATION_TYPE_MAP.get(relation, "fact")
        obj_node  = get_or_create_node(user_id, node_type, obj)
        add_or_strengthen_edge(user_id, user_node, obj_node, relation, ctx)

    # Persist goals (confidence threshold = 0.5)
    for goal in extracted.get("goals", []):
        if float(goal.get("confidence", 0)) < 0.5:
            continue
        label = str(goal.get("label", "")).strip()
        if not label:
            continue
        create_goal_node(
            user_id=user_id,
            label=label,
            priority=goal.get("priority", "medium"),
            source="chat",
            target=goal.get("target"),
            deadline=goal.get("deadline"),
        )

    return extracted


# ── Context retrieval ──────────────────────────────────────────────────────────
def get_user_context(user_id: int) -> dict:
    """
    Retrieve all active goals and top facts from the KG for a user.
    Returns a dict with 'goals' and 'facts' lists.
    """
    conn = get_db()

    goals = conn.execute("""
        SELECT id, label, priority, status, source, properties
        FROM   kg_nodes
        WHERE  user_id=? AND type='goal' AND status='active'
        ORDER BY CASE priority
            WHEN 'urgent' THEN 1 WHEN 'high'   THEN 2
            WHEN 'medium' THEN 3 WHEN 'low'    THEN 4
            ELSE 5 END
    """, (user_id,)).fetchall()

    facts = conn.execute("""
        SELECT n2.label AS object, e.relation, e.weight, e.context, e.created_at
        FROM   kg_edges  e
        JOIN   kg_nodes  n1 ON e.source_id = n1.id
        JOIN   kg_nodes  n2 ON e.target_id = n2.id
        WHERE  e.user_id=? AND n1.label='user'
        ORDER BY e.weight DESC, e.created_at DESC
        LIMIT 25
    """, (user_id,)).fetchall()

    conn.close()
    return {
        "goals": [dict(g) for g in goals],
        "facts": [dict(f) for f in facts],
    }

