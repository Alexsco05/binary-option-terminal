# ================================================================
# GIDEON — device/android.py
# ----------------------------------------------------------------
# Offline command detection: recognizes plain-text device commands
# ("what time is it", "lock my phone") without needing a full AI
# round trip, and builds the [ACTION:...] payload for them. This is
# the fast path for simple device operations — see resolve_immediate_
# reply() in server.py for where it plugs in, right before falling
# through to full AI routing.
#
# Moved from server.py with zero behavior change. Fully self-
# contained — only needs re.
# ================================================================

import re

OFFLINE_COMMANDS = {
    "open":          ["open ", "launch ", "start "],
    "call":          ["call ", "dial "],
    "alarm":         ["set alarm", "wake me up", "alarm for"],
    "timer":         ["set timer", "timer for", "countdown for"],
    "reminder":      ["remind me to ", "set reminder"],
    "volume":        ["volume up", "volume down", "max volume", "min volume",
                      "full volume", "mute phone", "unmute phone",
                      "lower volume", "raise volume", "lower the volume",
                      "raise the volume", "turn up the volume",
                      "turn down the volume"],
    "brightness":    ["increase brightness", "decrease brightness", "max brightness",
                      "min brightness", "full brightness", "lowest brightness",
                      "brighten screen", "dim screen", "brighten the screen",
                      "dim the screen"],
    "flashlight":    ["flashlight on", "flashlight off", "turn on flashlight",
                      "turn off flashlight", "torch on", "torch off"],
    "lock":          ["lock my phone", "lock device", "lock screen", "lock it"],
    "screenshot":    ["take screenshot", "take a screenshot"],
    "battery":       ["battery level", "battery percentage", "how much battery",
                      "check battery", "is my battery", "battery dying"],
    "time":          ["what time is it", "current time", "tell me the time"],
    "date":          ["what date is it", "today's date", "what day is it"],
    "wifi":          ["wifi settings", "turn on wifi", "turn off wifi",
                      "wifi on", "wifi off", "open wifi"],
    "bluetooth":     ["bluetooth settings", "bluetooth on", "bluetooth off",
                      "turn on bluetooth", "turn off bluetooth"],
    "silent":        ["silent mode", "vibrate mode", "ring mode"],
    "dnd":           ["do not disturb on", "do not disturb off", "dnd on", "dnd off"],
    "tasks":         ["show my tasks", "my tasks", "add task ",
                      "complete task", "show tasks"],
    "screen":        ["read my screen", "what do you see", "what's on my screen",
                      "what is on my screen", "read the screen"],
    "back":          ["go back"],
    "home":          ["go home", "home screen"],
    "recents":       ["recent apps", "open recent apps"],
    "notifications": ["open notifications", "read my notifications",
                      "read notifications"],
    "settings":      ["open settings", "open phone settings"],
    "search":        ["search for ", "search on google", "youtube search "],
    "calculate":     ["calculate ", " plus ", " minus ", " times ",
                      " divided by ", "percent of", "square root"],
    "clipboard":     ["read clipboard", "what did i copy"],
    "storage":       ["how much storage", "storage space", "check storage"],
    "internet":      ["check internet", "am i connected", "internet status"],
    "phone_info":    ["what phone do i have", "phone model", "device info"],
    "media_play":    ["play music", "play a song"],
    "media_pause":   ["pause music", "pause that", "stop the music"],
    "media_next":    ["next song", "skip song", "skip this"],
    "strict_mode":   ["strict mode on", "strict mode off", "focus mode on",
                      "focus mode off", "discipline mode"],
    "study_mode":    ["study mode", "start studying"],
    "sleep_mode":    ["sleep mode", "bedtime mode"],
    "work_mode":     ["work mode", "start work mode"],
    "morning":       ["morning routine", "start my day routine"],
}

# Phrases that look like commands but are usually conversational —
# require a more specific match before triggering, to cut false positives
# like "explain volume in physics" or "what is Morse code".
AMBIGUOUS_GUARD_WORDS = {
    "volume": ["physics", "explain", "what is", "definition", "math", "meaning"],
    "calculate": ["explain", "what is", "history of", "concept of"],
}


def detect_offline_command(msg: str):
    ml = msg.lower().strip()
    for cmd, patterns in OFFLINE_COMMANDS.items():
        guard_words = AMBIGUOUS_GUARD_WORDS.get(cmd, [])
        if guard_words and any(g in ml for g in guard_words):
            continue
        for p in patterns:
            if p in ml:
                # "calculate" patterns include very loose substrings like
                # " plus ", " minus ", " times " which match ordinary
                # conversation ("how many times have I asked you") far
                # more often than real math requests. Real calculations
                # almost always include an actual digit, so require one.
                if cmd == "calculate" and not re.search(r'\d', ml):
                    continue
                return cmd
    return None


def build_action_trigger(offline_type: str, msg: str) -> str:
    ml = msg.lower().strip()
    if offline_type == "open":
        for w in ["open ", "launch ", "start "]:
            if w in ml:
                a = ml.replace(w.strip(), "", 1).strip()
                a = a.replace(" the ", " ").replace(" app", "").strip()
                return f"open {a}" if a else "open"
        return "open"
    if offline_type == "call":
        for w in ["call ", "dial "]:
            if ml.startswith(w):
                c = ml[len(w):].strip()
                return f"call {c}" if c else "call"
        return "call"
    if offline_type == "search":
        for w in ["search for ", "search on google ", "youtube search "]:
            if ml.startswith(w):
                q = ml[len(w):].strip()
                return f"search for {q}" if q else ml
        return ml
    passthrough = ["alarm", "timer", "tasks", "volume", "brightness",
                   "strict_mode", "calculate", "settings", "reminder",
                   "silent", "dnd"]
    if offline_type in passthrough:
        return ml
    action_map = {
        "lock": "lock my phone", "screenshot": "take screenshot",
        "flashlight": "flashlight on", "battery": "battery level",
        "screen": "read my screen", "back": "go back", "home": "go home",
        "recents": "recent apps", "media_play": "play music",
        "media_pause": "pause music", "media_next": "next song",
        "wifi": "wifi settings", "bluetooth": "bluetooth settings",
        "notifications": "open notifications", "storage": "how much storage",
        "internet": "check internet", "phone_info": "what phone do i have",
        "time": "what time is it", "date": "what date is it",
        "clipboard": "read clipboard", "study_mode": "study mode",
        "sleep_mode": "sleep mode", "work_mode": "work mode",
        "morning": "morning routine",
    }
    return action_map.get(offline_type, ml)
