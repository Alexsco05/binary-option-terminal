# ================================================================
# GIDEON — realtime/events.py
# ----------------------------------------------------------------
# Builds and sends events in the exact envelope format the schema
# doc defines, and holds the CoreState constants for orb state.
#
# emit_event() is the ONE function the rest of the backend ever
# calls to push something to the client — nothing else should touch
# the registry or build a raw envelope by hand, so the wire format
# stays correct in exactly one place.
# ================================================================

import json
import uuid
import datetime

from realtime.registry import get_connection

# ================================================================
# CoreState — matches GideonCoreView.kt's CoreState enum exactly.
# Deliberately coarse: finer distinctions ride as the optional
# `label` string, not as new states. Adding a new state here means
# deciding what it looks like on the client first — see the schema
# doc §2 before ever adding to this list.
# ================================================================
DORMANT   = "dormant"
LISTENING = "listening"
THINKING  = "thinking"
EXECUTING = "executing"
WARNING   = "warning"
DANGER    = "danger"
OFFLINE   = "offline"

VALID_STATES = {DORMANT, LISTENING, THINKING, EXECUTING, WARNING, DANGER, OFFLINE}


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def emit_event(device_id: str, event: str, payload: dict, task_id: str = None) -> bool:
    """
    Sends one event to a specific device's live WebSocket connection,
    wrapped in the standard envelope. Returns True if it was actually
    sent, False if that device has no live connection right now (not
    an error — the client may be on a plain HTTP session, or briefly
    disconnected; every event is fire-and-forget, nothing in the
    backend should ever block waiting for one to be delivered).
    """
    ws = get_connection(device_id)
    if ws is None:
        return False

    envelope = {
        "event": event,
        "session_id": device_id,
        "task_id": task_id,
        "timestamp": _now_iso(),
        "payload": payload or {},
    }

    try:
        ws.send(json.dumps(envelope))
        return True
    except Exception as e:
        print(f"[Realtime] emit_event failed for {device_id}: {e}")
        return False


def emit_state(device_id: str, state: str, label: str = None) -> bool:
    """Convenience wrapper for the single most common event — orb
    state changes. Validates against VALID_STATES so a typo in a
    call site fails loudly here instead of silently confusing the
    client with an unrecognized state string."""
    if state not in VALID_STATES:
        print(f"[Realtime] emit_state: '{state}' is not a valid CoreState, dropping")
        return False
    payload = {"state": state}
    if label:
        payload["label"] = label
    return emit_event(device_id, "state.changed", payload)


def new_task_id() -> str:
    return uuid.uuid4().hex
