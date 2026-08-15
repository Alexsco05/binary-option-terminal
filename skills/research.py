# ================================================================
# GIDEON — skills/research.py
# ----------------------------------------------------------------
# Research Mode: search, read the top pages, synthesize a summary,
# and store what was learned as knowledge nodes. This is what makes
# "research X" meaningfully different from just asking the model
# directly — it gathers current information from real sources
# instead of answering from training data alone.
#
# Moved from server.py with zero behavior change.
# ================================================================

from integrations.web import web_search_with_links, firecrawl_read
from integrations.providers import _call_groq_raw_extended
from core.text import _safe_json_loads
from memory.knowledge import merge_nodes


def run_research(topic: str, device_id: str, max_pages: int = 3) -> dict:
    """
    Search, read the top pages, synthesize a summary, and store what
    was learned as knowledge nodes using the same extraction and
    merge logic used elsewhere for conversation extraction.

    Deliberately conservative on Firecrawl calls (max_pages default 3)
    since the free tier is 500 credits/month, one credit per page read.
    Falls back to search snippets alone if page reads all fail — still
    useful, just shallower.
    """
    results = web_search_with_links(topic, num=5)
    if not results:
        return {"topic": topic, "summary": "", "sources": [], "nodes": [],
                "note": "Search returned nothing — check SERPER_KEY or try a different phrasing."}

    sources, page_texts = [], []
    for item in results[:max_pages]:
        content = firecrawl_read(item["url"])
        if content:
            sources.append({"title": item["title"], "url": item["url"]})
            page_texts.append(f"### {item['title']} ({item['url']})\n{content[:2500]}")

    if not page_texts:
        page_texts = [f"- {r['title']}: {r['snippet']}" for r in results]
        sources = [{"title": r["title"], "url": r["url"]} for r in results]

    combined = "\n\n".join(page_texts)[:9000]

    summary_prompt = (
        f"Research topic: {topic}\n\n"
        f"Sources gathered:\n{combined}\n\n"
        "Write a clear, well-organized summary of what these sources say "
        "about this topic. Note any disagreement between sources if there "
        "is any. Do not add anything not supported by the text above."
    )
    summary = _call_groq_raw_extended(summary_prompt, max_tokens=900) or ""

    nodes = []
    if summary:
        node_prompt = (
            "Extract concept nodes from this research summary. A node is "
            "a meaningful topic, person, place, or idea, not every noun. "
            "Return ONLY valid JSON, this exact shape:\n"
            '{"nodes": [{"id": "n1", "label": "short label", '
            '"category": "one word", "related_to": ["n2"]}]}\n'
            f"Summary:\n{summary}"
        )
        raw = _call_groq_raw_extended(node_prompt, max_tokens=700) or ""
        clean = raw.strip().replace("```json", "").replace("```", "").strip()
        s, e = clean.find("{"), clean.rfind("}") + 1
        parsed = _safe_json_loads(clean[s:e]) if s >= 0 and e > 0 else None
        nodes = parsed.get("nodes", []) if parsed else []
        if nodes:
            merge_nodes(device_id, nodes)

    return {"topic": topic, "summary": summary, "sources": sources, "nodes": nodes}
