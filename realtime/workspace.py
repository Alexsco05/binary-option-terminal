# ================================================================
# GIDEON — realtime/workspace.py
# ----------------------------------------------------------------
# Workspace control (schema doc §5) and the block composition system
# (§7a). This is the piece that was entirely missing before Phase 5:
# task.started already told the client WHICH workspace a task maps
# to (via ROUTE_TO_WORKSPACE in realtime/tasks.py), but nothing ever
# sent the actual content to put in it. This file is that content
# layer.
#
# Scope note: only Teaching and Coding kept their own fixed payload
# shapes from §7 — every other workspace (Research, Planning,
# Writing, Science, File) uses the shared `blocks` array from §7a
# instead. This module only builds the block system, since that's
# what every currently-wired call site (§ /research, multi-step
# planner) actually needs. Teaching/Coding's fixed shapes aren't
# built here — see GIDEON_HANDOFF.md Phase 5 notes for why.
# ================================================================

from realtime.events import emit_event


def emit_workspace_open(device_id: str, task_id: str, workspace: str,
                        title: str, data: dict, mode: str = None) -> bool:
    """
    Opens a workspace on the client (schema §5). `data` is the
    workspace-specific payload — for every workspace wired so far,
    that's {"title", "subtitle", "blocks"} per §7a.
    """
    payload = {"workspace": workspace, "title": title, "data": data or {}}
    if mode:
        payload["mode"] = mode
    return emit_event(device_id, "workspace.open", payload, task_id=task_id)


def emit_workspace_update(device_id: str, task_id: str, data: dict) -> bool:
    """
    Sends a partial patch to an already-open workspace (schema §5).
    Per the schema's payload discipline, this should only ever carry
    what actually changed — never re-send the full state each time,
    even though it would be simpler call-site code to always send
    everything.
    """
    return emit_event(device_id, "workspace.update", {"data": data or {}}, task_id=task_id)


# ================================================================
# BLOCK BUILDERS (schema §7a) — one function per block type, so call
# sites can't typo a `"type"` string or drift from the documented
# field names. Each returns a plain dict ready to drop into a
# `blocks` list.
# ================================================================

def text_block(style: str, content: str) -> dict:
    return {"type": "text", "style": style, "content": content}


def heading_block(content: str) -> dict:
    return text_block("heading", content)


def body_block(content: str) -> dict:
    return text_block("body", content)


def source_list_block(label: str, items: list) -> dict:
    """items: iterable of {"title", "url", "status"?}. status defaults
    to "read" — every current call site (research) only ever sends
    sources it has already read, never a pending/error one yet."""
    return {
        "type": "source_list",
        "label": label,
        "items": [
            {
                "title": i.get("title", ""),
                "url": i.get("url", ""),
                "status": i.get("status", "read"),
            }
            for i in items
        ],
    }


def list_block(label: str, items: list) -> dict:
    return {"type": "list", "label": label, "items": list(items)}


def schedule_block(label: str, items: list) -> dict:
    return {"type": "schedule", "label": label, "items": list(items)}


def variables_block(label: str, items: list) -> dict:
    return {"type": "variables", "label": label, "items": list(items)}


def graph_block(label: str) -> dict:
    """Placeholder per schema §7a — no charting library is wired up on
    the client yet, so this renders as a labeled box. Don't expect a
    real chart until that's built."""
    return {"type": "graph", "label": label}


def file_list_block(label: str, items: list) -> dict:
    return {"type": "file_list", "label": label, "items": list(items)}


def progress_block(label: str, percent: int) -> dict:
    return {"type": "progress", "label": label, "percent": int(percent)}


def divider_block() -> dict:
    return {"type": "divider"}


def action_row_block(actions: list) -> dict:
    return {"type": "action_row", "actions": list(actions)}


# ================================================================
# CANONICAL ACTION REGISTRY (schema §11) — mirrors the wire-value
# table exactly, scoped to the workspaces actually wired so far.
# Adding an action here without adding it to the client's own
# WorkspaceAction registry does nothing; this only documents which
# strings THIS backend is allowed to send per workspace, so a call
# site can't invent one that the schema doesn't define.
# ================================================================
WORKSPACE_ACTIONS = {
    "research": ["summarize", "sources", "compare", "citations"],
    "planning": ["continue"],
    "writing": ["improve", "rewrite", "research", "continue"],
    # "science" has only run_simulation in §11, which implies a real
    # simulation backend Gideon doesn't have yet — deliberately left
    # out of this map rather than sending a button that does nothing
    # when tapped. Revisit once/if a simulation capability exists.
}
