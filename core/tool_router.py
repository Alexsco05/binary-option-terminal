# ================================================================
# GIDEON — core/tool_router.py
# ----------------------------------------------------------------
# Roadmap §3/§34 — the actual structured tool-calling round trip,
# using the catalog from core/tool_registry.py. This is genuinely new
# behavior, not a reorganization: the model gets a `tools` array and
# decides for itself whether a tool is needed, instead of the backend
# regex-parsing a text tag it was instructed to write.
#
# Deliberately Groq-only for now — that's where tool_choice support
# for the current primary model (openai/gpt-oss-120b) is confirmed,
# and every fallback provider in MODELS' chains would need its own
# testing before trusting this path with them too. Non-Groq providers
# and every existing [SEARCH:]/[READ:]/[ACTION:] tag path are
# completely untouched by this file — this is an additive capability,
# not a replacement, until it's proven out.
#
# ALWAYS uses tool_choice="auto", never a forced tool_choice. Real,
# recent community reports show gpt-oss-120b's forced tool_choice
# enforcement is unreliable — it can ignore a forced choice or call a
# different function than the one specified. "auto" sidesteps that
# entirely: the model deciding not to call a tool is just an ordinary
# answer, not a failure to route around.
# ================================================================

import json

from config.environment import GROQ_KEYS
from integrations.client import SESSION
from core.tool_registry import get_tool, list_tool_schemas


def call_with_tools(msg: str, system_prompt: str, short_term: list,
                    model: str = "openai/gpt-oss-120b", max_rounds: int = 3):
    """
    Returns (final_text, tool_calls_log) on success, or (None, []) if
    every Groq key failed outright (caller should fall back to the
    ordinary non-tool call_provider() path — this is additive, never
    the only way to get an answer).

    tool_calls_log is a list of {"name", "args", "result_preview"}
    dicts, in call order — args are the actual parsed arguments (e.g.
    {"url": "https://..."}), not just the tool's name, since a caller
    like research needs to know exactly which URLs got read, not just
    that "read_webpage" was called some number of times.
    """
    tools = list_tool_schemas()
    if not tools:
        return None, []

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(short_term[-10:] if short_term else [])
    messages.append({"role": "user", "content": msg})

    calls_log = []

    for _ in range(max_rounds):
        reply = _call_groq_with_tools(messages, tools, model)
        if reply is None:
            return (None, calls_log) if not calls_log else \
                   ("I looked into that but couldn't finish — please try again.", calls_log)

        tool_calls = reply.get("tool_calls")
        if not tool_calls:
            # No tool needed (or none left to call) — this is the
            # normal, common ending: the model just answered directly.
            return reply.get("content") or "", calls_log

        # Groq/OpenAI-compatible format requires the assistant's own
        # tool_calls message to be echoed back before any tool results,
        # so the model can see what it asked for when reasoning about
        # the results in the next round.
        messages.append({
            "role": "assistant",
            "content": reply.get("content") or "",
            "tool_calls": tool_calls,
        })

        for call in tool_calls:
            name = call.get("function", {}).get("name", "")
            raw_args = call.get("function", {}).get("arguments", "{}")
            try:
                args = json.loads(raw_args) if raw_args else {}
            except json.JSONDecodeError:
                args = {}

            tool = get_tool(name)
            if tool is None:
                result_text = f"Unknown tool '{name}'."
            else:
                try:
                    result = tool.function(**args)
                    result_text = result if tool.result_is_text else json.dumps(result)
                except Exception as e:
                    result_text = f"Tool '{name}' failed: {e}"
                calls_log.append({
                    "name": name, "args": args,
                    "result_preview": (result_text or "")[:200],
                })

            messages.append({
                "role": "tool",
                "tool_call_id": call.get("id", ""),
                "content": result_text,
            })

    # Ran out of rounds (max_rounds calls all wanted more tools) —
    # return whatever the model last said rather than nothing.
    return "I gathered some information but couldn't fully finish — here's what I found so far.", calls_log


def _call_groq_with_tools(messages: list, tools: list, model: str):
    """Returns the raw assistant message dict ({"content", "tool_calls"})
    from the first key that succeeds, or None if every key failed."""
    for key in GROQ_KEYS:
        if not key:
            continue
        try:
            r = SESSION.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": model,
                    "messages": messages,
                    "tools": tools,
                    "tool_choice": "auto",
                    "max_tokens": 1200,
                },
                timeout=15,
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]
            else:
                print(f"[ToolRouter] Groq {r.status_code}: {r.text[:200]}")
        except Exception as e:
            print(f"[ToolRouter] {e}")
    return None

