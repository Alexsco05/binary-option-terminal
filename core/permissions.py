# ================================================================
# GIDEON — core/permissions.py
# ----------------------------------------------------------------
# Action whitelisting: the model could otherwise hallucinate an
# action tag like [ACTION:factory reset] and the phone would attempt
# it. Every action trigger is checked against this prefix whitelist
# before being sent to the Android client. Anything outside this
# list is stripped and logged, never forwarded.
#
# Moved from server.py with zero behavior change.
# ================================================================

import json

from core.text import _safe_json_loads

ALLOWED_ACTION_PREFIXES = [
    "open", "launch", "call", "dial", "search", "set alarm", "alarm",
    "set timer", "timer", "remind", "reminder", "add task", "complete task",
    "show tasks", "show my tasks",
    "volume up", "volume down", "max volume", "min volume", "full volume",
    "mute phone", "unmute phone", "lower volume", "raise volume",
    "increase brightness", "decrease brightness", "max brightness",
    "min brightness", "full brightness", "lowest brightness",
    "brighten screen", "dim screen",
    "flashlight", "torch",
    "lock my phone", "lock device", "lock screen", "lock it",
    "take screenshot", "battery level", "battery percentage",
    "what time is it", "current time", "what date is it", "today's date",
    "wifi", "bluetooth",
    "silent mode", "vibrate mode", "ring mode",
    "do not disturb", "dnd",
    "read my screen", "what do you see", "what's on my screen",
    "go back", "go home", "home screen", "recent apps",
    "open notifications", "read my notifications", "read notifications",
    "open settings", "open phone settings",
    "calculate", "read clipboard", "what did i copy",
    "how much storage", "storage space", "check storage",
    "check internet", "am i connected", "internet status",
    "what phone do i have", "phone model", "device info",
    "play music", "play a song", "pause music", "pause that",
    "stop the music", "next song", "skip song", "skip this",
    "strict mode", "focus mode", "discipline mode",
    "study mode", "start studying", "sleep mode", "bedtime mode",
    "work mode", "start work mode", "morning routine", "start my day",

    # Added: these were fully missing before, meaning OfflineCommandHandler
    # supported them on the Android side but sanitize_action() dropped
    # every attempt to trigger them, silently, no matter how the model
    # phrased the request. Wording matches OfflineCommandHandler.kt's own
    # msg.contains() checks exactly, so passing this whitelist and
    # matching on-device rely on the same words.
    "game mode", "reading mode", "commute mode",
    "presentation mode", "meeting mode", "emergency",
    "phone health", "optimize", "daily report", "end of day",
    "my score", "how productive", "productivity",
    "screen time", "phone usage",
    "unlock", "split screen", "split app",
    "hotspot", "vpn settings", "open vpn", "nfc settings", "open nfc",
    "developer settings", "developer options",
    "language settings", "keyboard settings", "input settings",
    "date settings", "time settings", "change date", "change time",
    "security settings", "screen lock", "fingerprint", "face unlock",
    "accessibility settings", "open accessibility",
    "app settings", "manage apps", "installed apps",
    "notification settings", "manage notifications",
    "about phone", "about device", "device model",
    "gps settings", "location settings",
    "power off menu", "power menu",
    "airplane mode", "flight mode", "gaming mode",
    "battery saver", "battery settings", "power saving",
    "turn on data", "turn off data", "data on", "data off",
    "mobile data on", "mobile data off", "disable data", "enable data",
    "turn on location", "turn off location", "turn on screen",
    "my tasks", "task done", "finished task", "new task",
    "pending tasks", "what are my tasks",
]

# JSON-shaped tool calls (sms, calendar, email, etc.) can't be checked
# against a prefix whitelist the way plain-English commands can, so they
# get their own validation: the "tool" key must be one of these, and the
# JSON must actually parse. Anything else is dropped, same safety intent
# as ALLOWED_ACTION_PREFIXES above.
ALLOWED_TOOLS = {
    "sms", "calendar", "email", "clipboard", "navigate",
    "location", "whatsapp", "contact", "filesearch", "device",
}


def is_action_allowed(action: str) -> bool:
    if not action:
        return False
    al = action.lower().strip()
    return any(al.startswith(p) or p in al[:40] for p in ALLOWED_ACTION_PREFIXES)


def sanitize_action(action):
    """
    Returns the action only if it passes validation, else None.

    Two accepted shapes:
      1. Legacy plain-English device commands ("open whatsapp",
         "flashlight on", etc.) — checked against
         ALLOWED_ACTION_PREFIXES, unchanged from before.
      2. JSON tool calls ({"tool": "sms", "params": {...}}) — checked
         against ALLOWED_TOOLS instead, since a prefix whitelist can't
         validate a JSON blob. Re-serialized from the parsed dict
         rather than passed through as raw model text, so what reaches
         the phone is always well-formed JSON built only from keys the
         model actually produced.
    Anything that matches neither shape is dropped rather than
    forwarded.
    """
    if not action:
        return None
    stripped = action.strip()
    if stripped.startswith("{"):
        parsed = _safe_json_loads(stripped)
        if not isinstance(parsed, dict):
            print(f"[Security] Malformed tool action_trigger dropped: {stripped[:120]}")
            return None
        tool = parsed.get("tool")
        if tool not in ALLOWED_TOOLS:
            print(f"[Security] Unknown tool in action_trigger dropped: {tool}")
            return None
        return json.dumps(parsed)
    if is_action_allowed(stripped):
        return stripped
    print(f"[Security] Blocked unrecognized action: '{stripped[:120]}'")
    return None
