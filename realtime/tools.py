# ================================================================
# GIDEON — realtime/tools.py
# ----------------------------------------------------------------
# Skill/tool activity events (schema doc §4): skill.started,
# tool.started, tool.completed, tool.failed. Feeds the client's
# Activity Panel — an append-only log the UI renders as a checklist.
#
# The tricky part: most of Gideon's integrations (web_search,
# firecrawl_read, get_weather, get_news) already catch their own
# exceptions internally and return an empty string/list on failure —
# they never raise. A naive try/except wrapper would call every one
# of those a "success" since nothing ever throws. run_tool() checks
# the actual RETURN VALUE for emptiness instead, which is the only
# reliable way to tell a genuine empty-but-successful result from a
# real failure with these particular functions.
# ================================================================

import time

from realtime.events import emit_event


def emit_skill_started(device_id: str, skill: str, label: str, task_id: str = None) -> None:
    emit_event(device_id, "skill.started", {"skill": skill, "label": label}, task_id=task_id)


def run_tool(device_id: str, tool_name: str, label: str, fn, is_success=None, task_id: str = None):
    """
    Runs fn() (a zero-argument callable), emitting tool.started before
    it runs and either tool.completed (with duration_ms) or
    tool.failed afterward, based on is_success(result) — defaults to
    "truthy result = success" if not given, which is correct for
    every current integration (empty string/list/None all mean "no
    results", anything else means it worked).

    Always returns exactly what fn() returned, success or failure, so
    call sites don't need to change how they handle the result at all
    — this only adds event emission around the existing call, it
    never changes what the call site actually gets back.

    If fn() raises (genuinely unexpected, not the normal failure mode
    for these integrations, but possible), tool.failed is emitted with
    the exception message and the exception is re-raised unchanged —
    this never swallows an error, only reports it alongside whatever
    error handling already exists at the call site.
    """
    if is_success is None:
        is_success = bool

    emit_event(device_id, "tool.started", {"tool": tool_name, "label": label}, task_id=task_id)
    start = time.time()

    try:
        result = fn()
    except Exception as e:
        emit_event(device_id, "tool.failed", {
            "tool": tool_name, "error": str(e)[:200], "recoverable": True,
        }, task_id=task_id)
        raise

    duration_ms = int((time.time() - start) * 1000)

    if is_success(result):
        emit_event(device_id, "tool.completed", {
            "tool": tool_name, "label": label, "duration_ms": duration_ms,
        }, task_id=task_id)
    else:
        emit_event(device_id, "tool.failed", {
            "tool": tool_name, "error": "no_results", "recoverable": True,
        }, task_id=task_id)

    return result
