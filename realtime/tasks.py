# ================================================================
# GIDEON — realtime/tasks.py
# ----------------------------------------------------------------
# Task lifecycle events (schema doc §3): task.started, task.planning,
# task.progress, task.completed, task.failed.
#
# Attached to core/agent.py's process_multi_step() — the existing
# planner is the natural fit, since it already computes a genuine
# ordered steps list and executes them sequentially. That's exactly
# task.planning (the steps list) + task.progress (step_index/
# step_total as each one runs). A single-shot request through
# process() is NOT wrapped in task lifecycle events — a quick one-off
# exchange isn't what "task" means in this schema, and treating every
# message as a task would flood the client with lifecycle events for
# things that were never structured multi-step work in the first
# place.
# ================================================================

import threading

from realtime.events import emit_event

# ================================================================
# Task cancellation (schema §9's task.cancel). A real cross-thread
# concern, not just bookkeeping: task.cancel arrives on the
# WebSocket's own thread, while the multi-step task it targets is
# running synchronously inside a completely separate /stream (or
# /run) HTTP request thread. A plain set + lock is enough here — this
# doesn't need to survive a restart, only to be visible the instant
# it's set from the other thread. Entries are removed once consumed
# (see process_multi_step()) so this can't grow unbounded from
# finished tasks whose ids are never revisited.
# ================================================================
_CANCELLED_TASKS = set()
_CANCEL_LOCK = threading.Lock()


def request_task_cancel(task_id) -> None:
    if not task_id:
        return
    with _CANCEL_LOCK:
        _CANCELLED_TASKS.add(task_id)


def is_task_cancelled(task_id) -> bool:
    if not task_id:
        return False
    with _CANCEL_LOCK:
        return task_id in _CANCELLED_TASKS


def clear_task_cancel(task_id) -> None:
    if not task_id:
        return
    with _CANCEL_LOCK:
        _CANCELLED_TASKS.discard(task_id)

# Not every route has an obvious workspace equivalent — routes like
# "fast", "complex", "creative", "empathetic", "firm", "weather",
# "news", "business" stay as ordinary conversation with no workspace,
# same as before this system existed. Only routes that clearly match
# one of the schema's 7 workspace types get one.
ROUTE_TO_WORKSPACE = {
    "teaching": "teaching",
    "coding":   "coding",
    "research": "research",
    "planning": "planning",
    "writing":  "writing",
    "math":     "science",  # closest existing workspace type to math
}


def workspace_for_route(route: str):
    """Returns the schema workspace type for a route, or None if this
    route has no workspace equivalent — task.started's "workspace"
    field is allowed to be null for ordinary conversational tasks."""
    return ROUTE_TO_WORKSPACE.get(route)


def emit_task_started(device_id: str, task_id: str, intent: str,
                      workspace, summary: str) -> None:
    emit_event(device_id, "task.started", {
        "intent": intent,
        "workspace": workspace,
        "summary": summary,
    }, task_id=task_id)


def emit_task_planning(device_id: str, task_id: str, steps: list) -> None:
    emit_event(device_id, "task.planning", {"steps": steps}, task_id=task_id)


def emit_task_progress(device_id: str, task_id: str, step_index: int,
                       step_total: int, label: str) -> None:
    percent = int(round((step_index / step_total) * 100)) if step_total else 0
    emit_event(device_id, "task.progress", {
        "step_index": step_index,
        "step_total": step_total,
        "label": label,
        "percent": percent,
    }, task_id=task_id)


def emit_task_completed(device_id: str, task_id: str, summary: str,
                        result: dict = None) -> None:
    emit_event(device_id, "task.completed", {
        "summary": summary,
        "result": result or {},
    }, task_id=task_id)


def emit_task_failed(device_id: str, task_id: str, error: str,
                     message: str, recoverable: bool = True) -> None:
    emit_event(device_id, "task.failed", {
        "error": error,
        "message": message,
        "recoverable": recoverable,
    }, task_id=task_id)
