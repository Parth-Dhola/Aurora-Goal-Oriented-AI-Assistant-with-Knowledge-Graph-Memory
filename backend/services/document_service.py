"""
document_service.py — Deep Hierarchical Knowledge Graph & Obsidian Study Notes Engine for Documents & Books

Flow:
  1. Extract text from uploaded PDF/TXT using pypdf.
  2. Prompt Gemini (acting as a Knowledge Graph Architect) to extract:
     - Hierarchical multi-topic breakdown with in-depth study notes
     - Rich concept, algorithm, and data structure nodes
     - Directed semantic edges (PREREQUISITE_FOR, USES, OPTIMIZES, SOLVES, VARIATION_OF, PART_OF)
     - Interconnected [[wikilinks]] across all topics
  3. Save topic notes into obsidian-KG-vault/Documents/<DocName>/<Topic>.md
  4. Store chunks in SQLite document_chunks + document_chunks_fts.
  5. Inject rich nodes and edges into SQLite kg_nodes and kg_edges.
"""

import io
import os
import re
import json
from pathlib import Path
from typing import List, Dict, Any, Tuple
import pypdf
from dotenv import load_dotenv

from models.database import get_db
from services.kg_service import get_or_create_node, add_or_strengthen_edge
from services.llm_provider import get_llm_provider

load_dotenv()

# Path to project's Obsidian vault
_BACKEND_DIR = Path(__file__).parent.parent.resolve()
PROJECT_ROOT = _BACKEND_DIR.parent if (_BACKEND_DIR / "app.py").exists() and _BACKEND_DIR.name == "backend" else _BACKEND_DIR
VAULT_DOCS_DIR = PROJECT_ROOT / "obsidian-KG-vault" / "Documents"


def _safe_filename(name: str) -> str:
    """Sanitize strings for safe filenames and Obsidian links."""
    return "".join(c if c.isalnum() or c in " _-" else "_" for c in name).strip()


def extract_text_from_pdf(pdf_bytes: bytes, filename: str = "") -> Tuple[str, int]:
    """Extract raw text and page count from a PDF or text file in memory."""
    if filename.lower().endswith(".txt"):
        return pdf_bytes.decode("utf-8", errors="ignore"), 1

    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        total_pages = len(reader.pages)
        pages_text = []
        max_extract = min(total_pages, 100)
        for i in range(max_extract):
            try:
                page = reader.pages[i]
                text = page.extract_text() or ""
                if text.strip():
                    pages_text.append(f"--- [Page {i+1}] ---\n{text}")
            except Exception:
                continue
        full_text = "\n\n".join(pages_text)
        return full_text, max(total_pages, 1)
    except Exception:
        return pdf_bytes.decode("utf-8", errors="ignore"), 1


_DEEP_DOCUMENT_PROMPT = """You are a Senior Knowledge Graph Architect and University Professor.
Analyze the following textbook/document and perform a comprehensive, deep knowledge decomposition.

Document Filename: {filename}
Document Content:
{content}

Extract a rich, multi-layered Knowledge Graph and comprehensive study notes that do complete justice to this material.

Return ONLY valid JSON (no markdown fences, no conversational text) with this exact schema:
{{
  "title": "Clear, Professional Document Title",
  "summary": "3-4 sentence comprehensive overview of the core principles, methodologies, and value of this document.",
  "topics": [
    {{
      "topic_name": "Specific Topic / Chapter Name",
      "summary": "1-2 sentence topic summary",
      "markdown_content": "# Topic Title\\n\\n## 📌 Core Overview\\nDetailed conceptual explanation with clear depth...\\n\\n## ⚙️ Algorithms, Theorems & Mathematical Formulations\\nDetailed step-by-step breakdown. Include LaTeX formulas (e.g. $O(V + E \\\\log V)$, $\\\\sum$) and pseudocode where relevant.\\n\\n## 🔗 Interconnections & Prerequisites\\n- Prerequisite concepts: [[Concept A]], [[Concept B]]\\n- Solves problem classes: [[Problem Class X]]\\n- Related techniques: [[Technique Y]]\\n\\n## 💡 Key Takeaways & Exam/Interview Tips\\n- Key takeaway 1\\n- Key takeaway 2",
      "key_concepts": ["Concept 1", "Concept 2", "Algorithm 1"]
    }}
  ],
  "graph_nodes": [
    {{"label": "Core Topic", "type": "topic", "priority": "high"}},
    {{"label": "Specific Algorithm / Method", "type": "algorithm", "priority": "high"}},
    {{"label": "Underlying Data Structure", "type": "datastructure", "priority": "medium"}},
    {{"label": "Fundamental Concept / Theorem", "type": "concept", "priority": "medium"}},
    {{"label": "Problem Class Solved", "type": "problem_class", "priority": "medium"}}
  ],
  "graph_edges": [
    {{"source": "Concept A", "target": "Concept B", "relation": "PREREQUISITE_FOR", "context": "Detailed explanation of relationship"}},
    {{"source": "Algorithm X", "target": "DataStructure Y", "relation": "USES", "context": "Uses Y for efficient lookup"}},
    {{"source": "Algorithm X", "target": "ProblemClass Z", "relation": "SOLVES", "context": "Optimal solution for Z"}},
    {{"source": "Technique M", "target": "Technique N", "relation": "OPTIMIZES", "context": "Reduces time from exponential to polynomial"}},
    {{"source": "Variation 1", "target": "Base Problem", "relation": "VARIATION_OF", "context": "Generalizes base problem with constraints"}},
    {{"source": "Subtopic", "target": "Main Domain", "relation": "PART_OF", "context": "Core module of domain"}}
  ]
}}

Guidelines:
1. Extract 4 to 10 comprehensive topics covering all major sections of the document.
2. Extract 15 to 30 graph nodes and 15 to 35 rich directed edges.
3. In `markdown_content`, ensure thorough, educational depth with extensive `[[wikilinks]]` so that Obsidian Graph View blooms into an interconnected network of knowledge.
4. Strictly valid JSON output only.
"""


def _parse_json(text: str) -> dict:
    text = text.strip()
    if "```" in text:
        parts = text.split("```")
        for p in parts:
            p = p.strip()
            if p.startswith("json"):
                p = p[4:].strip()
            if p.startswith("{"):
                text = p
                break
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        text = match.group()
    try:
        return json.loads(text)
    except Exception:
        return {"title": "Uploaded Document", "summary": "", "topics": [], "graph_nodes": [], "graph_edges": []}


def process_and_graph_document(pdf_bytes: bytes, filename: str, user_id: int) -> Dict[str, Any]:
    """
    Process PDF / Document:
      1. Extract text across pages
      2. Call Gemini for deep hierarchical Knowledge Graph & Obsidian Markdown generation
      3. Save metadata to DB
      4. Save topic Markdown files to Obsidian vault with wikilinks
      5. Add dense nodes and edges to Knowledge Graph
      6. Index chunks for Hybrid RAG search
    """
    raw_text, total_pages = extract_text_from_pdf(pdf_bytes, filename=filename)
    file_size = len(pdf_bytes)

    # Sample up to 20,000 characters across document (beginning, middle, end) if large
    if len(raw_text) > 20000:
        chunk_size = 6500
        content_sample = (
            raw_text[:chunk_size] +
            "\n\n... [Middle Sections] ...\n\n" +
            raw_text[len(raw_text)//2 - chunk_size//2 : len(raw_text)//2 + chunk_size//2] +
            "\n\n... [Concluding Sections] ...\n\n" +
            raw_text[-chunk_size:]
        )
    else:
        content_sample = raw_text

    prompt = _DEEP_DOCUMENT_PROMPT.format(
        filename=filename,
        content=content_sample if content_sample.strip() else "(Empty document content)"
    )

    try:
        provider = get_llm_provider()
        structured = provider.generate_json(prompt)
        if not structured or not structured.get("topics"):
            structured = _parse_json(provider.generate(prompt))
    except Exception as e:
        print(f"[DocumentService] LLM decomposition error: {e}")
        structured = {}

    if not structured or not structured.get("topics"):
        clean_name = filename.rsplit(".", 1)[0].replace("_", " ").title()
        structured = {
            "title": (structured.get("title") if structured else None) or clean_name,
            "summary": (structured.get("summary") if structured else None) or "Document uploaded and indexed successfully.",
            "topics": [
                {
                    "topic_name": clean_name,
                    "summary": f"Core notes for {clean_name}",
                    "markdown_content": f"# {clean_name}\n\n{raw_text[:3000]}",
                    "key_concepts": []
                }
            ],
            "graph_nodes": [{"label": clean_name, "type": "topic", "priority": "high"}],
            "graph_edges": []
        }

    title = structured.get("title") or filename.rsplit(".", 1)[0]
    summary = structured.get("summary") or ""
    topics = structured.get("topics") or []

    # 1. Insert into documents table
    conn = get_db()
    cur = conn.execute(
        """
        INSERT INTO documents (user_id, filename, title, summary, total_pages, file_size)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, filename, title, summary, total_pages, file_size)
    )
    doc_id = cur.lastrowid
    conn.commit()

    # 2. Save topics as Obsidian Markdown files and database chunks
    safe_doc_folder = _safe_filename(title)
    doc_vault_path = VAULT_DOCS_DIR / safe_doc_folder
    try:
        doc_vault_path.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"[DocumentService] Vault folder creation error: {e}")

    for idx, topic in enumerate(topics):
        topic_name = topic.get("topic_name") or f"Topic_{idx+1}"
        content_md = topic.get("markdown_content") or f"# {topic_name}\n\n{topic.get('summary', '')}"
        
        # Build YAML frontmatter for Obsidian note
        frontmatter = (
            "---\n"
            f"aurora_type: document_topic\n"
            f"document: \"{title}\"\n"
            f"tags: [aurora, study, document, {safe_doc_folder.lower()}]\n"
            f"source: \"{filename}\"\n"
            "---\n\n"
        )
        full_note_content = frontmatter + content_md

        # Write to Obsidian vault
        try:
            note_file = doc_vault_path / f"{_safe_filename(topic_name)}.md"
            note_file.write_text(full_note_content, encoding="utf-8")
        except Exception as e:
            print(f"[DocumentService] Failed to write Obsidian note: {e}")

        # Store in document_chunks
        c_cur = conn.execute(
            """
            INSERT INTO document_chunks (document_id, user_id, topic, content, page_number)
            VALUES (?, ?, ?, ?, ?)
            """,
            (doc_id, user_id, topic_name, content_md, idx + 1)
        )
        chunk_id = c_cur.lastrowid

        # Index in FTS5
        try:
            conn.execute(
                "INSERT INTO document_chunks_fts (chunk_id, user_id, topic, content) VALUES (?, ?, ?, ?)",
                (chunk_id, user_id, topic_name, content_md)
            )
        except Exception:
            pass

    conn.commit()

    # 3. Add Deep Graph Nodes & Semantic Edges
    doc_node_id = get_or_create_node(user_id, "document", title)
    
    # Process graph nodes
    for node_def in structured.get("graph_nodes", []):
        lbl = node_def.get("label")
        ntype = node_def.get("type", "topic")
        priority = node_def.get("priority", "medium")
        if lbl:
            nid = get_or_create_node(user_id, ntype, lbl)
            add_or_strengthen_edge(user_id, doc_node_id, nid, "COVERS", f"Topic in {title}")

    # Process graph edges
    for edge_def in structured.get("graph_edges", []):
        src = edge_def.get("source")
        tgt = edge_def.get("target")
        rel = edge_def.get("relation", "RELATED_TO")
        ctx = edge_def.get("context", "")
        if src and tgt:
            src_id = get_or_create_node(user_id, "topic", src)
            tgt_id = get_or_create_node(user_id, "topic", tgt)
            add_or_strengthen_edge(user_id, src_id, tgt_id, rel, ctx)

    # 4. Link Document to Active Goals
    active_goals = conn.execute(
        "SELECT id, label FROM kg_nodes WHERE user_id=? AND type='goal' AND status='active'",
        (user_id,)
    ).fetchall()
    for g in active_goals:
        # Link goals to document
        add_or_strengthen_edge(user_id, g["id"], doc_node_id, "STUDIES", f"Study material for {g['label']}")

    conn.close()

    return {
        "id": doc_id,
        "filename": filename,
        "title": title,
        "summary": summary,
        "total_pages": total_pages,
        "topics_created": len(topics),
        "nodes_created": len(structured.get("graph_nodes", [])),
        "edges_created": len(structured.get("graph_edges", [])),
        "vault_folder": str(doc_vault_path)
    }


def search_document_chunks(query: str, user_id: int, top_k: int = 3) -> List[Dict[str, Any]]:
    """
    Search document notes and chunks for relevant context.
    Attempts FTS5 full-text search first, falls back to keyword matching.
    """
    conn = get_db()
    results = []

    words = [w for w in re.findall(r'\w+', query) if len(w) > 2]
    if not words:
        conn.close()
        return []

    try:
        fts_query = " OR ".join(words)
        rows = conn.execute(
            """
            SELECT c.id, c.document_id, c.topic, c.content, d.title AS doc_title
            FROM document_chunks_fts f
            JOIN document_chunks c ON f.chunk_id = c.id
            JOIN documents d ON c.document_id = d.id
            WHERE f.user_id = ? AND document_chunks_fts MATCH ?
            LIMIT ?
            """,
            (user_id, fts_query, top_k)
        ).fetchall()
        for r in rows:
            results.append(dict(r))
    except Exception:
        like_clauses = " OR ".join(["c.content LIKE ? OR c.topic LIKE ?" for _ in words])
        params = [user_id]
        for w in words:
            params.extend([f"%{w}%", f"%{w}%"])
        params.append(top_k)
        
        sql = f"""
            SELECT c.id, c.document_id, c.topic, c.content, d.title AS doc_title
            FROM document_chunks c
            JOIN documents d ON c.document_id = d.id
            WHERE c.user_id = ? AND ({like_clauses})
            ORDER BY c.id DESC
            LIMIT ?
        """
        try:
            rows = conn.execute(sql, params).fetchall()
            for r in rows:
                results.append(dict(r))
        except Exception as e:
            print(f"[DocumentService] Search fallback error: {e}")

    conn.close()
    return results


def list_user_documents(user_id: int) -> List[Dict[str, Any]]:
    """List all uploaded documents for a given user."""
    conn = get_db()
    rows = conn.execute(
        """
        SELECT id, filename, title, summary, total_pages, file_size, created_at
        FROM documents
        WHERE user_id = ?
        ORDER BY created_at DESC
        """,
        (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_document_details(doc_id: int, user_id: int) -> Dict[str, Any]:
    """Get document details with its topic notes."""
    conn = get_db()
    doc = conn.execute(
        "SELECT * FROM documents WHERE id = ? AND user_id = ?",
        (doc_id, user_id)
    ).fetchone()
    if not doc:
        conn.close()
        return None

    chunks = conn.execute(
        "SELECT id, topic, content, page_number, created_at FROM document_chunks WHERE document_id = ? AND user_id = ?",
        (doc_id, user_id)
    ).fetchall()
    conn.close()

    data = dict(doc)
    data["topics"] = [dict(c) for c in chunks]
    return data


def delete_user_document(doc_id: int, user_id: int) -> bool:
    """Delete a document, its chunks, and associated vault files."""
    conn = get_db()
    doc = conn.execute(
        "SELECT * FROM documents WHERE id = ? AND user_id = ?",
        (doc_id, user_id)
    ).fetchone()
    if not doc:
        conn.close()
        return False

    title = doc["title"]
    conn.execute("DELETE FROM document_chunks WHERE document_id = ? AND user_id = ?", (doc_id, user_id))
    try:
        conn.execute("DELETE FROM document_chunks_fts WHERE user_id = ?", (user_id,))
    except Exception:
        pass
    conn.execute("DELETE FROM documents WHERE id = ? AND user_id = ?", (doc_id, user_id))
    conn.commit()
    conn.close()

    try:
        doc_folder = VAULT_DOCS_DIR / _safe_filename(title)
        if doc_folder.exists():
            import shutil
            shutil.rmtree(doc_folder)
    except Exception as e:
        print(f"[DocumentService] Vault folder deletion note: {e}")

    return True
