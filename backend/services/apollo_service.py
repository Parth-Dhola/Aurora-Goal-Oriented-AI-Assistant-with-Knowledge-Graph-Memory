"""
services/apollo_service.py — Decoupled Integration Bridge for Apollo Research Engine

Architecture Design:
1. Aurora is 100% standalone and does NOT hardcode local directory paths.
2. If Apollo is installed in the python environment (pip install apollo-mcp) or configured via
   APOLLO_PATH / APOLLO_MCP_URL, Aurora utilizes Apollo's multi-source academic/code pipeline.
3. If Apollo is absent, disabled, or unreachable, Aurora automatically falls back to native
   DuckDuckGo search with zero errors.
"""
import os
import sys
import asyncio
import logging
from pathlib import Path
from typing import Optional

from config import settings

logger = logging.getLogger("aurora.apollo")

# Check if Apollo source path is explicitly configured via environment variable
if settings.APOLLO_PATH:
    custom_path = Path(settings.APOLLO_PATH)
    src_sub = custom_path / "src"
    target_path = src_sub if src_sub.exists() else custom_path
    if target_path.exists() and str(target_path) not in sys.path:
        sys.path.insert(0, str(target_path))

_mcp_server_instance = None


def is_apollo_available() -> bool:
    """Return True if Apollo research engine is enabled and accessible."""
    if not settings.APOLLO_ENABLED:
        return False
    try:
        import apollo
        return True
    except ImportError:
        return False


def get_apollo_server():
    """Lazily instantiate the Apollo FastMCP Server instance if available."""
    global _mcp_server_instance
    if not is_apollo_available():
        return None

    if _mcp_server_instance is None:
        try:
            from apollo.server.mcp_server import create_mcp_server
            _mcp_server_instance = create_mcp_server()
            logger.info("Apollo Research MCP Server initialized successfully.")
        except Exception as e:
            logger.debug(f"Could not initialize Apollo server instance: {e}")
            _mcp_server_instance = None
    return _mcp_server_instance


def fetch_unified_research_context(query: str, top_k: int = 3) -> str:
    """
    Query Apollo's Unified Research Context Pipeline if available; otherwise fallback to DuckDuckGo.
    1. Zero-cost Intent Classification (Academic Paper vs Code vs General Theory vs Web).
    2. Parallel Ingestion from arXiv, Semantic Scholar, GitHub, and DuckDuckGo.
    3. Neutralizes prompt injections and cleans LaTeX math.
    4. Reranks with FlashRank CPU cross-encoder and packs with source citations.
    """
    if not is_apollo_available():
        return _fallback_ddg(query, top_k)

    try:
        from apollo.router.tool_selector import select_tools_for_query
        from apollo.models.schemas import QueryIntent, GroundedContextSnippet
        from apollo.ingestion.arxiv_client import search_arxiv
        from apollo.ingestion.semantic_scholar import search_semantic_scholar
        from apollo.ingestion.github_client import search_github_repos
        from apollo.ingestion.web_search import search_duckduckgo
        from apollo.guardrail_rag.reranker import rank_snippets
        from apollo.guardrail_rag.snippet_packer import pack_grounded_snippets

        async def _run():
            selection = select_tools_for_query(query)
            tasks = []
            if selection.intent in (QueryIntent.ACADEMIC_PAPER, QueryIntent.DEEP_THEORY, QueryIntent.HYBRID):
                tasks.append(search_arxiv(query, max_results=top_k))
                tasks.append(search_semantic_scholar(query, limit=top_k))

            if selection.intent in (QueryIntent.CODE_IMPLEMENTATION, QueryIntent.HYBRID):
                tasks.append(search_github_repos(topic=query, per_page=top_k))

            if selection.intent == QueryIntent.GENERAL_WEB or not tasks:
                ddg_results = search_duckduckgo(query, max_results=top_k)
                candidates = [
                    GroundedContextSnippet(
                        source="web",
                        title=r["title"],
                        url=r["url"],
                        content=r["content"],
                        citation_meta={"engine": "duckduckgo"}
                    )
                    for r in ddg_results
                ]
                ranked = rank_snippets(query, candidates, top_k=top_k)
                return pack_grounded_snippets(ranked)

            ingestion_results = await asyncio.gather(*tasks, return_exceptions=True)
            candidates = []
            for res in ingestion_results:
                if isinstance(res, Exception) or not res:
                    continue
                for item in res:
                    if hasattr(item, "abstract"):
                        candidates.append(GroundedContextSnippet(
                            source=item.source,
                            title=item.title,
                            url=item.url or (f"https://arxiv.org/abs/{item.arxiv_id}" if item.arxiv_id else None),
                            content=item.abstract,
                            citation_meta={
                                "arxiv_id": item.arxiv_id,
                                "doi": item.doi,
                                "year": item.year,
                                "citations": item.citation_count,
                                "authors": item.authors
                            }
                        ))
                    elif hasattr(item, "repo_name"):
                        candidates.append(GroundedContextSnippet(
                            source="github",
                            title=f"{item.repo_name} ({item.file_path})",
                            url=item.repo_url,
                            content=item.snippet,
                            citation_meta={
                                "stars": item.stars,
                                "language": item.language
                            }
                        ))

            if not candidates:
                ddg_results = search_duckduckgo(query, max_results=top_k)
                candidates = [
                    GroundedContextSnippet(
                        source="web",
                        title=r["title"],
                        url=r["url"],
                        content=r["content"],
                        citation_meta={"engine": "duckduckgo"}
                    )
                    for r in ddg_results
                ]

            ranked = rank_snippets(query, candidates, top_k=top_k)
            packed_text = pack_grounded_snippets(ranked)
            header = f"### [Apollo Anti-Poisoned Research Engine | Intent: {selection.intent.value}]\n\n"
            return header + packed_text

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()
                return loop.run_until_complete(_run())
            else:
                return loop.run_until_complete(_run())
        except RuntimeError:
            return asyncio.run(_run())

    except Exception as e:
        logger.error(f"Apollo unified research execution error: {e}")
        return _fallback_ddg(query, top_k)


def fetch_academic_papers_context(query: str, top_k: int = 5) -> str:
    """Explicitly search arXiv and Semantic Scholar for academic research papers."""
    if not is_apollo_available():
        return _fallback_ddg(query, top_k)

    try:
        from apollo.ingestion.arxiv_client import search_arxiv
        from apollo.ingestion.semantic_scholar import search_semantic_scholar
        from apollo.guardrail_rag.reranker import rank_snippets
        from apollo.guardrail_rag.snippet_packer import pack_grounded_snippets
        from apollo.models.schemas import GroundedContextSnippet

        async def _run():
            arxiv_task = search_arxiv(query, max_results=top_k)
            s2_task = search_semantic_scholar(query, limit=top_k)
            arxiv_papers, s2_papers = await asyncio.gather(arxiv_task, s2_task, return_exceptions=True)

            candidates = []
            if not isinstance(arxiv_papers, Exception) and arxiv_papers:
                for p in arxiv_papers:
                    candidates.append(GroundedContextSnippet(
                        source="arxiv",
                        title=p.title,
                        url=p.url or f"https://arxiv.org/abs/{p.arxiv_id}",
                        content=p.abstract,
                        citation_meta={"arxiv_id": p.arxiv_id, "year": p.year, "authors": p.authors}
                    ))
            if not isinstance(s2_papers, Exception) and s2_papers:
                for p in s2_papers:
                    candidates.append(GroundedContextSnippet(
                        source="semantic_scholar",
                        title=p.title,
                        url=p.url,
                        content=p.abstract,
                        citation_meta={"doi": p.doi, "year": p.year, "citations": p.citation_count, "authors": p.authors}
                    ))

            if not candidates:
                return "No academic papers found for this topic."

            ranked = rank_snippets(query, candidates, top_k=top_k)
            return pack_grounded_snippets(ranked)

        try:
            return asyncio.run(_run())
        except RuntimeError:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(_run())
    except Exception as e:
        logger.error(f"Academic paper search error: {e}")
        return _fallback_ddg(query, top_k)


def _fallback_ddg(query: str, max_results: int = 3) -> str:
    """Standard decoupled DuckDuckGo fallback when Apollo is offline or disabled."""
    try:
        from duckduckgo_search import DDGS
        for backend in ("api", "html", "lite"):
            try:
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=max_results, backend=backend))
                    if results:
                        formatted_snippets = "\n\n".join(
                            f"**{r.get('title', 'Web Result')}**\n{r.get('body', '')}" for r in results
                        )
                        return f"### [Web Search Context (DuckDuckGo Live Fallback)]\n\n{formatted_snippets}"
            except Exception:
                continue
        return f"### [Web Search Context]\n\nNo live web search results available for: {query}"
    except Exception as e:
        logger.warning(f"DuckDuckGo fallback search error: {e}")
        return f"External search unavailable: {e}"
