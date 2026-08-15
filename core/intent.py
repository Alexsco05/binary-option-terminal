# ================================================================
# GIDEON — core/intent.py
# ----------------------------------------------------------------
# Two related things:
#
# 1. INTENT DETECTION: recognizes conversational phrasing that
#    implies a device action without being a direct command — "I
#    need to call" vs. the direct "call mom". detect_user_intent()
#    matches these; build_intent_response() (still in server.py,
#    since it depends on personality/weather/news) decides how to
#    respond, often by asking for confirmation via store_pending().
#
# 2. PENDING CONFIRMATIONS: when Gideon asks "should I open
#    WhatsApp?", the pending action is stashed here and resolved on
#    the user's next message (yes/no) via check_user_confirmation().
#
# Moved from server.py with zero behavior change.
# ================================================================

import time

from memory.conversation import PENDING_CONFIRMATIONS
from core.permissions import sanitize_action

INTENT_PATTERNS = {
    "intent_whatsapp":        ["send a message", "send a text", "text someone",
                               "message someone", "whatsapp someone", "i need to text",
                               "i want to message", "i want to send a message",
                               "send on whatsapp"],
    "intent_call":            ["i need to call", "i want to call", "make a call",
                               "ring someone", "phone someone", "give someone a call",
                               "i need to speak to", "i want to talk to",
                               "call someone for me"],
    "intent_alarm":           ["i need to wake up at", "don't let me sleep past",
                               "i have to be up by", "i need a reminder to wake",
                               "remind me to wake", "i need to get up at",
                               "wake me up at"],
    "intent_music":           ["i want to listen", "i feel like listening",
                               "put on some music", "i want some music",
                               "music please", "something to listen to"],
    "intent_open_app":        ["i want to use", "i need to use", "can you open",
                               "take me to", "bring up", "i need to go to",
                               "i want to go to"],
    "intent_screenshot":      ["capture this", "save this screen",
                               "take a picture of the screen",
                               "save what i'm seeing", "snap this"],
    "intent_battery":         ["is my battery okay", "battery dying",
                               "check my battery", "how long will my battery last",
                               "is my phone charged"],
    "intent_brightness_down": ["too bright", "screen too bright", "hurting my eyes",
                               "make it darker", "lower the light", "dim the screen",
                               "reduce brightness", "screen is too bright"],
    "intent_brightness_up":   ["too dim", "can't see the screen", "make it brighter",
                               "increase the light", "screen is too dark",
                               "brighten it up"],
    "intent_volume_down":     ["too loud", "turn it down", "lower the sound",
                               "make it quieter", "sound is too high",
                               "reduce the volume", "lower volume"],
    "intent_volume_up":       ["can't hear", "increase the sound", "make it louder",
                               "sound is too low", "turn it up", "raise the volume"],
    "intent_focus":           ["i need to focus", "help me focus",
                               "i keep getting distracted",
                               "stop me from wasting time",
                               "i need to be productive",
                               "help me stop procrastinating",
                               "i'm wasting time", "put me in focus mode",
                               "help me concentrate"],
    "intent_task":            ["i need to remember to", "don't let me forget to",
                               "add this to my list", "put this on my list",
                               "note this down", "i need to do"],
    "intent_lock":            ["lock up", "secure the phone", "i'm done with my phone",
                               "lock it up", "secure it for me"],
    "intent_sleep":           ["i'm going to sleep", "time for bed", "about to sleep",
                               "heading to bed", "i'm sleepy",
                               "turning in for the night", "i want to sleep",
                               "i need to sleep", "help me sleep",
                               "prepare for bed", "i need rest",
                               "i'm going to rest", "let me sleep", "i'm tired"],
    "intent_weather":         ["is it going to rain", "should i carry an umbrella",
                               "what's the weather like", "how's the weather",
                               "is it hot outside", "is it cold outside",
                               "weather today", "weather outside"],
    "intent_news":            ["what's going on in the world", "any news today",
                               "current events", "what happened today",
                               "what's in the news"],
}


def detect_user_intent(msg: str):
    ml = msg.lower().strip()
    for intent, patterns in INTENT_PATTERNS.items():
        for p in patterns:
            if p in ml:
                return intent
    return None


# ================================================================
# PENDING CONFIRMATIONS
# ================================================================

def store_pending(device_id: str, action: str, follow_up: str):
    PENDING_CONFIRMATIONS[device_id] = {
        "action": action, "follow_up": follow_up, "timestamp": time.time()
    }


def check_user_confirmation(msg: str, device_id: str):
    pending = PENDING_CONFIRMATIONS.get(device_id)
    if not pending:
        return None
    if time.time() - pending.get("timestamp", 0) > 120:
        del PENDING_CONFIRMATIONS[device_id]
        return None
    ml = msg.lower().strip()
    pos = ["yes", "yeah", "yep", "sure", "ok", "okay", "go ahead", "please do",
           "do it", "proceed", "definitely", "of course", "yes please", "yh",
           "aye", "alright", "fine", "do that", "open it", "yes open",
           "go on", "please"]
    neg = ["no", "nope", "don't", "cancel", "stop", "never mind", "nah",
           "not now", "skip it", "forget it", "no thanks", "don't do that",
           "leave it"]
    if any(ml == w or ml.startswith(w + " ") for w in pos):
        action, fu = pending["action"], pending["follow_up"]
        del PENDING_CONFIRMATIONS[device_id]
        return fu, sanitize_action(action)
    if any(ml == w or ml.startswith(w + " ") for w in neg):
        del PENDING_CONFIRMATIONS[device_id]
        return "No problem. Let me know if you need anything.", None
    return None
