# ================= GIDEON BACKEND =================
# Creator: Alexsco (Adegolu Alex)
# Version: 6.0 - Multi-Model Brain

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

# ─── MODEL REGISTRY ───────────────────────────────
# Each task type has a primary and fallback model
MODELS = {
    "fast": {
        "primary": {"provider": "groq", "model": "llama-3.1-8b-instant"},
        "fallback": {"provider": "openrouter", "model": "meta-llama/llama-3.1-8b-instruct:free"}
    },
    "complex": {
        "primary": {"provider": "groq", "model": "llama-3.3-70b-versatile"},
        "fallback": {"provider": "gemini", "model": "gemini-1.5-flash"}
    },
    "creative": {
        "primary": {"provider": "groq", "model": "llama-3.3-70b-versatile"},
        "fallback": {"provider": "openrouter", "model": "mistralai/mistral-7b-instruct:free"}
    },
    "empathetic": {
        "primary": {"provider": "groq", "model": "llama-3.3-70b-versatile"},
        "fallback": {"provider": "cohere", "model": "command-r"}
    },
    "firm": {
        "primary": {"provider": "groq", "model": "llama-3.1-8b-instant"},
        "fallback": {"provider": "openrouter", "model": "mistralai/mistral-7b-instruct:free"}
    },
    "math": {
        "primary": {"provider": "openrouter", "model": "qwen/qwen-2-math-72b-instruct:free"},
        "fallback": {"provider": "groq", "model": "llama-3.3-70b-versatile"}
    },
    "vision": {
        "primary": {"provider": "gemini", "model": "gemini-1.5-flash"},
        "fallback": {"provider": "groq", "model": "llama-3.1-8b-instant"}
    },
    "coding": {
        "primary": {"provider": "openrouter", "model": "deepseek/deepseek-coder:free"},
        "fallback": {"provider": "groq", "model": "llama-3.3-70b-versatile"}
    },
    "weather": {
        "primary": {"provider": "groq", "model": "llama-3.1-8b-instant"},
        "fallback": {"provider": "openrouter", "model": "meta-llama/llama-3.1-8b-instruct:free"}
    },
    "news": {
        "primary": {"provider": "groq", "model": "llama-3.1-8b-instant"},
        "fallback": {"provider": "openrouter", "model": "meta-llama/llama-3.1-8b-instruct:free"}
    }
}

# ================= CACHE =================
CACHE = {}
USER_SHORT_TERM = {}
MEMORY_LIMIT = 20

# ================= SHORT TERM MEMORY =================
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
    except:
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
    except:
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
            f'{{\"facts\": [], \"preferences\": [], \"people\": [], \"locations\": [], \"mood\": \"neutral\"}} '
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
OFFLINE_COMMANDS = {
    "open": ["open", "launch", "start"],
    "call": ["call", "dial"],
    "alarm": ["set alarm", "wake me", "alarm for"],
    "timer": ["set timer", "timer for", "countdown"],
    "reminder": ["remind me", "set reminder"],
    "volume": ["volume up", "volume down", "mute", "unmute",
               "max volume", "min volume", "full volume"],
    "brightness": ["increase brightness", "decrease brightness",
                   "max brightness", "min brightness", "brightest", "dimmest"],
    "flashlight": ["turn on flashlight", "turn off flashlight",
                   "flashlight on", "flashlight off"],
    "lock": ["lock my phone", "lock device", "lock screen", "lock it"],
    "screenshot": ["take screenshot", "screenshot"],
    "battery": ["battery level", "battery percentage", "how much battery"],
    "time": ["what time", "current time", "what is the time"],
    "date": ["what date", "today's date", "what is today"],
    "wifi": ["wifi settings", "turn on wifi", "turn off wifi",
             "wifi on", "wifi off"],
    "bluetooth": ["bluetooth settings", "bluetooth on", "bluetooth off",
                  "turn on bluetooth", "turn off bluetooth"],
    "silent": ["silent mode", "vibrate mode", "ring mode", "mute phone"],
    "dnd": ["do not disturb", "dnd on", "dnd off"],
    "tasks": ["show tasks", "my tasks", "add task",
              "complete task", "show my tasks"],
    "screen": ["read my screen", "what do you see",
               "what's on my screen", "what is on my screen"],
    "back": ["go back"],
    "home": ["go home", "home screen"],
    "recents": ["recent apps", "open recent"],
    "notifications": ["open notifications", "read my notifications"],
    "settings": ["open settings", "open wifi settings",
                 "open bluetooth settings"],
    "search": ["search for", "google", "youtube search", "search on youtube"],
    "calculate": ["calculate", "what is", "plus", "minus",
                  "times", "divided by"],
    "clipboard": ["read clipboard", "what did i copy"],
    "storage": ["how much storage", "storage space"],
    "internet": ["check internet", "am i connected", "internet status"],
    "phone_info": ["what phone", "phone model", "device info"],
    "media_play": ["play music", "play song"],
    "media_pause": ["pause music", "pause that", "stop music"],
    "media_next": ["next song", "skip song", "skip"],
    "strict_mode": ["strict mode", "focus mode", "discipline mode"],
    "study_mode": ["study mode", "start studying"],
    "sleep_mode": ["sleep mode", "good night", "bedtime"],
    "work_mode": ["work mode", "start work"],
    "morning": ["morning routine", "start my day"],
}

def detect_offline_command(msg: str):
    """Detect if message matches an offline command pattern."""
    msg_lower = msg.lower().strip()
    for cmd_type, patterns in OFFLINE_COMMANDS.items():
        for pattern in patterns:
            if pattern in msg_lower:
                return cmd_type
    return None


# ================= ACTION TRIGGER BUILDER =================
def build_action_trigger(offline_type: str, msg: str) -> str:
    """Build a clean action trigger command the Android app can execute."""
    msg_lower = msg.lower().strip()

    if offline_type == "open":
        for word in ["open", "launch", "start"]:
            if word in msg_lower:
                app = msg_lower.replace(word, "").strip()
                app = app.replace("the", "").replace("app", "").strip()
                if app:
                    return f"open {app}"
        return "open"

    if offline_type == "call":
        for word in ["call", "dial"]:
            if word in msg_lower:
                contact = msg_lower.replace(word, "").strip()
                if contact:
                    return f"call {contact}"
        return "call"

    if offline_type == "search":
        for word in ["search for", "google", "search"]:
            if word in msg_lower:
                query = msg_lower.replace(word, "").strip()
                if query:
                    return f"search for {query}"
        return msg_lower

    if offline_type == "alarm":
        return msg_lower

    if offline_type == "timer":
        return msg_lower

    if offline_type == "tasks":
        return msg_lower

    action_map = {
        "lock": "lock my phone",
        "screenshot": "take screenshot",
        "flashlight": "flashlight on",
        "battery": "battery level",
        "screen": "read my screen",
        "back": "go back",
        "home": "go home",
        "recents": "recent apps",
        "media_play": "play music",
        "media_pause": "pause music",
        "media_next": "next song",
        "silent": "silent mode",
        "wifi": "wifi settings",
        "bluetooth": "bluetooth settings",
        "dnd": "do not disturb on",
        "notifications": "open notifications",
        "storage": "how much storage",
        "internet": "check internet",
        "phone_info": "what phone do i have",
        "time": "what time is it",
        "date": "what date is it",
        "clipboard": "read clipboard",
        "strict_mode": msg_lower,
        "study_mode": "study mode",
        "sleep_mode": "sleep mode",
        "work_mode": "work mode",
        "morning": "morning routine",
        "volume": msg_lower,
        "brightness": msg_lower,
        "settings": msg_lower,
        "calculate": msg_lower,
    }

    return action_map.get(offline_type, msg_lower)



# ================= INTENT UNDERSTANDING =================

INTENT_PATTERNS = {
    # MESSAGING INTENTS
    "intent_whatsapp": [
        "send a message", "send a text", "text someone", "message someone",
        "whatsapp someone", "chat with", "send on whatsapp",
        "i need to text", "i want to message", "reach out to someone"
    ],
    "intent_call": [
        "i need to call", "i want to call", "can you call", "make a call",
        "ring someone", "phone someone", "give someone a call",
        "i need to speak to", "i want to talk to", "call someone for me"
    ],
    "intent_alarm": [
        "i need to wake up", "wake me up", "don't let me sleep past",
        "i have to be up by", "set something for", "i need a reminder to wake",
        "remind me to wake", "i need to get up at"
    ],
    "intent_music": [
        "i want to listen", "i feel like listening", "play something",
        "put on some music", "i want some music", "music please",
        "something to listen to", "i want to hear"
    ],
    "intent_open_app": [
        "i want to use", "i need to use", "open something for",
        "can you open", "launch something", "i need to go to",
        "take me to", "bring up", "i want to go to"
    ],
    "intent_navigate": [
        "go back", "take me back", "previous screen",
        "i want to go back", "return to", "back to"
    ],
    "intent_search": [
        "look something up", "find information", "i want to know about",
        "search something", "look up", "find out about", "get information on",
        "i need information about", "tell me about", "i want to learn about"
    ],
    "intent_screenshot": [
        "capture this", "save this screen", "take a picture of the screen",
        "save what i'm seeing", "capture the screen", "snap this"
    ],
    "intent_battery": [
        "how much battery", "is my battery okay", "battery dying",
        "check my battery", "how long will my battery last",
        "is my phone charged", "phone battery"
    ],
    "intent_brightness": [
        "too bright", "screen too bright", "hurting my eyes",
        "too dim", "can't see the screen", "make it brighter",
        "make it darker", "lower the light", "increase the light"
    ],
    "intent_volume": [
        "too loud", "turn it down", "can't hear", "increase the sound",
        "lower the sound", "make it louder", "make it quieter",
        "sound is low", "sound is high"
    ],
    "intent_focus": [
        "i need to focus", "help me focus", "i keep getting distracted",
        "stop me from using my phone", "i need to study",
        "i need to be productive", "help me stop procrastinating",
        "i'm wasting time", "put me in focus mode"
    ],
    "intent_task": [
        "i need to remember to", "don't let me forget to",
        "remind me about", "i have to", "i should", "i must",
        "add this to my list", "put this on my list",
        "note this down", "i need to do"
    ],
    "intent_lock": [
        "lock up", "secure the phone", "put it to sleep",
        "i'm done with my phone", "lock it up", "secure it"
    ],
    "intent_sleep": [
        "i'm going to sleep", "i'm tired", "time for bed",
        "good night", "about to sleep", "heading to bed",
        "i'm sleepy", "turning in for the night"
    ],
    "intent_weather": [
        "is it going to rain", "should i carry an umbrella",
        "what's the weather like", "how's the weather",
        "is it hot outside", "is it cold outside",
        "weather today", "weather outside"
    ],
    "intent_news": [
        "what's happening", "what's going on in the world",
        "any news", "latest news", "current events",
        "what happened today", "news today"
    ]
}

def detect_user_intent(msg: str) -> str | None:
    """Detect high-level user intent from natural language."""
    msg_lower = msg.lower().strip()
    for intent, patterns in INTENT_PATTERNS.items():
        for pattern in patterns:
            if pattern in msg_lower:
                return intent
    return None


INTENT_CONFIRMATIONS = {
    "intent_whatsapp": {
        "question": "Should I open WhatsApp for you?",
        "action": "open whatsapp",
        "follow_up": "Go ahead and send your message."
    },
    "intent_call": {
        "question": "Should I help you make a call?",
        "action": "call",
        "follow_up": "Who would you like to call?"
    },
    "intent_alarm": {
        "question": "Should I set an alarm for you?",
        "action": "set alarm",
        "follow_up": "What time should I set it for?"
    },
    "intent_music": {
        "question": "Should I open your music app?",
        "action": "open spotify",
        "follow_up": "Music is ready for you."
    },
    "intent_open_app": {
        "question": "Which app would you like me to open?",
        "action": None,
        "follow_up": "Opening it now."
    },
    "intent_navigate": {
        "question": None,
        "action": "go back",
        "follow_up": None
    },
    "intent_search": {
        "question": "Should I search that for you?",
        "action": "search for",
        "follow_up": "Searching now."
    },
    "intent_screenshot": {
        "question": "Should I take a screenshot?",
        "action": "take screenshot",
        "follow_up": "Screenshot saved."
    },
    "intent_battery": {
        "question": None,
        "action": "battery level",
        "follow_up": None
    },
    "intent_brightness": {
        "question": None,
        "action": "adjust brightness",
        "follow_up": None
    },
    "intent_volume": {
        "question": None,
        "action": "adjust volume",
        "follow_up": None
    },
    "intent_focus": {
        "question": "Should I activate focus mode to help you?",
        "action": "strict mode focus",
        "follow_up": "Focus mode is on. Distractions will be limited."
    },
    "intent_task": {
        "question": "Should I add that as a task?",
        "action": "add task",
        "follow_up": "Task added."
    },
    "intent_lock": {
        "question": "Should I lock your phone?",
        "action": "lock my phone",
        "follow_up": "Locking now."
    },
    "intent_sleep": {
        "question": None,
        "action": "sleep mode",
        "follow_up": None
    },
    "intent_weather": {
        "question": None,
        "action": "weather",
        "follow_up": None
    },
    "intent_news": {
        "question": None,
        "action": "latest news",
        "follow_up": None
    }
}

# stores pending confirmations per device
PENDING_CONFIRMATIONS = {}

def check_user_confirmation(msg: str, device_id: str) -> tuple | None:
    """Check if user is confirming or denying a pending action."""
    if device_id not in PENDING_CONFIRMATIONS:
        return None

    pending = PENDING_CONFIRMATIONS[device_id]
    msg_lower = msg.lower().strip()

    positive = [
        "yes", "yeah", "yep", "sure", "ok", "okay", "go ahead",
        "please do", "do it", "proceed", "definitely", "of course",
        "yes please", "yh", "aye", "right", "correct"
    ]
    negative = [
        "no", "nope", "don't", "cancel", "stop", "never mind",
        "nah", "not now", "skip it", "forget it", "no thanks"
    ]

    if any(word == msg_lower or msg_lower.startswith(word) for word in positive):
        action = pending.get("action")
        follow_up = pending.get("follow_up", "Done.")
        del PENDING_CONFIRMATIONS[device_id]
        return follow_up, action

    if any(word == msg_lower or msg_lower.startswith(word) for word in negative):
        del PENDING_CONFIRMATIONS[device_id]
        return "No problem. Let me know if you need anything else.", None

    return None


def build_smart_action(intent: str, msg: str, personality: dict) -> tuple:
    """Build a response and action trigger based on detected intent."""
    name = personality.get("nickname") or personality.get("name", "")
    greeting = f"{name}, " if name else ""
    msg_lower = msg.lower()

    config = INTENT_CONFIRMATIONS.get(intent, {})
    question = config.get("question")
    action = config.get("action")

    # intents that need no confirmation - just do it
    no_confirm_intents = {
        "intent_navigate", "intent_battery", "intent_sleep",
        "intent_weather", "intent_news"
    }

    if intent in no_confirm_intents or question is None:
        # handle brightness direction
        if intent == "intent_brightness":
            if any(w in msg_lower for w in
                   ["bright", "light", "see", "low", "dim"]):
                action = "decrease brightness"
            else:
                action = "increase brightness"
        # handle volume direction
        elif intent == "intent_volume":
            if any(w in msg_lower for w in ["loud", "high", "up", "louder"]):
                action = "volume up"
            else:
                action = "volume down"

        follow_up = config.get("follow_up")
        reply = follow_up if follow_up else "On it."
        return reply, action

    # for call intent, extract the name if given
    if intent == "intent_call":
        for skip in ["i need to call", "i want to call", "call",
                     "can you call", "please call", "make a call to"]:
            if skip in msg_lower:
                contact = msg_lower.replace(skip, "").strip()
                if contact and len(contact) > 1:
                    return (
                        f"{greeting}Should I call {contact} for you?",
                        f"call {contact}"
                    )

    # for open app intent, extract the app name
    if intent == "intent_open_app":
        for skip in ["i want to use", "i need to use", "can you open",
                     "open", "take me to", "bring up", "launch",
                     "i need to go to", "i want to go to"]:
            if skip in msg_lower:
                app = msg_lower.replace(skip, "").strip()
                app = app.replace("the", "").replace("app", "").strip()
                if app and len(app) > 1:
                    return (
                        f"{greeting}Should I open {app} for you?",
                        f"open {app}"
                    )

    # for task intent, extract the task content
    if intent == "intent_task":
        for skip in ["i need to remember to", "don't let me forget to",
                     "remind me about", "i have to", "i should",
                     "i must", "i need to do", "remind me to"]:
            if skip in msg_lower:
                task = msg_lower.replace(skip, "").strip()
                if task and len(task) > 2:
                    return (
                        f"{greeting}Should I add '{task}' to your tasks?",
                        f"add task {task}"
                    )

    # default confirmation question
    return f"{greeting}{question}", None

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
    "calculate", "solve", "equation", "integral", "derivative",
    "algebra", "geometry", "trigonometry", "statistics",
    "probability", "matrix", "calculus", "formula"
    ]
    if any(k in msg_lower for k in math_keywords):
        return "math"
    emotional_keywords = [
        "sad", "depressed", "anxious", "lonely", "stressed",
        "worried", "scared", "angry", "upset", "hurt",
        "heartbreak", "crying", "feel like", "i feel", "i am tired",
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

    if len(msg.split()) < 8:
        return "fast"

    return "fast"

# ================= MOOD INSTRUCTION =================
def get_mood_instruction(route: str) -> str:
    if route == "empathetic":
        return (
            "CURRENT MODE: Empathetic support. "
            "The user may be feeling emotional or vulnerable. "
            "Respond with warmth, genuine care, and patience. "
            "Validate their feelings before offering solutions. "
            "Do not rush. Be human and kind."
        )
    elif route == "creative":
        return (
            "CURRENT MODE: Creative and playful. "
            "The user is in a light mood. Be witty, fun, and engaging. "
            "Use light humor where it fits naturally. "
            "Keep energy warm and responses lively."
        )
    elif route == "complex":
        return (
            "CURRENT MODE: Deep thinking required. "
            "Give a thorough, well-reasoned response. "
            "Be clear and structured but still conversational. "
            "Avoid unnecessary jargon."
        )
    elif route == "coding":
        return (
            "CURRENT MODE: Developer assistance. "
            "The user needs coding help. "
            "Be precise, technical, and practical. "
            "Provide working code examples where helpful. "
            "Explain errors clearly and suggest fixes."
        )
    elif route == "firm":
        return (
            "CURRENT MODE: Firm and dignified. "
            "The user is being rude or disrespectful. "
            "Respond calmly but with confidence and self-respect. "
            "Do not apologize for existing. "
            "Set a polite boundary, redirect to being helpful, "
            "and do not match their negative energy."
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
        facts_text = f"What you know about {name}: {', '.join(facts[:10])}. "

    prefs_text = ""
    if prefs:
        prefs_text = f"Their preferences: {', '.join(prefs[:5])}. "

    mood_instruction = get_mood_instruction(route)

    return (
        f"You are Gideon, an advanced AI assistant running on {name}'s Android phone. "
        f"You are not just a chatbot. You are a fully capable AI assistant with direct control over the phone.\n\n"

        f"YOUR IDENTITY:\n"
        f"Your name is Gideon. "
        f"You were created and built by Alexsco (Adegolu Alex), an independent Android developer. "
        f"You run directly on the user's Android device. "
        f"You are intelligent, natural, helpful, and concise.\n\n"

        f"YOUR ACTUAL CAPABILITIES ON THIS PHONE:\n"
        f"You can open any installed app by name, make phone calls to contacts, "
        f"lock the device immediately, control volume and mute, "
        f"turn flashlight on and off, take screenshots, control media playback, "
        f"set alarms reminders and timers, read what is on the screen, "
        f"read clipboard contents, read notifications aloud, check wifi network name, "
        f"check battery level, control screen brightness, "
        f"toggle silent vibrate and ring modes, toggle do not disturb, "
        f"perform navigation actions like back home and recents, "
        f"search the web and YouTube, perform calculations, "
        f"check storage internet and device info, access all phone settings, "
        f"monitor app usage and help user stay focused.\n\n"

        f"SMART ACTION SYSTEM:\n"
        f"When the user asks you to do a device action, include [ACTION:command] in your response.\n"
        f"Examples:\n"
        f"'I want music' -> natural reply + [ACTION:open spotify]\n"
        f"'too bright' -> natural reply + [ACTION:decrease brightness]\n"
        f"'call my mum' -> natural reply + [ACTION:call mom]\n"
        f"'lock it' -> natural reply + [ACTION:lock my phone]\n"
        f"'take photo' -> natural reply + [ACTION:open camera]\n"
        f"Only use action triggers when confident. Ask if unsure.\n\n"

        f"PERSONALITY:\n"
        f"You speak in a natural, friendly, confident tone. "
        f"You never claim to lack phone access or device control. "
        f"You remember past conversations and learn about {name} over time. "
        f"Current mood context: {mood}. "
        f"{facts_text}{prefs_text}\n\n"

        f"{mood_instruction}\n\n"

        f"RESPONSE STYLE:\n"
        f"Keep responses concise and natural as if speaking aloud. "
        f"Never use markdown, bullet points, asterisks, or special formatting. "
        f"Be like a helpful friend, not a search engine. "
        f"Use {name}'s name occasionally but not excessively.\n\n"

        f"RULES:\n"
        f"Never claim you are just a chatbot. "
        f"Never say you cannot perform device actions. "
        f"If a permission is needed explain how to grant it. "
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

def call_provider(
    msg: str,
    provider: str,
    model: str,
    system_prompt: str,
    short_term: list,
    device_id: str
) -> str | None:
    if provider == "groq":
        return _call_groq(msg, model, system_prompt, short_term)
    elif provider == "openrouter":
        return _call_openrouter(msg, model, system_prompt)
    elif provider == "gemini":
        return _call_gemini(msg, system_prompt)
    elif provider == "cohere":
        return _call_cohere(msg, system_prompt)
    return None

def _call_groq(
    msg: str,
    model: str,
    system_prompt: str,
    short_term: list,
    retries: int = 2
) -> str | None:
    for key in GROQ_KEYS:
        if not key:
            continue
        for attempt in range(retries):
            try:
                messages = list(short_term)
                messages[0] = {"role": "system", "content": system_prompt}
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

def _call_openrouter(
    msg: str,
    model: str,
    system_prompt: str
) -> str | None:
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

def _call_gemini(msg: str, system_prompt: str) -> str | None:
    if not GEMINI_KEY:
        return None
    try:
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-1.5-flash:generateContent?key={GEMINI_KEY}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [
                    {"role": "user", "parts": [{"text": f"{system_prompt}\n\n{msg}"}]}
                ],
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

def _call_cohere(msg: str, system_prompt: str) -> str | None:
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

# ================= NETWORK CHECK =================
def is_online():
    try:
        requests.get("https://api.groq.com", timeout=3)
        return True
    except:
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

    # ─── CHECK PENDING CONFIRMATIONS FIRST ────────────────────────
    # if user is responding yes/no to a previous question
    confirmation = check_user_confirmation(msg, device_id)
    if confirmation is not None:
        reply, action = confirmation
        update_short_term(msg, reply, device_id)
        return reply, action

    cache_key = f"{device_id}:{msg.lower()}"
    if cache_key in CACHE:
        cached = CACHE[cache_key]
        update_short_term(msg, cached, device_id)
        return cached, None

    personality = load_personality(device_id)

    # ─── DETECT INTENT (natural language understanding) ───────────
    intent = detect_user_intent(msg)
    if intent:
        reply, action = build_smart_action(intent, msg, personality)

        # if action is None, this needs confirmation
        # store pending confirmation so next message
        # can be yes/no
        if action is None:
            config = INTENT_CONFIRMATIONS.get(intent, {})
            PENDING_CONFIRMATIONS[device_id] = {
                "intent": intent,
                "action": config.get("action"),
                "follow_up": config.get("follow_up", "Done."),
                "original_msg": msg
            }
        else:
            # direct action - no confirmation needed
            update_short_term(msg, reply, device_id)
            return reply, action

        # reply contains the confirmation question
        update_short_term(msg, reply, device_id)
        return reply, None

    # ─── DETECT OFFLINE COMMAND (exact keyword matching) ──────────
    offline_type = detect_offline_command(msg)
    if offline_type:
        action_trigger = build_action_trigger(offline_type, msg)
        answer = _call_groq(
            msg, "llama-3.1-8b-instant",
            build_system_prompt(personality, "fast"),
            get_short_term(device_id)
        )
        if answer:
            clean_answer, _ = extract_action_trigger(answer)
            update_short_term(msg, clean_answer, device_id)
            return clean_answer, action_trigger
        return "On it.", action_trigger

    # ─── AI ROUTING ───────────────────────────────────────────────
    route = route_model(msg, personality)
    system_prompt = build_system_prompt(personality, route)
    short_term = get_short_term(device_id)

    # handle weather route
    if route == "weather":
        city = ""
        in_idx = msg.lower().find(" in ")
        if in_idx > 0:
            city = msg[in_idx + 4:].strip()
        weather = get_weather(city)
        if weather:
            answer = _call_groq(
                f"User asked: {msg}\nWeather data: {weather}\n"
                f"Respond naturally using this data.",
                "llama-3.1-8b-instant",
                system_prompt,
                short_term
            )
            if answer:
                clean_answer, action_trigger = extract_action_trigger(answer)
                update_short_term(msg, clean_answer, device_id)
                return clean_answer, action_trigger

    # handle news route
    if route == "news":
        news = get_news()
        if news:
            answer = _call_groq(
                f"User asked: {msg}\nNews data: {news}\n"
                f"Respond naturally summarizing these headlines.",
                "llama-3.1-8b-instant",
                system_prompt,
                short_term
            )
            if answer:
                clean_answer, action_trigger = extract_action_trigger(answer)
                update_short_term(msg, clean_answer, device_id)
                return clean_answer, action_trigger

    model_config = MODELS.get(route, MODELS["fast"])
    primary = model_config["primary"]
    fallback = model_config["fallback"]

    print(f"[Router] Route: {route}, Model: {primary['model']}")

    answer = call_provider(
        msg, primary["provider"], primary["model"],
        system_prompt, short_term, device_id
    )

    if not answer:
        print(f"[Router] Primary failed, trying: {fallback['model']}")
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
            return jsonify(response)

        elif action == "update_name":
            personality = load_personality(device_id)
            personality["name"] = msg
            personality["nickname"] = msg
            save_personality(personality, device_id)
            return jsonify({"reply": f"Name updated to {msg}"})

        elif action == "memory":
            personality = load_personality(device_id)
            return jsonify({"reply": json.dumps(personality, indent=2)})

        elif action == "clear_memory":
            save_history([], device_id)
            save_personality({
                "name": user_name,
                "nickname": user_name,
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
            cache_keys = [k for k in CACHE if k.startswith(device_id)]
            for k in cache_keys:
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
        return jsonify({"reply": f"Server error: {str(e)}"})

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "online",
        "bot": BOT_NAME,
        "version": "6.0",
        "groq_key_set": bool(GROQ_KEYS[0]),
        "openrouter_key_set": bool(OPENROUTER_KEYS[0]),
        "gemini_key_set": bool(GEMINI_KEY),
        "cohere_key_set": bool(COHERE_KEY)
    })

if __name__ == "__main__":
    print(f"{BOT_NAME} online - Version 6.0")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
