# ================================================================
# GIDEON — core/tool_registry.py
# ----------------------------------------------------------------
# Roadmap §3 (Tool Registry) and §34's "structured tool/function
# calls" requirement. Before this file, "tool use" meant the model
# writing a plain-text tag like [SEARCH:query] into its reply, which
# core/tags.py then regex-parsed out. That works, but it's not
# discoverable (nothing lists what tools exist), not structured (no
# argument schema — a query is just whatever text sat between the
# colon and the bracket), and it's *this backend's own convention*,
# not something the model's own tool-calling training actually
# targets.
#
# This registers the SAME underlying capabilities (integrations/web.py
# already has real, working functions — nothing here is a new
# integration) as proper tools: a name, a description, and a JSON
# Schema for arguments, in the exact shape Groq's (and any OpenAI-
# compatible) chat completions API expects in its `tools` parameter.
# core/tool_router.py is what actually sends these to a model and
# executes what comes back — this file only holds the catalog.
#
# To add a tool: register_tool(Tool(name=..., description=...,
# parameters={...JSON Schema...}, function=<callable>)). Nothing in
# tool_router.py needs to change — it reads this registry generically.
# ================================================================

from dataclasses import dataclass
from typing import Callable, Dict, Optional

from integrations.web import web_search_with_links, firecrawl_read, get_weather, get_news


@dataclass
class Tool:
    name: str
    description: str
    # JSON Schema for the function's arguments — exactly the "parameters"
    # object OpenAI-compatible tool-calling expects, e.g.:
    #   {"type": "object", "properties": {"query": {"type": "string"}},
    #    "required": ["query"]}
    parameters: dict
    function: Callable
    # Some tools return a plain string ready to hand back to the model
    # (web_search); others return structured data a caller might want
    # to keep, not just read back (firecrawl_read returning markdown
    # the caller displays verbatim). result_is_text=True means "safe to
    # pass straight back into the model's next turn as the tool result
    # content" — the common case. False means the router should str()
    # or otherwise serialize it itself.
    result_is_text: bool = True


TOOL_REGISTRY: Dict[str, Tool] = {}


def register_tool(tool: Tool) -> None:
    TOOL_REGISTRY[tool.name] = tool


def get_tool(name: str) -> Optional[Tool]:
    return TOOL_REGISTRY.get(name)


def list_tool_schemas() -> list:
    """Builds the `tools` array for an OpenAI-compatible chat
    completions request — one entry per registered tool, in the exact
    {"type": "function", "function": {...}} shape the API expects."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
        for tool in TOOL_REGISTRY.values()
    ]


# ================================================================
# REGISTRATION — every tool Gideon can currently call. Each wraps an
# existing, already-working function from integrations/web.py; this
# file adds the name/schema/discoverability layer on top, not new
# capabilities.
# ================================================================

def _web_search_tool(query: str) -> str:
    results = web_search_with_links(query)
    if not results:
        return "No search results found."
    lines = [f"{i}. {r['title']} — {r['snippet']} ({r['url']})"
             for i, r in enumerate(results, start=1)]
    return "\n".join(lines)


register_tool(Tool(
    name="web_search",
    description=(
        "Search the web for current information — news, prices, recent "
        "events, or anything that may have changed since training. "
        "Returns titles, snippets, and URLs for the top results."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query"},
        },
        "required": ["query"],
    },
    function=_web_search_tool,
))


def _read_webpage_tool(url: str) -> str:
    content = firecrawl_read(url)
    return content or "Could not read that page — it may be unavailable or blocked."


register_tool(Tool(
    name="read_webpage",
    description=(
        "Fetch and read the full text content of a specific webpage URL. "
        "Use this after web_search when a result needs to be read in full, "
        "or when the user gives you a URL directly."
    ),
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The full URL to read"},
        },
        "required": ["url"],
    },
    function=_read_webpage_tool,
))


def _get_weather_tool(city: str = "") -> str:
    result = get_weather(city)
    return result or f"Could not get weather for {city or 'the default location'}."


register_tool(Tool(
    name="get_weather",
    description="Get the current weather for a city.",
    parameters={
        "type": "object",
        "properties": {
            "city": {"type": "string",
                     "description": "City name. Defaults to Lagos if omitted."},
        },
        "required": [],
    },
    function=_get_weather_tool,
))


def _get_news_tool() -> str:
    result = get_news()
    return result or "Could not fetch news right now."


register_tool(Tool(
    name="get_news",
    description="Get today's top news headlines (Nigeria).",
    parameters={"type": "object", "properties": {}, "required": []},
    function=_get_news_tool,
))

