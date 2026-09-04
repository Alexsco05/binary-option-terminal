# ================================================================
# GIDEON — core/workspace_actions.py
# ----------------------------------------------------------------
# Resolves workspace.action (schema §9/§11) — the client->server
# hook for in-workspace buttons ("Summarize", "Citations", "Compare",
# "Continue", etc). Dispatched here from
# realtime/socket_server.py's _handle_workspace_action.
#
# Every result lands back in the SAME workspace via workspace.update,
# never as a separate chat message — one consistent home for a
# button's result, and workspace.update was already designed as a
# standalone push (schema §5), so this needed no new event the way
# the permission flow did.
#
# Scope: only actions with genuine backing data are handled. research
# has real stored state to act on (see memory/conversation.py's
# LAST_RESEARCH). planning/writing's "continue" just extends the
# existing conversation, which short-term memory already has.
# Everything else (coding's run/stop, file's open/move/rename/etc.,
# teaching's practice/quiz) has no real backend capability behind it
# yet — same reasoning as leaving Teaching/Coding workspaces unwired
# in Phase 5, logged and ignored rather than faked.
# ================================================================

from memory.conversation import LAST_RESEARCH, get_short_term
from memory.personality import load_personality
from core.prompts import build_system_prompt
from core.router import select_primary, call_provider
from config.settings import MODELS
from realtime.workspace import (
    emit_workspace_update, heading_block, body_block, divider_block,
)

RESEARCH_ACTIONS = {"summarize", "sources", "citations", "compare"}
CONTINUE_WORKSPACES = {"planning", "writing"}


def _call_model(prompt: str, route: str, device_id: str) -> str:
    """Small, single-purpose model call — not routed through
    process()/process_multi_step(), since this isn't a new user
    message, it's a targeted transformation of data the server
    already has (or a short continuation of existing context)."""
    personality   = load_personality(device_id)
    system_prompt = build_system_prompt(personality, route)
    model_cfg     = MODELS.get(route, MODELS["fast"])
    primary       = select_primary(model_cfg)
    short_term    = get_short_term(device_id)

    answer = call_provider(prompt, primary["provider"], primary["model"],
                           system_prompt, short_term, device_id)
    if not answer:
        for fb in model_cfg.get("fallbacks", []):
            answer = call_provider(prompt, fb["provider"], fb["model"],
                                   system_prompt, short_term, device_id)
            if answer:
                break
    return answer or ""


def _handle_research_action(device_id: str, task_id, action: str, params: dict) -> None:
    state = LAST_RESEARCH.get(device_id)
    if not state:
        print(f"[WorkspaceAction] {device_id} tapped '{action}' on research "
              f"but no research result is on file for them, ignoring")
        return

    if action == "sources":
        # Sources are already always shown in the research workspace's
        # initial blocks (see api/routes.py's /research) — this tap is
        # a client-side expand/collapse, nothing for the server to do.
        return

    if action == "citations":
        lines = [f"{i}. {s.get('title', 'Untitled')} — {s.get('url', '')}"
                 for i, s in enumerate(state["sources"], start=1)]
        content = "\n".join(lines) if lines else "No sources to cite."
        blocks = [divider_block(), heading_block("Citations"), body_block(content)]

    elif action == "summarize":
        prompt = (f"Give a shorter, more concise summary of this research on "
                 f"\"{state['topic']}\":\n\n{state['summary']}")
        content = _call_model(prompt, "research", device_id)
        blocks = [divider_block(), heading_block("Concise Summary"), body_block(content)]

    elif action == "compare":
        titles = ", ".join(s.get("title", "a source") for s in state["sources"]) or "the sources"
        prompt = (f"Briefly compare and contrast what these sources say about "
                 f"\"{state['topic']}\": {titles}. Base this only on: {state['summary']}")
        content = _call_model(prompt, "research", device_id)
        blocks = [divider_block(), heading_block("Comparison"), body_block(content)]

    else:
        return

    emit_workspace_update(device_id, task_id or state.get("task_id"), {"blocks": blocks})


def _handle_continue_action(device_id: str, task_id, workspace: str) -> None:
    short_term = get_short_term(device_id)
    if not short_term:
        print(f"[WorkspaceAction] {device_id} tapped 'continue' on {workspace} "
              f"but has no conversation history to continue from, ignoring")
        return
    prompt = "Continue from where you left off, building on what you just said."
    content = _call_model(prompt, workspace, device_id)
    if not content:
        return
    blocks = [divider_block(), body_block(content)]
    emit_workspace_update(device_id, task_id, {"blocks": blocks})


def handle_workspace_action(device_id: str, task_id, workspace: str,
                            action: str, params: dict) -> None:
    """Entry point called from realtime/socket_server.py. Every branch
    below is deliberately narrow — see module docstring for what's
    out of scope and why."""
    print(f"[WorkspaceAction] {device_id}: workspace='{workspace}' action='{action}'")

    if workspace == "research" and action in RESEARCH_ACTIONS:
        _handle_research_action(device_id, task_id, action, params or {})
        return

    if workspace in CONTINUE_WORKSPACES and action == "continue":
        _handle_continue_action(device_id, task_id, workspace)
        return

    if action == "workspace.back":
        # Per schema §11: handled entirely client-side, never sent to
        # the backend as a task instruction. If this ever arrives
        # here, it's a client bug, not something to act on.
        print(f"[WorkspaceAction] {device_id} sent 'workspace.back' to the "
              f"backend — this should be handled client-side only")
        return

    print(f"[WorkspaceAction] no handler for workspace='{workspace}' "
          f"action='{action}' — no backend capability behind this yet, ignoring")
