# ================= GIDEON BACKEND =================
# Creator: Alexsco (Adegolu Alex)
# Version: 7.0 - Intent-First Brain

from flask import Flask, request, jsonify
import os
import requests
import json
import threading
import datetime
import re

app = Flask(__name__)

# ================= CONFIG =================
BOT_NAME = "Gideon"

GROQ_KEYS = [
    os.getenv("GROQ_KEY_1", ""),
    os.getenv("GROQ_KEY_2", "")
]

OPENROUTER_KEYS = [
    os.getenv("OPENROUTER_KEY_1", ""),
    os.getenv("OPENROUTER_KEY_2", "")
]

GEMINI_KEY = [
    os.getenv("GEMINI_KEY_1", ""),
    os.getenv("GEMINI_KEY_2", "")
]

MISTRAL_KEY = [
    os.getenv("MISTRAL_KEY_1", ""),
    os.getenv("MISTRAL_KEY_2", "")
]

COHERE_KEY = [
    os.getenv("COHERE_KEY_1", ""),
    os.getenv("COHERE_KEY_2", "")
]

WEATHER_KEY = os.getenv("WEATHER_KEY", "")
NEWS_KEY = os.getenv("NEWS_KEY", "")

# ================= MODEL REGISTRY =================
MODELS = {
    "fast": {
        "primary": {"provider": "groq", "model": "llama-3.1-8b-instant"},
        "fallback": {"provider": "openrouter",
                     "model": "meta-llama/llama-3.1-8b-instruct:free"}
    },
    "complex": {
        "primary": {"provider": "groq", "model": "llama-3.3-70b-versatile"},
        "fallback": {"provider": "gemini", "model": "gemini-1.5-flash"}
    },
    "creative": {
        "primary": {"provider": "groq", "model": "llama-3.3-70b-versatile"},
        "fallback": {"provider": "openrouter",
                     "model": "mistralai/mistral-7b-instruct:free"}
    },
    "empathetic": {
        "primary": {"provider": "groq", "model": "llama-3.3-70b-versatile"},
        "fallback": {"provider": "cohere", "model": "command-r"}
    },
    "firm": {
        "primary": {"provider": "groq", "model": "llama-3.1-8b-instant"},
        "fallback": {"provider": "openrouter",
                     "model": "mistralai/mistral-7b-instruct:free"}
    },
    "math": {
        "primary": {"provider": "openrouter",
                    "model": "qwen/qwen-2-math-72b-instruct:free"},
        "fallback": {"provider": "groq", "model": "llama-3.3-70b-versatile"}
    },
    "vision": {
        "primary": {"provider": "gemini", "model": "gemini-1.5-flash"},
        "fallback": {"provider": "groq", "model": "llama-3.1-8b-instant"}
    },
    "coding": {
        "primary": {"provider": "openrouter",
                    "model": "deepseek/deepseek-coder:free"},
        "fallback": {"provider": "groq", "model": "llama-3.3-70b-versatile"}
    },
    "weather": {
        "primary": {"provider": "groq", "model": "llama-3.1-8b-instant"},
        "fallback": {"provider": "openrouter",
                     "model": "meta-llama/llama-3.1-8b-instruct:free"}
    },
    "news": {
        "primary": {"provider": "groq", "model": "llama-3.1-8b-instant"},
        "fallback": {"provider": "openrouter",
                     "model": "meta-llama/llama-3.1-8b-instruct:free"}
    },
}

# ================= CACHE AND MEMORY =================
CACHE = {}
USER_SHORT_TERM = {}
MEMORY_LIMIT = 20
PENDING_CONFIRMATIONS = {}


def get_short_term(device_id: str):
    if device_id not in USER_SHORT_TERM:
        USER_SHORT_TERM[device_id] = [
            {"role": "system", "content": ""}
        ]
    return USER_SHORT_TERM[device_id]


# ================= FILE PATHS =================
def get_user_files(device_id: str):
    safe_id = "".join(
        c for c in device_id if c.isalnum() or c == "-"
    )[:36]
    return {
        "personality": f"personality_{safe_id}.json",
        "history": f"history_{safe_id}.json"
    }


# ================= HISTORY =================
def load_history(device_id: str):
    try:
        path = get_user_files(device_id)["history"]
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return []


def save_history(history: list, device_id: str):
    try:
        path = get_user_files(device_id)["history"]
        with open(path, "w") as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        print(f"[Memory] Failed to save history: {e}")


# ================= PERSONALITY =================
def load_personality(device_id: str):
    try:
        path = get_user_files(device_id)["personality"]
        with open(path, "r") as f:
            return json.load(f)
        # sanitize name fields to remove any corruption
        data["name"] = clean_name(data.get("name", "User")) or "User"
        data["nickname"] = clean_name(
            data.get("nickname", "")
        ) or data["name"]
        return data
    except Exception:
        return {
            "name": "User",
            "nickname": "User",
            "facts": [],
            "preferences": [],
            "people": [],
            "locations": [],
            "mood": "neutral",
            "mood_history": [],
            "last_seen": ""
        }


def save_personality(data: dict, device_id: str):
    try:
        path = get_user_files(device_id)["personality"]
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[Memory] Failed to save personality: {e}")


# ================= MEMORY UPDATES =================
def update_short_term(user_msg: str, bot_reply: str, device_id: str):
    st = get_short_term(device_id)
    st.append({"role": "user", "content": user_msg})
    st.append({"role": "assistant", "content": bot_reply})
    while len(st) > MEMORY_LIMIT:
        del st[1]


def update_long_term(user_msg: str, bot_reply: str, device_id: str):
    history = load_history(device_id)
    history.append({
        "timestamp": datetime.datetime.now().isoformat(),
        "user": user_msg,
        "gideon": bot_reply
    })
    if len(history) > 100:
        history = summarize_history(history, device_id)
    save_history(history, device_id)


def summarize_history(history: list, device_id: str):
    try:
        recent = history[-40:]
        older = history[:-40]
        older_text = "\n".join([
            f"User: {h['user']}\nGideon: {h['gideon']}"
            for h in older
        ])
        summary = call_groq_raw(
            f"Summarize this conversation into a short paragraph: {older_text}"
        )
        if summary:
            return [{
                "timestamp": datetime.datetime.now().isoformat(),
                "user": "[Summary]",
                "gideon": summary
            }] + recent
    except Exception as e:
        print(f"[Memory] Summarization failed: {e}")
    return history[-40:]


# ================= FACT EXTRACTION =================
def extract_facts(user_msg: str, device_id: str):
    threading.Thread(
        target=_extract_facts_thread,
        args=(user_msg, device_id),
        daemon=True
    ).start()


def _extract_facts_thread(user_msg: str, device_id: str):
    try:
        personality = load_personality(device_id)
        name = personality.get("nickname") or personality.get("name", "User")

        result = call_groq_raw(
            f"Extract personal facts about {name} from this message. "
            f"Return ONLY a valid JSON object with these exact keys: "
            f"facts, preferences, people, locations, mood. "
            f"Each key except mood is a list of short strings. "
            f"mood is a single word like happy, sad, neutral, excited. "
            f"If nothing to extract return exactly: "
            f'{{"facts":[],"preferences":[],"people":[],"locations":[],"mood":"neutral"}} '
            f"Message: {user_msg}"
        )

        if not result:
            return

        clean = result.strip()
        clean = clean.replace("```json", "").replace("```", "").strip()
        start = clean.find("{")
        end = clean.rfind("}") + 1
        if start == -1 or end == 0:
            return

        extracted = json.loads(clean[start:end])

        for key in ["facts", "preferences", "people", "locations"]:
            for item in extracted.get(key, []):
                if item and item not in personality.get(key, []):
                    if key not in personality:
                        personality[key] = []
                    personality[key].append(item)

        mood = extracted.get("mood", "")
        if mood and mood != "neutral":
            personality["mood"] = mood
            if "mood_history" not in personality:
                personality["mood_history"] = []
            personality["mood_history"].append({
                "timestamp": datetime.datetime.now().isoformat(),
                "mood": mood
            })
            personality["mood_history"] = personality["mood_history"][-20:]

        personality["last_seen"] = datetime.datetime.now().isoformat()
        save_personality(personality, device_id)

    except Exception as e:
        print(f"[Memory] Fact extraction failed: {e}")


# ================= ACTION TRIGGER PARSER =================
def extract_action_trigger(reply: str):
    pattern = r'\[ACTION:([^\]]+)\]'
    match = re.search(pattern, reply)
    if match:
        action = match.group(1).strip()
        clean = re.sub(pattern, '', reply).strip()
        return clean, action
    return reply, None


# ================= OFFLINE COMMAND DETECTION =================
# IMPORTANT: patterns use full phrases with spaces to prevent
# false matches. "what's happening" should NOT match "what is"
OFFLINE_COMMANDS = {
    "open":        ["open ", "launch ", "start "],
    "call":        ["call ", "dial "],
    "alarm":       ["set alarm", "wake me up", "alarm for"],
    "timer":       ["set timer", "timer for", "countdown for"],
    "reminder":    ["remind me to ", "set reminder"],
    "volume":      ["volume up", "volume down", "max volume",
                    "min volume", "full volume", "mute phone",
                    "unmute phone", "lower volume", "raise volume"],
    "brightness":  ["increase brightness", "decrease brightness",
                    "max brightness", "min brightness",
                    "full brightness", "lowest brightness",
                    "brighten screen", "dim screen"],
    "flashlight":  ["flashlight on", "flashlight off",
                    "turn on flashlight", "turn off flashlight",
                    "torch on", "torch off"],
    "lock":        ["lock my phone", "lock device",
                    "lock screen", "lock it"],
    "screenshot":  ["take screenshot", "take a screenshot"],
    "battery":     ["battery level", "battery percentage",
                    "how much battery", "check battery"],
    "time":        ["what time is it", "current time",
                    "tell me the time"],
    "date":        ["what date is it", "today's date",
                    "what day is it"],
    "wifi":        ["wifi settings", "turn on wifi", "turn off wifi",
                    "wifi on", "wifi off", "open wifi"],
    "bluetooth":   ["bluetooth settings", "bluetooth on",
                    "bluetooth off", "turn on bluetooth",
                    "turn off bluetooth"],
    "silent":      ["silent mode", "vibrate mode", "ring mode"],
    "dnd":         ["do not disturb on", "do not disturb off",
                    "dnd on", "dnd off"],
    "tasks":       ["show my tasks", "my tasks", "add task ",
                    "complete task", "show tasks"],
    "screen":      ["read my screen", "what do you see",
                    "what's on my screen", "what is on my screen",
                    "read the screen"],
    "back":        ["go back"],
    "home":        ["go home", "home screen"],
    "recents":     ["recent apps", "open recent apps"],
    "notifications": ["open notifications", "read my notifications",
                      "read notifications"],
    "settings":    ["open settings", "open phone settings"],
    "search":      ["search for ", "search on google",
                    "youtube search "],
    "calculate":   ["calculate ", " plus ", " minus ",
                    " times ", " divided by ", "percent of",
                    "square root"],
    "clipboard":   ["read clipboard", "what did i copy"],
    "storage":     ["how much storage", "storage space",
                    "check storage"],
    "internet":    ["check internet", "am i connected",
                    "internet status"],
    "phone_info":  ["what phone do i have", "phone model",
                    "device info"],
    "media_play":  ["play music", "play a song"],
    "media_pause": ["pause music", "pause that",
                    "stop the music"],
    "media_next":  ["next song", "skip song", "skip this"],
    "strict_mode": ["strict mode on", "strict mode off",
                    "focus mode on", "focus mode off",
                    "discipline mode"],
    "study_mode":  ["study mode", "start studying"],
    "sleep_mode":  ["sleep mode", "bedtime mode"],
    "work_mode":   ["work mode", "start work mode"],
    "morning":     ["morning routine", "start my day routine"],
}


def detect_offline_command(msg: str):
    msg_lower = msg.lower().strip()
    for cmd_type, patterns in OFFLINE_COMMANDS.items():
        for pattern in patterns:
            if pattern in msg_lower:
                return cmd_type
    return None


# ================= ACTION TRIGGER BUILDER =================
def build_action_trigger(offline_type: str, msg: str) -> str:
    msg_lower = msg.lower().strip()

    if offline_type == "open":
        for word in ["open ", "launch ", "start "]:
            if word in msg_lower:
                app = msg_lower.replace(word.strip(), "").strip()
                app = app.replace(" the ", " ").replace(" app", "").strip()
                if app:
                    return f"open {app}"
        return "open"

    if offline_type == "call":
        for word in ["call ", "dial "]:
            if word in msg_lower:
                contact = msg_lower.replace(word.strip(), "").strip()
                if contact:
                    return f"call {contact}"
        return "call"

    if offline_type == "search":
        for word in ["search for ", "search on google ", "youtube search "]:
            if word in msg_lower:
                query = msg_lower.replace(word.strip(), "").strip()
                if query:
                    return f"search for {query}"
        return msg_lower

    # these pass the full message so Android can extract details
    passthrough = ["alarm", "timer", "tasks", "volume",
                   "brightness", "strict_mode", "calculate",
                   "settings", "reminder"]
    if offline_type in passthrough:
        return msg_lower

    action_map = {
        "lock":          "lock my phone",
        "screenshot":    "take screenshot",
        "flashlight":    "flashlight on",
        "battery":       "battery level",
        "screen":        "read my screen",
        "back":          "go back",
        "home":          "go home",
        "recents":       "recent apps",
        "media_play":    "play music",
        "media_pause":   "pause music",
        "media_next":    "next song",
        "silent":        msg_lower,
        "wifi":          "wifi settings",
        "bluetooth":     "bluetooth settings",
        "dnd":           msg_lower,
        "notifications": "open notifications",
        "storage":       "how much storage",
        "internet":      "check internet",
        "phone_info":    "what phone do i have",
        "time":          "what time is it",
        "date":          "what date is it",
        "clipboard":     "read clipboard",
        "study_mode":    "study mode",
        "sleep_mode":    "sleep mode",
        "work_mode":     "work mode",
        "morning":       "morning routine",
    }

    return action_map.get(offline_type, msg_lower)


# ================= INTENT UNDERSTANDING =================
# These match natural language expressions, not commands
INTENT_PATTERNS = {
    "intent_whatsapp": [
        "send a message", "send a text", "text someone",
        "message someone", "whatsapp someone",
        "i need to text", "i want to message",
        "reach out to someone", "send on whatsapp",
        "i want to send a message"
    ],
    "intent_call": [
        "i need to call", "i want to call", "make a call",
        "ring someone", "phone someone",
        "give someone a call", "i need to speak to",
        "i want to talk to", "call someone for me"
    ],
    "intent_alarm": [
        "i need to wake up at", "don't let me sleep past",
        "i have to be up by", "i need a reminder to wake",
        "remind me to wake", "i need to get up at",
        "wake me up at"
    ],
    "intent_music": [
        "i want to listen", "i feel like listening",
        "put on some music", "i want some music",
        "music please", "something to listen to",
        "i want to hear music"
    ],
    "intent_open_app": [
        "i want to use", "i need to use",
        "can you open", "take me to",
        "bring up", "i need to go to",
        "i want to go to"
    ],
    "intent_screenshot": [
        "capture this", "save this screen",
        "take a picture of the screen",
        "save what i'm seeing", "snap this"
    ],
    "intent_battery": [
        "is my battery okay", "battery dying",
        "check my battery", "how long will my battery last",
        "is my phone charged"
    ],
    "intent_brightness_down": [
        "too bright", "screen too bright", "hurting my eyes",
        "make it darker", "lower the light",
        "dim the screen", "reduce brightness",
        "screen is too bright"
    ],
    "intent_brightness_up": [
        "too dim", "can't see the screen", "make it brighter",
        "increase the light", "screen is too dark",
        "brighten it up"
    ],
    "intent_volume_down": [
        "too loud", "turn it down", "lower the sound",
        "make it quieter", "sound is too high",
        "reduce the volume", "lower volume"
    ],
    "intent_volume_up": [
        "can't hear", "increase the sound",
        "make it louder", "sound is too low",
        "turn it up", "raise the volume"
    ],
    "intent_focus": [
        "i need to focus", "help me focus",
        "i keep getting distracted",
        "stop me from wasting time",
        "i need to be productive",
        "help me stop procrastinating",
        "i'm wasting time", "put me in focus mode",
        "help me concentrate"
    ],
    "intent_task": [
        "i need to remember to", "don't let me forget to",
        "add this to my list", "put this on my list",
        "note this down", "i need to do"
    ],
    "intent_lock": [
        "lock up", "secure the phone",
        "i'm done with my phone", "lock it up",
        "secure it for me"
    ],
    "intent_sleep": [
    "i'm going to sleep", "time for bed",
    "about to sleep", "heading to bed",
    "i'm sleepy", "turning in for the night",
    "i want to sleep", "i need to sleep",
    "setting up for sleep",
    "help me sleep", "prepare for bed",
    "i need rest", "i'm going to rest",
    "let me sleep"
],
    "intent_weather": [
        "is it going to rain", "should i carry an umbrella",
        "what's the weather like", "how's the weather",
        "is it hot outside", "is it cold outside",
        "weather today", "weather outside"
    ],
    "intent_news": [
        "what's going on in the world", "any news today",
        "current events", "what happened today",
        "what's in the news"
    ],
}


def detect_user_intent(msg: str):
    msg_lower = msg.lower().strip()
    for intent, patterns in INTENT_PATTERNS.items():
        for pattern in patterns:
            if pattern in msg_lower:
                return intent
    return None


# ================= PENDING CONFIRMATION SYSTEM =================
def store_pending(device_id: str, action: str, follow_up: str):
    PENDING_CONFIRMATIONS[device_id] = {
        "action": action,
        "follow_up": follow_up
    }


def check_user_confirmation(msg: str, device_id: str):
    pending = PENDING_CONFIRMATIONS.get(device_id)
    if not pending:
        return None

    msg_lower = msg.lower().strip()

    positive = [
        "yes", "yeah", "yep", "sure", "ok", "okay",
        "go ahead", "please do", "do it", "proceed",
        "definitely", "of course", "yes please",
        "yh", "aye", "alright", "fine", "do that",
        "open it", "yes open", "go on", "please"
    ]
    negative = [
        "no", "nope", "don't", "cancel", "stop",
        "never mind", "nah", "not now", "skip it",
        "forget it", "no thanks", "don't do that", "leave it"
    ]

    is_positive = any(
        msg_lower == w or msg_lower.startswith(w + " ")
        for w in positive
    )
    is_negative = any(
        msg_lower == w or msg_lower.startswith(w + " ")
        for w in negative
    )

    if is_positive:
        action = pending["action"]
        follow_up = pending["follow_up"]
        del PENDING_CONFIRMATIONS[device_id]
        print(f"[Confirm] Confirmed. Executing: {action}")
        return follow_up, action

    if is_negative:
        del PENDING_CONFIRMATIONS[device_id]
        return "No problem. Let me know if you need anything.", None

    return None


# ================= INTENT ACTION BUILDER =================
def build_intent_response(intent: str, msg: str,
                          personality: dict, device_id: str):
    name = personality.get("nickname") or personality.get("name", "")
    n = f"{name}, " if name else ""
    msg_lower = msg.lower()

    print(f"[Intent] Detected: {intent}")

    # ── DIRECT ACTIONS (no confirmation needed) ──────────────────
    if intent == "intent_sleep":
        store_pending(device_id, "sleep mode",
                      "Sleep mode is set up. Goodnight.")
        return (
            f"Goodnight{', ' + name if name else ''}. "
            f"Should I set up sleep mode for you now? "
            f"I will dim the screen, lower volume, and enable do not disturb."
        ), None

    if intent == "intent_brightness_down":
        return f"{n}dimming your screen now.", "min brightness"

    if intent == "intent_brightness_up":
        return f"{n}increasing brightness now.", "max brightness"

    if intent == "intent_volume_down":
        return f"{n}lowering the volume now.", "min volume"

    if intent == "intent_volume_up":
        return f"{n}turning up the volume.", "max volume"

    if intent == "intent_battery":
        return f"{n}checking your battery.", "battery level"

    if intent == "intent_lock":
        return f"{n}locking your phone now.", "lock my phone"

    if intent == "intent_screenshot":
        return f"{n}taking a screenshot now.", "take screenshot"

    if intent == "intent_weather":
        return f"{n}checking the weather for you.", "weather"

    if intent == "intent_news":
        return f"{n}getting the latest news.", "latest news"

    # ── FOCUS MODE ───────────────────────────────────────────────
    if intent == "intent_focus":
        store_pending(device_id, "strict mode focus",
                      "Focus mode is active. Distractions limited.")
        return (
            f"{n}should I activate focus mode? "
            f"I will limit distractions and help you stay on track."
        ), None

    # ── WHATSAPP ─────────────────────────────────────────────────
    if intent == "intent_whatsapp":
        store_pending(device_id, "open whatsapp",
                      "WhatsApp is open. Go ahead and send your message.")
        return (
            f"{n}should I open WhatsApp for you?"
        ), None

    # ── CALL ─────────────────────────────────────────────────────
    if intent == "intent_call":
        for skip in ["i need to call", "i want to call",
                     "make a call to", "ring", "phone"]:
            if skip in msg_lower:
                contact = msg_lower.replace(skip, "").strip()
                if contact and len(contact) > 1:
                    store_pending(device_id, f"call {contact}",
                                  f"Calling {contact}.")
                    return (
                        f"{n}should I call {contact} for you?"
                    ), None
        return (
            f"{n}who would you like me to call?"
        ), None

    # ── OPEN APP ─────────────────────────────────────────────────
    if intent == "intent_open_app":
        for skip in ["i want to use", "i need to use",
                     "can you open", "take me to",
                     "bring up", "i need to go to",
                     "i want to go to"]:
            if skip in msg_lower:
                app = msg_lower.replace(skip, "").strip()
                app = app.replace(" the ", " ").replace(" app", "").strip()
                if app and len(app) > 1:
                    store_pending(device_id, f"open {app}",
                                  f"Opening {app} for you.")
                    return (
                        f"{n}should I open {app} for you?"
                    ), None
        return (
            f"{n}which app would you like me to open?"
        ), None

    # ── MUSIC ────────────────────────────────────────────────────
    if intent == "intent_music":
        store_pending(device_id, "open spotify",
                      "Opening your music app.")
        return (
            f"{n}should I open your music app?"
        ), None

    # ── ALARM ────────────────────────────────────────────────────
    if intent == "intent_alarm":
        time_match = re.search(
            r'(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)', msg_lower
        )
        if time_match:
            t = time_match.group(1).strip()
            store_pending(device_id, f"set alarm for {t}",
                          f"Alarm set for {t}.")
            return (
                f"{n}should I set an alarm for {t}?"
            ), None
        return (
            f"{n}what time should I set the alarm for?"
        ), None

    # ── TASK ─────────────────────────────────────────────────────
    if intent == "intent_task":
        for skip in ["i need to remember to",
                     "don't let me forget to",
                     "add this to my list",
                     "put this on my list",
                     "note this down",
                     "i need to do"]:
            if skip in msg_lower:
                task = msg_lower.replace(skip, "").strip()
                if task and len(task) > 2:
                    store_pending(device_id, f"add task {task}",
                                  f"Task added: {task}.")
                    return (
                        f"{n}should I add '{task}' to your tasks?"
                    ), None
        return (
            f"{n}what task should I add?"
        ), None

    return None, None


# ================= MODEL ROUTER =================
def route_model(msg: str, personality: dict) -> str:
    msg_lower = msg.lower()
    mood = personality.get("mood", "neutral")

    coding_keywords = [
        "code", "program", "debug", "error", "kotlin", "python",
        "java", "function", "class", "compile", "gradle", "syntax",
        "algorithm", "api", "json", "xml", "crash", "exception"
    ]
    if any(k in msg_lower for k in coding_keywords):
        return "coding"

    complex_keywords = [
        "explain", "analyze", "compare", "why", "how does",
        "difference between", "pros and cons", "write a",
        "summarize", "translate", "essay", "story",
        "philosophy", "meaning of", "history of"
    ]
    if any(k in msg_lower for k in complex_keywords):
        return "complex"

    humor_keywords = [
        "joke", "funny", "humor", "laugh", "roast",
        "prank", "silly", "entertain", "riddle", "make me laugh"
    ]
    if any(k in msg_lower for k in humor_keywords):
        return "creative"

    math_keywords = [
        "calculate", "solve", "equation", "integral",
        "derivative", "algebra", "geometry", "trigonometry",
        "statistics", "probability", "matrix", "calculus", "formula"
    ]
    if any(k in msg_lower for k in math_keywords):
        return "math"

    weather_keywords = [
        "weather", "temperature", "rain", "forecast",
        "hot outside", "cold outside", "sunny", "cloudy"
    ]
    if any(k in msg_lower for k in weather_keywords):
        return "weather"

    news_keywords = [
        "latest news", "news today", "current events",
        "what happened today", "headlines"
    ]
    if any(k in msg_lower for k in news_keywords):
        return "news"

    emotional_keywords = [
        "sad", "depressed", "anxious", "lonely", "stressed",
        "worried", "scared", "angry", "upset", "hurt",
        "heartbreak", "crying", "i feel", "i am tired",
        "nobody cares", "give up", "hopeless"
    ]
    if any(k in msg_lower for k in emotional_keywords):
        return "empathetic"

    strict_keywords = [
        "shut up", "stupid", "idiot", "useless", "hate you",
        "terrible", "worst", "rubbish", "nonsense", "dumb",
        "you are trash", "garbage", "pathetic"
    ]
    if any(k in msg_lower for k in strict_keywords):
        return "firm"

    if mood in ["sad", "depressed", "lonely", "anxious"]:
        return "empathetic"
    if mood in ["happy", "excited", "playful"]:
        return "creative"

    return "fast"


# ================= MOOD INSTRUCTION =================
def get_mood_instruction(route: str) -> str:
    if route == "empathetic":
        return (
            "CURRENT MODE: Empathetic support. "
            "The user may be feeling emotional. "
            "Respond with warmth and care. "
            "Validate feelings before offering solutions."
        )
    if route == "creative":
        return (
            "CURRENT MODE: Creative and playful. "
            "Be witty, fun, and engaging. "
            "Use light humor where natural."
        )
    if route == "complex":
        return (
            "CURRENT MODE: Deep thinking. "
            "Give a thorough, well-reasoned response. "
            "Be clear but conversational."
        )
    if route == "coding":
        return (
            "CURRENT MODE: Developer assistance. "
            "Be precise, technical, and practical. "
            "Provide working code examples."
        )
    if route == "firm":
        return (
            "CURRENT MODE: Firm and dignified. "
            "The user is being rude. "
            "Respond calmly but with self-respect. "
            "Set a polite boundary and redirect."
        )
    return ""


# ================= SYSTEM PROMPT =================
def build_system_prompt(personality: dict, route: str = "fast") -> str:
    name = personality.get("nickname") or personality.get("name", "User")
    mood = personality.get("mood", "neutral")
    facts = personality.get("facts", [])
    prefs = personality.get("preferences", [])

    facts_text = ""
    if facts:
        facts_text = (
            f"What you know about {name}: {', '.join(facts[:10])}. "
        )

    prefs_text = ""
    if prefs:
        prefs_text = (
            f"Their preferences: {', '.join(prefs[:5])}. "
        )

    mood_instruction = get_mood_instruction(route)

    return (
        f"You are Gideon, an advanced AI assistant running on "
        f"{name}'s Android phone. "
        f"You are not just a chatbot. You have full control over the phone.\n\n"

        f"YOUR IDENTITY:\n"
        f"Your name is Gideon. "
        f"You were built by Alexsco (Adegolu Alex), a Nigerian developer. "
        f"You run directly on the user's Android device.\n\n"

        f"YOUR CAPABILITIES:\n"
        f"Open apps, make calls, lock device, control volume, "
        f"flashlight, screenshots, media, alarms, reminders, timers, "
        f"read screen, read clipboard, read notifications, check WiFi, "
        f"check battery, control brightness, silent mode, do not disturb, "
        f"navigation, web search, calculations, storage, device info, "
        f"strict mode, task management, productivity tracking.\n\n"

        f"SMART ACTION SYSTEM:\n"
        f"When the user asks you to perform a device action, you MUST "
        f"include [ACTION:command] at the end of your reply.\n"
        f"Examples:\n"
        f"'open whatsapp' -> Opening WhatsApp now. [ACTION:open whatsapp]\n"
        f"'too bright' -> Dimming your screen. [ACTION:min brightness]\n"
        f"'call mom' -> Calling your mum now. [ACTION:call mom]\n"
        f"'lock it' -> Locking your phone. [ACTION:lock my phone]\n"
        f"'i want music' -> Opening music for you. [ACTION:open spotify]\n"
        f"'take screenshot' -> Done. [ACTION:take screenshot]\n"
        f"'silent mode' -> Phone is now silent. [ACTION:silent mode]\n"
        f"'set alarm 7am' -> Alarm set. [ACTION:set alarm for 7am]\n"
        f"'go home' -> Going to home screen. [ACTION:go home]\n"
        f"ALWAYS include the [ACTION:] tag when the user asks you to DO "
        f"something on the phone. Never just talk about it.\n\n"

        f"PERSONALITY:\n"
        f"Speak naturally and confidently. "
        f"Never claim you cannot perform device actions. "
        f"Remember past conversations. "
        f"Current mood context: {mood}. "
        f"{facts_text}{prefs_text}\n\n"

        f"{mood_instruction}\n\n"

        f"RESPONSE STYLE:\n"
        f"Concise and natural as if speaking aloud. "
        f"No markdown, bullets, asterisks, or formatting. "
        f"Be like a helpful friend. "
        f"Use {name}'s name occasionally but not every message.\n\n"

        f"RULES:\n"
        f"Never say you are just a chatbot. "
        f"Never say you cannot do device actions. "
        f"Always respond as Gideon. Never break character."
    )


# ================= AI CALLS =================
def call_groq_raw(prompt: str):
    for key in GROQ_KEYS:
        if not key:
            continue
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "llama-3.1-8b-instant",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 500
                },
                timeout=8
            )
            data = r.json()
            if "choices" in data:
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"[Groq Raw] Error: {e}")
    return None


def call_provider(msg, provider, model, system_prompt,
                  short_term, device_id):
    if provider == "groq":
        return _call_groq(msg, model, system_prompt, short_term)
    elif provider == "openrouter":
        return _call_openrouter(msg, model, system_prompt)
    elif provider == "gemini":
        return _call_gemini(msg, system_prompt)
    elif provider == "cohere":
        return _call_cohere(msg, system_prompt)
    return None


def _call_groq(msg, model, system_prompt, short_term, retries=2):
    for key in GROQ_KEYS:
        if not key:
            continue
        for attempt in range(retries):
            try:
                messages = list(short_term)
                messages[0] = {
                    "role": "system", "content": system_prompt
                }
                messages.append({"role": "user", "content": msg})

                r = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": model,
                        "messages": messages,
                        "max_tokens": 800
                    },
                    timeout=12
                )
                data = r.json()
                if "choices" in data:
                    return data["choices"][0]["message"]["content"]
                print(f"[Groq {model}] Failed: {data}")
            except Exception as e:
                print(f"[Groq {model}] Error attempt {attempt}: {e}")
                if attempt < retries - 1:
                    import time
                    time.sleep(1)
    return None


def _call_openrouter(msg, model, system_prompt):
    for key in OPENROUTER_KEYS:
        if not key:
            continue
        try:
            r = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://gideon-app.com",
                    "X-Title": "Gideon AI"
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": msg}
                    ],
                    "max_tokens": 800
                },
                timeout=12
            )
            data = r.json()
            if "choices" in data:
                print(f"[OpenRouter] Success: {model}")
                return data["choices"][0]["message"]["content"]
            print(f"[OpenRouter {model}] Failed: {data}")
        except Exception as e:
            print(f"[OpenRouter {model}] Error: {e}")
    return None


def _call_gemini(msg, system_prompt):
    if not GEMINI_KEY:
        return None
    try:
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-1.5-flash:generateContent?key={GEMINI_KEY}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{
                    "role": "user",
                    "parts": [{"text": f"{system_prompt}\n\n{msg}"}]
                }],
                "generationConfig": {"maxOutputTokens": 800}
            },
            timeout=12
        )
        data = r.json()
        candidates = data.get("candidates", [])
        if candidates:
            return candidates[0]["content"]["parts"][0]["text"]
    except Exception as e:
        print(f"[Gemini] Error: {e}")
    return None


def _call_cohere(msg, system_prompt):
    if not COHERE_KEY:
        return None
    try:
        r = requests.post(
            "https://api.cohere.ai/v1/chat",
            headers={
                "Authorization": f"Bearer {COHERE_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "message": msg,
                "preamble": system_prompt,
                "max_tokens": 800
            },
            timeout=12
        )
        data = r.json()
        return data.get("text", None)
    except Exception as e:
        print(f"[Cohere] Error: {e}")
    return None


# ================= WEATHER AND NEWS =================
def get_weather(city: str = "") -> str:
    if not WEATHER_KEY:
        return ""
    try:
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {
            "q": city if city else "Lagos",
            "appid": WEATHER_KEY,
            "units": "metric"
        }
        r = requests.get(url, params=params, timeout=5)
        data = r.json()
        if data.get("cod") == 200:
            temp = data["main"]["temp"]
            feels = data["main"]["feels_like"]
            desc = data["weather"][0]["description"]
            city_name = data["name"]
            humidity = data["main"]["humidity"]
            return (
                f"Weather in {city_name}: {desc}, "
                f"{temp}°C, feels like {feels}°C, "
                f"humidity {humidity}%."
            )
    except Exception as e:
        print(f"[Weather] Error: {e}")
    return ""


def get_news() -> str:
    if not NEWS_KEY:
        return ""
    try:
        url = "https://newsapi.org/v2/top-headlines"
        params = {
            "apiKey": NEWS_KEY,
            "country": "ng",
            "pageSize": 3
        }
        r = requests.get(url, params=params, timeout=5)
        data = r.json()
        articles = data.get("articles", [])
        if articles:
            headlines = [
                a.get("title", "")
                for a in articles[:3]
                if a.get("title")
            ]
            return "Latest news: " + ". ".join(headlines[:3])
    except Exception as e:
        print(f"[News] Error: {e}")
    return ""


# ================= NETWORK CHECK =================
def is_online():
    try:
        requests.get("https://api.groq.com", timeout=3)
        return True
    except Exception:
        return False


# ================= PROCESS =================
def process(msg: str, device_id: str):
    msg = msg.strip()
    if not msg:
        return "No input received.", None

    if not is_online():
        return (
            "I am offline right now. "
            "Please check your internet connection.",
            None
        )

    # ── STEP 1: Check if user is confirming a pending action ───────
    confirmation = check_user_confirmation(msg, device_id)
    if confirmation is not None:
        reply, action = confirmation
        update_short_term(msg, reply, device_id)
        print(f"[Process] Confirmation handled. Action: {action}")
        return reply, action

    # ── STEP 2: Cache check ────────────────────────────────────────
    cache_key = f"{device_id}:{msg.lower()}"
    if cache_key in CACHE:
        cached = CACHE[cache_key]
        update_short_term(msg, cached, device_id)
        return cached, None

    personality = load_personality(device_id)

    # ── STEP 3: Intent understanding (natural language) ────────────
    intent = detect_user_intent(msg)
    if intent:
        print(f"[Process] Intent detected: {intent}")
        reply, action = build_intent_response(
            intent, msg, personality, device_id
        )
        if reply:
            update_short_term(msg, reply, device_id)
            print(f"[Process] Intent reply: '{reply}' action: '{action}'")
            return reply, action

    # ── STEP 4: Exact command detection ───────────────────────────
    offline_type = detect_offline_command(msg)
    if offline_type:
        action_trigger = build_action_trigger(offline_type, msg)
        print(f"[Process] Offline command: {offline_type} -> {action_trigger}")

        # get natural AI reply for the command
        short_term = get_short_term(device_id)
        system_prompt = build_system_prompt(personality, "fast")
        answer = _call_groq(
            msg, "llama-3.1-8b-instant", system_prompt, short_term
        )
        if answer:
            clean_answer, extra_trigger = extract_action_trigger(answer)
            # prefer the explicit action_trigger over AI-generated one
            final_trigger = action_trigger or extra_trigger
            update_short_term(msg, clean_answer, device_id)
            return clean_answer, final_trigger

        return "On it.", action_trigger

    # ── STEP 5: AI routing for everything else ────────────────────
    route = route_model(msg, personality)
    system_prompt = build_system_prompt(personality, route)
    short_term = get_short_term(device_id)

    print(f"[Process] AI route: {route}")

    # weather
    if route == "weather":
        city = ""
        in_idx = msg.lower().find(" in ")
        if in_idx > 0:
            city = msg[in_idx + 4:].strip()
        weather = get_weather(city)
        if weather:
            answer = _call_groq(
                f"User asked: {msg}\nWeather: {weather}\n"
                f"Respond naturally with this data.",
                "llama-3.1-8b-instant", system_prompt, short_term
            )
            if answer:
                clean_answer, action_trigger = extract_action_trigger(answer)
                update_short_term(msg, clean_answer, device_id)
                return clean_answer, action_trigger

    # news
    if route == "news":
        news = get_news()
        if news:
            answer = _call_groq(
                f"User asked: {msg}\nNews: {news}\n"
                f"Summarize naturally.",
                "llama-3.1-8b-instant", system_prompt, short_term
            )
            if answer:
                clean_answer, action_trigger = extract_action_trigger(answer)
                update_short_term(msg, clean_answer, device_id)
                return clean_answer, action_trigger

    model_config = MODELS.get(route, MODELS["fast"])
    primary = model_config["primary"]
    fallback = model_config["fallback"]

    answer = call_provider(
        msg, primary["provider"], primary["model"],
        system_prompt, short_term, device_id
    )

    if not answer:
        print(f"[Process] Primary failed, trying fallback: {fallback['model']}")
        answer = call_provider(
            msg, fallback["provider"], fallback["model"],
            system_prompt, short_term, device_id
        )

    if not answer:
        for model in ["llama-3.1-8b-instant", "llama-3.3-70b-versatile"]:
            answer = _call_groq(msg, model, system_prompt, short_term)
            if answer:
                break

    if not answer:
        answer = "I could not process that right now. Please try again."

    clean_answer, action_trigger = extract_action_trigger(answer)

    CACHE[cache_key] = clean_answer
    update_short_term(msg, clean_answer, device_id)

    threading.Thread(
        target=update_long_term,
        args=(msg, clean_answer, device_id),
        daemon=True
    ).start()

    extract_facts(msg, device_id)

    print(
        f"[Process] Final reply: '{clean_answer[:60]}' "
        f"action: '{action_trigger}'"
    )
    return clean_answer, action_trigger


# ================= ROUTES =================
@app.route("/run", methods=["POST"])
def run():
    data = request.get_json(silent=True) or {}
    action = data.get("action", "process")
    msg = data.get("data", "") or data.get("message", "")
    user_name = data.get("user_name", "User")
    device_id = data.get("device_id", "default")

    try:
        if action == "process":
            reply, action_trigger = process(msg, device_id)
            response = {"reply": reply or "Done"}
            if action_trigger:
                response["action_trigger"] = action_trigger
            print(
                f"[Route] reply='{(reply or '')[:50]}' "
                f"action_trigger='{action_trigger}'"
            )
            return jsonify(response)

        elif action == "update_name":
            personality = load_personality(device_id)
            personality["name"] = msg
            personality["nickname"] = msg
            save_personality(personality, device_id)
            return jsonify({"reply": f"Name updated to {msg}"})

        elif action == "memory":
            personality = load_personality(device_id)
            return jsonify({
                "reply": json.dumps(personality, indent=2)
            })

        elif action == "clear_memory":
            save_history([], device_id)
            save_personality({
                "name": "User",
                "nickname": "User",
                "facts": [],
                "preferences": [],
                "people": [],
                "locations": [],
                "mood": "neutral",
                "mood_history": [],
                "last_seen": ""
            }, device_id)
            if device_id in USER_SHORT_TERM:
                USER_SHORT_TERM[device_id] = [
                    {"role": "system", "content": ""}
                ]
            for k in [k for k in CACHE if k.startswith(device_id)]:
                del CACHE[k]
            return jsonify({"reply": "Memory cleared"})

        else:
            reply, action_trigger = process(msg, device_id)
            response = {"reply": reply or "Done"}
            if action_trigger:
                response["action_trigger"] = action_trigger
            return jsonify(response)

    except Exception as e:
        print(f"[Server] Route error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"reply": f"Server error: {str(e)}"})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "online",
        "bot": BOT_NAME,
        "version": "7.0",
        "groq_keys": sum(1 for k in GROQ_KEYS if k),
        "openrouter_keys": sum(1 for k in OPENROUTER_KEYS if k),
        "gemini": bool(GEMINI_KEY),
        "cohere": bool(COHERE_KEY),
        "weather": bool(WEATHER_KEY),
        "news": bool(NEWS_KEY),
    })


if __name__ == "__main__":
    print(f"{BOT_NAME} online - Version 7.0")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
