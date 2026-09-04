# ================================================================
# GIDEON — realtime/permissions.py
# ----------------------------------------------------------------
# Permission flow (schema doc §6): permission.required (server -> client)
# and permission.response (client -> server, dispatched from
# realtime/socket_server.py into core/intent.py's
# resolve_permission_response()).
#
# Built ON TOP of the confirmation system that already existed in
# core/intent.py (PENDING_CONFIRMATIONS / store_pending() /
# check_user_confirmation()) rather than replacing it. A spoken or
# typed "yes" as the user's next message still works exactly as
# before, completely unchanged. This adds the structured permission
# card as a SECOND way to resolve the same pending action, for when
# the client is showing the card instead of waiting on a spoken
# reply.
#
# ----------------------------------------------------------------
# action.execute — NOT part of the original schema doc. Read this if
# you're the frontend developer.
# ----------------------------------------------------------------
# The documented contract (§6) only defines permission.required and
# permission.response — there's no event for pushing the resulting
# action back to the client once it's approved. That gap is real, not
# an oversight on either side: the existing action-delivery path (the
# `[ACTION:...]` marker in an HTTP response body, from /run or
# /stream) only works because there's a request in flight to attach
# it to — the user's own message that triggered the question. A card
# tap has no such request; the decision arrives on its own, over the
# socket, whenever the user gets to it.
#
# action.execute closes that gap:
#   { "event": "action.execute", "task_id": "...", "payload": {
#       "action": "open whatsapp",
#       "message": "WhatsApp is open. Go ahead and send your message."
#   }}
# `action` is the exact same string format the client already knows
# how to execute from the `[ACTION:...]` tag today — same whitelist
# (core/permissions.py), same on-device handling, just pushed over the
# socket instead of riding an HTTP response. `message` is the
# confirmation text that would normally accompany it in that response
# — there's no separate event for delivering conversational text
# either, so it rides along here rather than being silently dropped.
# This needs a small addition on the client: listen for this event and
# run it through whatever already executes an [ACTION:...] tag from an
# HTTP reply.
# ================================================================

import uuid

from realtime.events import emit_event

VALID_LEVELS = {
    "read", "write", "execute", "communicate",
    "device_control", "financial", "account_access", "destructive",
}
VALID_DECISIONS = {"allow_once", "always_allow", "deny"}


def new_permission_id() -> str:
    return uuid.uuid4().hex


def emit_permission_required(device_id: str, task_id, permission_id: str,
                             action: str, level: str, reason: str = None) -> bool:
    """Schema §6, server -> client. `level` is validated against the
    schema's permission tiers so a typo at a call site fails loudly
    here instead of silently confusing the client's urgency styling."""
    if level not in VALID_LEVELS:
        print(f"[Permission] '{level}' is not a valid permission level, dropping")
        return False
    payload = {"permission_id": permission_id, "action": action, "level": level}
    if reason:
        payload["reason"] = reason
    sent = emit_event(device_id, "permission.required", payload, task_id=task_id)
    print(f"[Permission] required '{action}' ({level}) for {device_id} "
          f"(task {task_id}) -> {'sent' if sent else 'NOT sent: no live connection'}")
    return sent


def emit_action_execute(device_id: str, task_id, action: str, message: str = None) -> bool:
    """Not in the original schema doc — see module docstring above."""
    payload = {"action": action}
    if message:
        payload["message"] = message
    sent = emit_event(device_id, "action.execute", payload, task_id=task_id)
    print(f"[Permission] action.execute '{action}' for {device_id} "
          f"(task {task_id}) -> {'sent' if sent else 'NOT sent: no live connection'}")
    return sent

