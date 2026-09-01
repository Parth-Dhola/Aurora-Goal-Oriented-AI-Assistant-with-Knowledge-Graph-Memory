"""
services/apollo_service.py — Integration Bridge for Apollo Anti-Poisoned Research Engine
"""
import sys
import asyncio
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("aurora.apollo")

# Ensure Apollo source directory is in sys.path if not installed globally
APOLLO_ROOT = Path("/Users/apple/Downloads/Apollo/src")
if APOLLO_ROOT.exists() and str(APOLLO_ROOT) not in sys.path:
    sys.path.insert(0, str(APOLLO_ROOT))

_mcp_server_instance = None


def get_apollo_server():
    """Lazily instantiate the Apollo FastMCP Server instance."""
    global _mcp_server_instance
    if _mcp_server_instance is None:
        try:
            from apollo.server.mcp_server import create_mcp_server
            _mcp_server_instance = create_mcp_server()
            logger.info("Apollo Research MCP Server initialized successfully.")
        except Exception as e:
            logger.warning(f"Could not initialize Apollo server directly: {e}")
            _mcp_server_instance = None
    return _mcp_server_instance


def is_apollo_available() -> bool:
    """Return True if Apollo research engine is available."""
    try:
        import apollo
        return True
    except ImportError:
        return False


def fetch_unified_research_context(query: str, top_k: int = 3) -> str:
    """
    Synchronously invoke Apollo's Unified Research Context Pipeline.
    1. Classifies query intent (Academic Paper vs Code vs General Theory vs Web).
    2. Gathers from arXiv, Semantic Scholar, GitHub, and DuckDuckGo in parallel.
    3. Neutralizes prompt injections and cleans LaTeX math.
    4. Reranks with FlashRank CPU cross-encoder and packs with source citations.
    """
    try:
        server = get_apollo_server()
        if server:
            # Run async MCP tool inside synchronous wrapper
            from apollo.router.tool_selector import select_tools_for_query
            from apollo.models.schemas import QueryIntent
            from apollo.ingestion.arxiv_client import search_arxiv
            from apollo.ingestion.semantic_scholar import search_semantic_scholar
            from apollo.ingestion.github_client import search_github_repos
            from apollo.ingestion.web_search import search_duckduckgo
            from apollo.guardrail_rag.reranker import rank_snippets
            from apollo.guardrail_rag.snippet_packer import pack_grounded_snippets
            from apollo.models.schemas import GroundedContextSnippet

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

    # Fallback to standard DuckDuckGo if Apollo encounters an unexpected error
    return _fallback_ddg(query, top_k)


def fetch_academic_papers_context(query: str, top_k: int = 5) -> str:
    """Explicitly search arXiv and Semantic Scholar for academic research papers."""
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
    """Safe DuckDuckGo fallback."""
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return "\n\n".join(f"**{r['title']}**\n{r['body']}" for r in results)
    except Exception:
        return f"No external search results found for: {query}"
