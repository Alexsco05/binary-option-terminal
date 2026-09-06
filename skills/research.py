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
from realtime.tools import emit_skill_started, run_tool
from core.tool_router import call_with_tools

_RESEARCH_SYSTEM_PROMPT = (
    "You are a research assistant. Use the web_search and read_webpage "
    "tools to investigate the user's topic thoroughly before answering. "
    "Search first. Read the pages that actually look relevant — do not "
    "read every result, and do not read pages that are clearly off-topic "
    "or low-quality. For a simple, well-established topic, one search "
    "and reading 1-2 pages may be enough. For a topic with conflicting "
    "or fast-changing information, search more and read more pages "
    "before answering. When you have enough, write a clear, well-"
    "organized summary of what you found. Note any disagreement between "
    "sources if there is any. Never state something as fact that your "
    "sources did not actually say."
)


def run_research(topic: str, device_id: str, max_pages: int = 3) -> dict:
    """
    Tries real tool-calling first (the model decides how much searching
    and reading a topic actually needs — see run_research_agentic()),
    falling back to the original fixed pipeline (always 1 search, read
    exactly the top max_pages results) only if the agentic path fails
    outright (e.g. Groq unreachable). The fixed pipeline is kept
    exactly as it was — this never removes a working path, only tries
    a better one first.
    """
    agentic_result = run_research_agentic(topic, device_id)
    if agentic_result is not None:
        return agentic_result
    return _run_research_fixed(topic, device_id, max_pages)


def run_research_agentic(topic: str, device_id: str) -> dict:
    """
    Returns None if the tool-calling path failed outright (caller
    should use the fixed pipeline instead) — never None just because
    the model chose not to call any tool, since that's a legitimate
    answer for a topic it can already address directly, not a failure.
    """
    emit_skill_started(device_id, "research", f"Researching {topic[:60]}")

    summary, calls_log = call_with_tools(
        f"Research this topic thoroughly: {topic}",
        _RESEARCH_SYSTEM_PROMPT, [], max_rounds=6,
    )
    if summary is None:
        return None  # every Groq key failed — let the fixed pipeline try

    sources = [
        {"title": c["args"].get("url", "source"), "url": c["args"]["url"]}
        for c in calls_log
        if c["name"] == "read_webpage" and c["args"].get("url")
    ]
    # web_search itself doesn't map to one specific source (it returns
    # several), so it doesn't add to `sources` — only pages actually
    # read do, matching what the fixed pipeline's `sources` list meant.

    nodes = _extract_and_store_nodes(summary, device_id) if summary else []

    return {"topic": topic, "summary": summary, "sources": sources, "nodes": nodes}


def _extract_and_store_nodes(summary: str, device_id: str) -> list:
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
    return nodes


def _run_research_fixed(topic: str, device_id: str, max_pages: int = 3) -> dict:
    """
    The original fixed pipeline — always exactly 1 search, read exactly
    the top max_pages results, no matter how simple or complex the
    topic. Kept as-is, unchanged, as the fallback for when the agentic
    path above can't run at all.

    Deliberately conservative on Firecrawl calls (max_pages default 3)
    since the free tier is 500 credits/month, one credit per page read.
    Falls back to search snippets alone if page reads all fail — still
    useful, just shallower.
    """
    emit_skill_started(device_id, "research", f"Researching {topic[:60]}")

    results = run_tool(
        device_id, "web.search", f"Searching for {topic[:60]}",
        lambda: web_search_with_links(topic, num=5),
    )
    if not results:
        return {"topic": topic, "summary": "", "sources": [], "nodes": [],
                "note": "Search returned nothing — check SERPER_KEY or try a different phrasing."}
    sources, page_texts = [], []
    for item in results[:max_pages]:
        content = run_tool(
            device_id, "web.read", f"Reading {item['title'][:60]}",
            lambda url=item["url"]: firecrawl_read(url),
        )
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
    nodes = _extract_and_store_nodes(summary, device_id) if summary else []

    return {"topic": topic, "summary": summary, "sources": sources, "nodes": nodes}
