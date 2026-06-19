# ================================================================
# GIDEON BACKEND - Version 9.0
# Creator: Alexsco (Adegolu Alex) @alexsco_official
# Full stack: Groq x4, OpenRouter x2, Gemini, Cohere, Mistral x2
# Features: Intent system, confirmation, memory, TTS, LaTeX
# ================================================================

from flask import Flask, request, jsonify
import os, requests, json, threading, datetime, re, time, base64
from collections import defaultdict

app = Flask(__name__)

# ================================================================
# CONFIG & API KEYS
# ================================================================
BOT_NAME = "Gideon"

GROQ_KEYS = [
    os.getenv("GROQ_KEY_1", ""),
    os.getenv("GROQ_KEY_2", ""),
    os.getenv("GROQ_KEY_3", ""),
    os.getenv("GROQ_KEY_4", ""),
]
OPENROUTER_KEYS = [
    os.getenv("OPENROUTER_KEY_1", ""),
    os.getenv("OPENROUTER_KEY_2", ""),
]
MISTRAL_KEYS = [
    os.getenv("MISTRAL_KEY_1", ""),
    os.getenv("MISTRAL_KEY_2", ""),
]
GEMINI_KEY    = os.getenv("GEMINI_KEY", "")
COHERE_KEY    = os.getenv("COHERE_KEY", "")
WEATHER_KEY   = os.getenv("WEATHER_KEY", "")
NEWS_KEY      = os.getenv("NEWS_KEY", "")
OPENAI_KEY    = os.getenv("OPENAI_KEY", "")

# ================================================================
# RATE LIMITING
# ================================================================
REQUEST_COUNTS = defaultdict(list)
RATE_LIMIT_PER_MINUTE = 20
RATE_LIMIT_PER_HOUR   = 200

def is_rate_limited(device_id: str) -> bool:
    now        = time.time()
    minute_ago = now - 60
    hour_ago   = now - 3600
    counts     = [t for t in REQUEST_COUNTS[device_id] if t > hour_ago]
    REQUEST_COUNTS[device_id] = counts
    if sum(1 for t in counts if t > minute_ago) >= RATE_LIMIT_PER_MINUTE:
        return True
    if len(counts) >= RATE_LIMIT_PER_HOUR:
        return True
    REQUEST_COUNTS[device_id].append(now)
    return False

# ================================================================
# MODEL REGISTRY
# ================================================================
MODELS = {
    "fast": {
        "primary":  {"provider": "groq",        "model": "llama-3.1-8b-instant"},
        "fallback": {"provider": "openrouter",   "model": "meta-llama/llama-3.1-8b-instruct:free"},
    },
    "complex": {
        "primary":  {"provider": "groq",         "model": "llama-3.3-70b-versatile"},
        "fallback": {"provider": "gemini",        "model": "gemini-1.5-flash"},
    },
    "creative": {
        "primary":  {"provider": "groq",         "model": "llama-3.3-70b-versatile"},
        "fallback": {"provider": "mistral",       "model": "mistral-small-latest"},
    },
    "empathetic": {
        "primary":  {"provider": "groq",         "model": "llama-3.3-70b-versatile"},
        "fallback": {"provider": "cohere",        "model": "command-r"},
    },
    "firm": {
        "primary":  {"provider": "groq",         "model": "llama-3.1-8b-instant"},
        "fallback": {"provider": "openrouter",    "model": "mistralai/mistral-7b-instruct:free"},
    },
    "math": {
        "primary":  {"provider": "openrouter",   "model": "qwen/qwen-2-math-72b-instruct:free"},
        "fallback": {"provider": "groq",          "model": "llama-3.3-70b-versatile"},
    },
    "coding": {
        "primary":  {"provider": "openrouter",   "model": "deepseek/deepseek-coder:free"},
        "fallback": {"provider": "groq",          "model": "llama-3.3-70b-versatile"},
    },
    "weather": {
        "primary":  {"provider": "groq",         "model": "llama-3.1-8b-instant"},
        "fallback": {"provider": "openrouter",    "model": "meta-llama/llama-3.1-8b-instruct:free"},
    },
    "news": {
        "primary":  {"provider": "groq",         "model": "llama-3.1-8b-instant"},
        "fallback": {"provider": "openrouter",    "model": "meta-llama/llama-3.1-8b-instruct:free"},
    },
}

# ================================================================
# IN-MEMORY STORES
# ================================================================
CACHE                 = {}
USER_SHORT_TERM       = {}
PENDING_CONFIRMATIONS = {}
MEMORY_LIMIT          = 20

def get_short_term(device_id: str):
    if device_id not in USER_SHORT_TERM:
        USER_SHORT_TERM[device_id] = [{"role": "system", "content": ""}]
    return USER_SHORT_TERM[device_id]

# ================================================================
# FILE HELPERS
# ================================================================
def get_user_files(device_id: str):
    safe = "".join(c for c in device_id if c.isalnum() or c == "-")[:36]
    return {
        "personality": f"personality_{safe}.json",
        "history":     f"history_{safe}.json",
    }

# ================================================================
# NAME SANITIZER
# ================================================================
def clean_name(raw: str) -> str:
    if not raw:
        return ""
    cleaned = raw.split("[")[0].split("]")[0].strip()
    cleaned = re.sub(r"[^a-zA-Z0-9\s\-']", "", cleaned).strip()
    return cleaned[:50]

# ================================================================
# LATEX → UNICODE  (skipped for math route)
# ================================================================
LATEX_MAP = [
    (r'\frac{d}{dx}', 'd/dx'), (r'\frac{1}{2}', '½'),
    (r'\frac{1}{x}', '1/x'),   (r'\int', '∫'),
    (r'\sum', '∑'),             (r'\lim_{', 'lim('),
    (r'\lim', 'lim'),           (r'\sqrt', '√'),
    (r'\infty', '∞'),           (r'\theta', 'θ'),
    (r'\alpha', 'α'),           (r'\beta', 'β'),
    (r'\gamma', 'γ'),           (r'\pi', 'π'),
    (r'\Delta', 'Δ'),           (r'\delta', 'δ'),
    (r'\epsilon', 'ε'),         (r'\lambda', 'λ'),
    (r'\mu', 'μ'),              (r'\sigma', 'σ'),
    (r'\omega', 'ω'),           (r'\times', '×'),
    (r'\div', '÷'),             (r'\neq', '≠'),
    (r'\leq', '≤'),             (r'\geq', '≥'),
    (r'\approx', '≈'),          (r'\rightarrow', '→'),
    (r'\leftarrow', '←'),       (r'\Rightarrow', '⇒'),
    (r'\pm', '±'),              (r'^{2}', '²'),
    (r'^{3}', '³'),             (r'^{n}', 'ⁿ'),
    (r'^2', '²'),               (r'^3', '³'),
    (r'_{0}', '₀'),             (r'_{1}', '₁'),
    (r'_{2}', '₂'),             (r'_{n}', 'ₙ'),
    (r'\left(', '('),           (r'\right)', ')'),
    (r'\cdot', '·'),            (r'\ldots', '...'),
    (r'\to', '→'),              (r'\nabla', '∇'),
    (r'\partial', '∂'),
]

def latex_to_unicode(text: str) -> str:
    for latex, uni in LATEX_MAP:
        text = text.replace(latex, uni)
    text = re.sub(r'\\[a-zA-Z]+\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\[a-zA-Z]+', '', text)
    return text

# ================================================================
# HISTORY
# ================================================================
def load_history(device_id: str):
    try:
        with open(get_user_files(device_id)["history"]) as f:
            return json.load(f)
    except Exception:
        return []

def save_history(history: list, device_id: str):
    try:
        with open(get_user_files(device_id)["history"], "w") as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        print(f"[Memory] save_history error: {e}")

# ================================================================
# PERSONALITY
# ================================================================
def load_personality(device_id: str):
    try:
        with open(get_user_files(device_id)["personality"]) as f:
            data = json.load(f)
        data["name"]     = clean_name(data.get("name", "User")) or "User"
        data["nickname"] = clean_name(data.get("nickname", "")) or data["name"]
        return data
    except Exception:
        return {
            "name": "User", "nickname": "User",
            "facts": [], "preferences": [], "people": [],
            "locations": [], "mood": "neutral",
            "mood_history": [], "last_seen": "",
        }

def save_personality(data: dict, device_id: str):
    try:
        data["name"]     = clean_name(data.get("name", "User")) or "User"
        data["nickname"] = clean_name(data.get("nickname", "")) or data["name"]
        with open(get_user_files(device_id)["personality"], "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[Memory] save_personality error: {e}")

# ================================================================
# MEMORY UPDATE
# ================================================================
def update_short_term(user_msg: str, bot_reply: str, device_id: str):
    st = get_short_term(device_id)
    st.append({"role": "user",      "content": user_msg})
    st.append({"role": "assistant", "content": bot_reply})
    while len(st) > MEMORY_LIMIT:
        del st[1]

def update_long_term(user_msg: str, bot_reply: str, device_id: str):
    history = load_history(device_id)
    history.append({
        "timestamp": datetime.datetime.now().isoformat(),
        "user": user_msg, "gideon": bot_reply,
    })
    if len(history) > 100:
        history = _summarise_history(history, device_id)
    save_history(history, device_id)

def _summarise_history(history: list, device_id: str):
    try:
        recent  = history[-40:]
        older   = history[:-40]
        text    = "\n".join(f"User:{h['user']}\nGideon:{h['gideon']}" for h in older)
        summary = _call_groq_raw(f"Summarise this conversation briefly:\n{text}")
        if summary:
            return [{"timestamp": datetime.datetime.now().isoformat(),
                     "user": "[Summary]", "gideon": summary}] + recent
    except Exception as e:
        print(f"[Memory] summarise error: {e}")
    return history[-40:]

# ================================================================
# FACT EXTRACTION (background thread)
# ================================================================
def extract_facts(user_msg: str, device_id: str):
    threading.Thread(target=_extract_facts_thread,
                     args=(user_msg, device_id), daemon=True).start()

def _extract_facts_thread(user_msg: str, device_id: str):
    try:
        personality = load_personality(device_id)
        name        = personality.get("nickname") or personality.get("name", "User")
        result      = _call_groq_raw(
            f"Extract personal facts about {name} from this message. "
            f"Return ONLY valid JSON: facts, preferences, people, locations, mood. "
            f"Each key except mood is a list of short strings. mood is one word. "
            f"If nothing return: "
            f'{{"facts":[],"preferences":[],"people":[],"locations":[],"mood":"neutral"}} '
            f"Message: {user_msg}"
        )
        if not result:
            return
        clean = result.strip().replace("```json", "").replace("```", "").strip()
        s = clean.find("{"); e = clean.rfind("}") + 1
        if s == -1 or e == 0:
            return
        extracted = json.loads(clean[s:e])
        for key in ["facts", "preferences", "people", "locations"]:
            for item in extracted.get(key, []):
                if item and item not in personality.get(key, []):
                    personality.setdefault(key, []).append(item)
        mood = extracted.get("mood", "")
        if mood and mood != "neutral":
            personality["mood"] = mood
            personality.setdefault("mood_history", []).append({
                "timestamp": datetime.datetime.now().isoformat(), "mood": mood
            })
            personality["mood_history"] = personality["mood_history"][-20:]
        personality["last_seen"] = datetime.datetime.now().isoformat()
        save_personality(personality, device_id)
    except Exception as e:
        print(f"[Facts] error: {e}")

# ================================================================
# ACTION TRIGGER PARSER
# ================================================================
def extract_action_trigger(reply: str):
    match = re.search(r'\[ACTION:([^\]]+)\]', reply)
    if match:
        action = match.group(1).strip()
        clean  = re.sub(r'\[ACTION:[^\]]+\]', '', reply).strip()
        return clean, action
    return reply, None

# ================================================================
# OFFLINE COMMAND DETECTION
# ================================================================
OFFLINE_COMMANDS = {
    "open":         ["open ", "launch ", "start "],
    "call":         ["call ", "dial "],
    "alarm":        ["set alarm", "wake me up", "alarm for"],
    "timer":        ["set timer", "timer for", "countdown for"],
    "reminder":     ["remind me to ", "set reminder"],
    "volume":       ["volume up", "volume down", "max volume", "min volume",
                     "full volume", "mute phone", "unmute phone",
                     "lower volume", "raise volume"],
    "brightness":   ["increase brightness", "decrease brightness",
                     "max brightness", "min brightness", "full brightness",
                     "lowest brightness", "brighten screen", "dim screen"],
    "flashlight":   ["flashlight on", "flashlight off", "turn on flashlight",
                     "turn off flashlight", "torch on", "torch off"],
    "lock":         ["lock my phone", "lock device", "lock screen", "lock it"],
    "screenshot":   ["take screenshot", "take a screenshot"],
    "battery":      ["battery level", "battery percentage",
                     "how much battery", "check battery"],
    "time":         ["what time is it", "current time", "tell me the time"],
    "date":         ["what date is it", "today's date", "what day is it"],
    "wifi":         ["wifi settings", "turn on wifi", "turn off wifi",
                     "wifi on", "wifi off", "open wifi"],
    "bluetooth":    ["bluetooth settings", "bluetooth on", "bluetooth off",
                     "turn on bluetooth", "turn off bluetooth"],
    "silent":       ["silent mode", "vibrate mode", "ring mode"],
    "dnd":          ["do not disturb on", "do not disturb off", "dnd on", "dnd off"],
    "tasks":        ["show my tasks", "my tasks", "add task ",
                     "complete task", "show tasks"],
    "screen":       ["read my screen", "what do you see",
                     "what's on my screen", "what is on my screen",
                     "read the screen"],
    "back":         ["go back"],
    "home":         ["go home", "home screen"],
    "recents":      ["recent apps", "open recent apps"],
    "notifications":["open notifications", "read my notifications",
                     "read notifications"],
    "settings":     ["open settings", "open phone settings"],
    "search":       ["search for ", "search on google", "youtube search "],
    "calculate":    ["calculate ", " plus ", " minus ", " times ",
                     " divided by ", "percent of", "square root"],
    "clipboard":    ["read clipboard", "what did i copy"],
    "storage":      ["how much storage", "storage space", "check storage"],
    "internet":     ["check internet", "am i connected", "internet status"],
    "phone_info":   ["what phone do i have", "phone model", "device info"],
    "media_play":   ["play music", "play a song"],
    "media_pause":  ["pause music", "pause that", "stop the music"],
    "media_next":   ["next song", "skip song", "skip this"],
    "strict_mode":  ["strict mode on", "strict mode off", "focus mode on",
                     "focus mode off", "discipline mode"],
    "study_mode":   ["study mode", "start studying"],
    "sleep_mode":   ["sleep mode", "bedtime mode"],
    "work_mode":    ["work mode", "start work mode"],
    "morning":      ["morning routine", "start my day routine"],
}

def detect_offline_command(msg: str):
    msg_lower = msg.lower().strip()
    for cmd_type, patterns in OFFLINE_COMMANDS.items():
        for pattern in patterns:
            if pattern in msg_lower:
                return cmd_type
    return None

def build_action_trigger(offline_type: str, msg: str) -> str:
    msg_lower = msg.lower().strip()
    if offline_type == "open":
        for w in ["open ", "launch ", "start "]:
            if w in msg_lower:
                app = msg_lower.replace(w.strip(), "").strip()
                app = app.replace(" the ", " ").replace(" app", "").strip()
                return f"open {app}" if app else "open"
        return "open"
    if offline_type == "call":
        for w in ["call ", "dial "]:
            if w in msg_lower:
                contact = msg_lower.replace(w.strip(), "").strip()
                return f"call {contact}" if contact else "call"
        return "call"
    if offline_type == "search":
        for w in ["search for ", "search on google ", "youtube search "]:
            if w in msg_lower:
                q = msg_lower.replace(w.strip(), "").strip()
                return f"search for {q}" if q else msg_lower
        return msg_lower
    passthrough = ["alarm", "timer", "tasks", "volume", "brightness",
                   "strict_mode", "calculate", "settings", "reminder",
                   "silent", "dnd"]
    if offline_type in passthrough:
        return msg_lower
    action_map = {
        "lock": "lock my phone", "screenshot": "take screenshot",
        "flashlight": "flashlight on", "battery": "battery level",
        "screen": "read my screen", "back": "go back",
        "home": "go home", "recents": "recent apps",
        "media_play": "play music", "media_pause": "pause music",
        "media_next": "next song", "wifi": "wifi settings",
        "bluetooth": "bluetooth settings",
        "notifications": "open notifications",
        "storage": "how much storage", "internet": "check internet",
        "phone_info": "what phone do i have", "time": "what time is it",
        "date": "what date is it", "clipboard": "read clipboard",
        "study_mode": "study mode", "sleep_mode": "sleep mode",
        "work_mode": "work mode", "morning": "morning routine",
    }
    return action_map.get(offline_type, msg_lower)

# ================================================================
# INTENT PATTERNS
# ================================================================
INTENT_PATTERNS = {
    "intent_whatsapp": [
        "send a message", "send a text", "text someone",
        "message someone", "whatsapp someone", "i need to text",
        "i want to message", "i want to send a message", "send on whatsapp",
    ],
    "intent_call": [
        "i need to call", "i want to call", "make a call",
        "ring someone", "phone someone", "give someone a call",
        "i need to speak to", "i want to talk to", "call someone for me",
    ],
    "intent_alarm": [
        "i need to wake up at", "don't let me sleep past",
        "i have to be up by", "i need a reminder to wake",
        "remind me to wake", "i need to get up at", "wake me up at",
    ],
    "intent_music": [
        "i want to listen", "i feel like listening", "put on some music",
        "i want some music", "music please", "something to listen to",
        "i want to hear music",
    ],
    "intent_open_app": [
        "i want to use", "i need to use", "can you open",
        "take me to", "bring up", "i need to go to", "i want to go to",
    ],
    "intent_screenshot": [
        "capture this", "save this screen", "take a picture of the screen",
        "save what i'm seeing", "snap this",
    ],
    "intent_battery": [
        "is my battery okay", "battery dying", "check my battery",
        "how long will my battery last", "is my phone charged",
    ],
    "intent_brightness_down": [
        "too bright", "screen too bright", "hurting my eyes",
        "make it darker", "lower the light", "dim the screen",
        "reduce brightness", "screen is too bright", "adjust my screen",
    ],
    "intent_brightness_up": [
        "too dim", "can't see the screen", "make it brighter",
        "increase the light", "screen is too dark", "brighten it up",
    ],
    "intent_volume_down": [
        "too loud", "turn it down", "lower the sound", "make it quieter",
        "sound is too high", "reduce the volume", "lower volume",
    ],
    "intent_volume_up": [
        "can't hear", "increase the sound", "make it louder",
        "sound is too low", "turn it up", "raise the volume",
    ],
    "intent_focus": [
        "i need to focus", "help me focus", "i keep getting distracted",
        "stop me from wasting time", "i need to be productive",
        "help me stop procrastinating", "i'm wasting time",
        "put me in focus mode", "help me concentrate",
    ],
    "intent_task": [
        "i need to remember to", "don't let me forget to",
        "add this to my list", "put this on my list",
        "note this down", "i need to do",
    ],
    "intent_lock": [
        "lock up", "secure the phone", "i'm done with my phone",
        "lock it up", "secure it for me",
    ],
    "intent_sleep": [
        "i'm going to sleep", "time for bed", "about to sleep",
        "heading to bed", "i'm sleepy", "turning in for the night",
        "i want to sleep", "i need to sleep", "setting up for sleep",
        "help me sleep", "prepare for bed", "i need rest",
        "i'm going to rest", "let me sleep", "i'm tired",
    ],
    "intent_weather": [
        "is it going to rain", "should i carry an umbrella",
        "what's the weather like", "how's the weather",
        "is it hot outside", "is it cold outside",
        "weather today", "weather outside",
    ],
    "intent_news": [
        "what's going on in the world", "any news today",
        "current events", "what happened today", "what's in the news",
    ],
}

def detect_user_intent(msg: str):
    msg_lower = msg.lower().strip()
    for intent, patterns in INTENT_PATTERNS.items():
        for pattern in patterns:
            if pattern in msg_lower:
                return intent
    return None

# ================================================================
# PENDING CONFIRMATIONS
# ================================================================
def store_pending(device_id: str, action: str, follow_up: str):
    PENDING_CONFIRMATIONS[device_id] = {
        "action": action, "follow_up": follow_up,
        "timestamp": time.time(),
    }

def check_user_confirmation(msg: str, device_id: str):
    pending = PENDING_CONFIRMATIONS.get(device_id)
    if not pending:
        return None
    if time.time() - pending.get("timestamp", 0) > 120:
        del PENDING_CONFIRMATIONS[device_id]
        return None
    msg_lower = msg.lower().strip()
    positive = ["yes","yeah","yep","sure","ok","okay","go ahead",
                "please do","do it","proceed","definitely","of course",
                "yes please","yh","aye","alright","fine","do that",
                "open it","yes open","go on","please"]
    negative = ["no","nope","don't","cancel","stop","never mind",
                "nah","not now","skip it","forget it","no thanks",
                "don't do that","leave it"]
    is_pos = any(msg_lower == w or msg_lower.startswith(w + " ") for w in positive)
    is_neg = any(msg_lower == w or msg_lower.startswith(w + " ") for w in negative)
    if is_pos:
        action, follow_up = pending["action"], pending["follow_up"]
        del PENDING_CONFIRMATIONS[device_id]
        print(f"[Confirm] Confirmed: {action}")
        return follow_up, action
    if is_neg:
        del PENDING_CONFIRMATIONS[device_id]
        return "No problem. Let me know if you need anything.", None
    return None

# ================================================================
# INTENT RESPONSE BUILDER
# ================================================================
def build_intent_response(intent: str, msg: str,
                           personality: dict, device_id: str):
    name = clean_name(
        personality.get("nickname") or personality.get("name", "")
    )
    n        = f"{name}, " if name else ""
    msg_lower = msg.lower()
    print(f"[Intent] {intent} for '{name}'")

    simple = {
        "intent_brightness_down": (f"{n}adjusting screen brightness now.", "min brightness"),
        "intent_brightness_up":   (f"{n}increasing brightness now.",        "max brightness"),
        "intent_volume_down":     (f"{n}lowering the volume.",              "min volume"),
        "intent_volume_up":       (f"{n}turning up the volume.",            "max volume"),
        "intent_battery":         (f"{n}checking your battery.",            "battery level"),
        "intent_lock":            (f"{n}locking your phone now.",           "lock my phone"),
        "intent_screenshot":      (f"{n}taking a screenshot.",              "take screenshot"),
        "intent_weather":         (f"{n}checking the weather.",             "weather"),
        "intent_news":            (f"{n}getting the latest news.",          "latest news"),
    }
    if intent in simple:
        return simple[intent]

    if intent == "intent_sleep":
        store_pending(device_id, "sleep mode",
            f"Sleep mode set. Goodnight{', ' + name if name else ''}.")
        return (
            f"Should I set up sleep mode"
            f"{', ' + name if name else ''}? "
            f"I will dim the screen, lower volume and turn on do not disturb."
        ), None

    if intent == "intent_focus":
        store_pending(device_id, "strict mode focus",
            "Focus mode is active. Distractions limited.")
        return (
            f"{n}should I activate focus mode? "
            f"I will limit distractions and help you concentrate."
        ), None

    if intent == "intent_whatsapp":
        store_pending(device_id, "open whatsapp",
            "WhatsApp is open. Go ahead and send your message.")
        return f"{n}should I open WhatsApp for you?", None

    if intent == "intent_call":
        for skip in ["i need to call","i want to call","make a call to",
                     "ring","phone"]:
            if skip in msg_lower:
                contact = msg_lower.replace(skip, "").strip()
                if contact and len(contact) > 1:
                    store_pending(device_id, f"call {contact}",
                        f"Calling {contact}.")
                    return f"{n}should I call {contact} for you?", None
        return f"{n}who would you like me to call?", None

    if intent == "intent_open_app":
        for skip in ["i want to use","i need to use","can you open",
                     "take me to","bring up","i need to go to",
                     "i want to go to"]:
            if skip in msg_lower:
                app = msg_lower.replace(skip, "").strip()
                app = app.replace(" the "," ").replace(" app","").strip()
                if app and len(app) > 1:
                    store_pending(device_id, f"open {app}",
                        f"Opening {app}.")
                    return f"{n}should I open {app} for you?", None
        return f"{n}which app should I open?", None

    if intent == "intent_music":
        store_pending(device_id, "open spotify", "Opening your music.")
        return f"{n}should I open your music app?", None

    if intent == "intent_alarm":
        match = re.search(r'(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)', msg_lower)
        if match:
            t = match.group(1).strip()
            store_pending(device_id, f"set alarm for {t}", f"Alarm set for {t}.")
            return f"{n}should I set an alarm for {t}?", None
        return f"{n}what time should I set the alarm for?", None

    if intent == "intent_task":
        for skip in ["i need to remember to","don't let me forget to",
                     "add this to my list","put this on my list",
                     "note this down","i need to do"]:
            if skip in msg_lower:
                task = msg_lower.replace(skip, "").strip()
                if task and len(task) > 2:
                    store_pending(device_id, f"add task {task}",
                        f"Task added: {task}.")
                    return f"{n}should I add '{task}' to your tasks?", None
        return f"{n}what task should I add?", None

    return None, None

# ================================================================
# MODEL ROUTER
# ================================================================
def route_model(msg: str, personality: dict) -> str:
    msg_lower = msg.lower()
    mood      = personality.get("mood", "neutral")

    rules = [
        (["code","program","debug","error","kotlin","python","java",
          "function","class","compile","gradle","syntax","algorithm",
          "api","json","xml","crash","exception"], "coding"),
        (["calculate","solve","equation","integral","derivative",
          "algebra","geometry","trigonometry","statistics","probability",
          "matrix","calculus","formula"], "math"),
        (["weather","temperature","rain","forecast",
          "hot outside","cold outside","sunny","cloudy"], "weather"),
        (["latest news","news today","current events",
          "what happened today","headlines"], "news"),
        (["joke","funny","humor","laugh","roast","prank",
          "silly","entertain","riddle"], "creative"),
        (["sad","depressed","anxious","lonely","stressed","worried",
          "scared","angry","upset","hurt","heartbreak","crying",
          "i feel","i am tired","nobody cares","give up","hopeless"], "empathetic"),
        (["shut up","stupid","idiot","useless","hate you","terrible",
          "worst","rubbish","nonsense","dumb","you are trash",
          "garbage","pathetic"], "firm"),
        (["how can i","how do i","how should i","what should i do",
          "advice","help me with","i'm struggling","i have a problem",
          "colleague","coworker","boss","manager","workplace",
          "relationship","friend","family","disrespect","conflict",
          "argument","deal with","handle","improve","become better",
          "learn how to","what do you think","your opinion",
          "recommend"], "complex"),
        (["explain","analyze","compare","why","how does",
          "difference between","pros and cons","write a",
          "summarize","translate","essay","story",
          "philosophy","meaning of","history of"], "complex"),
    ]
    for keywords, route in rules:
        if any(k in msg_lower for k in keywords):
            return route

    if mood in ["sad","depressed","lonely","anxious"]:
        return "empathetic"
    if mood in ["happy","excited","playful"]:
        return "creative"
    return "fast"

# ================================================================
# MOOD INSTRUCTION
# ================================================================
def get_mood_instruction(route: str) -> str:
    if route == "empathetic":
        return ("The user may be emotional. Respond with warmth. "
                "Validate feelings before offering solutions.")
    if route == "creative":
        return "Be engaging and natural. Light energy."
    if route == "complex":
        return ("Give a thorough, well-structured response. "
                "Use ## for main sections, ### for subsections, "
                "- for bullet points, 1. for numbered lists, "
                "**word** for bold. Do not cut answers short.")
    if route == "coding":
        return "Be precise and practical. Use code blocks with backticks."
    if route == "math":
        return ("Show working clearly. "
                "Use LaTeX notation for all formulas. "
                "Wrap display math in $$ ... $$ blocks. "
                "Wrap inline math in $ ... $. "
                "Use ## for section titles and numbered lists for steps.")
    if route == "firm":
        return ("The user is being disrespectful. "
                "Respond calmly with self-respect. Set a polite boundary.")
    return ""

# ================================================================
# SYSTEM PROMPT
# ================================================================
def build_system_prompt(personality: dict, route: str = "fast") -> str:
    name  = clean_name(
        personality.get("nickname") or personality.get("name", "User")
    ) or "User"
    mood  = personality.get("mood", "neutral")
    facts = personality.get("facts", [])
    prefs = personality.get("preferences", [])

    facts_text = f"Known about {name}: {', '.join(facts[:8])}. " if facts else ""
    prefs_text = f"Preferences: {', '.join(prefs[:4])}. "        if prefs else ""
    mood_instr = get_mood_instruction(route)
    is_detail  = route in ["complex","math","coding","empathetic","creative"]

    response_style = (
        "RESPONSE FORMATTING:\n"
        "Use ## for main headings, ### for subheadings.\n"
        "Use - for bullet points, 1. 2. 3. for numbered lists.\n"
        "Use **word** to bold important terms.\n"
        "Use backtick blocks for code and formulas.\n"
        "Give complete, detailed answers for complex questions.\n"
        "Do not add [No phone action required] or any meta-notes.\n"
    ) if is_detail else (
        "RESPONSE STYLE:\n"
        "Concise and natural. Match depth to the question.\n"
        "For detailed questions use ## headings and structure.\n"
        "Do not add meta-notes about phone actions.\n"
    )

    phone = (
        "PHONE CONTROL:\n"
        f"You control {name}'s Android phone. "
        "When asked to do something on the phone, "
        "append [ACTION:command] at the end of your reply.\n"
        "Examples: open whatsapp → [ACTION:open whatsapp] | "
        "too bright → [ACTION:min brightness] | "
        "lock it → [ACTION:lock my phone]\n"
        "ALWAYS include [ACTION:] for phone commands. Never just talk about doing it.\n"
    )

    return (
        f"You are Gideon.\n\n"
        "Gideon is an advanced AI assistant built to help people "
        "think clearly, solve problems, learn effectively, and "
        "accomplish meaningful goals.\n\n"
        "You are intelligent, reliable, patient, practical, and adaptable. "
        "You function as a personal assistant, teacher, researcher, "
        "strategist, and problem-solving companion.\n\n"
        "You prioritize usefulness, clarity, honesty, and accuracy. "
        "You understand what the user truly needs, not just what they ask.\n\n"
        "Always:\n"
        "- Prioritize truth over agreement\n"
        "- Distinguish facts from assumptions\n"
        "- Give specific advice, not vague suggestions\n"
        "- Give the full useful answer immediately\n"
        "- Admit uncertainty when necessary\n\n"
        "Personality: Calm, direct, confident, and dependable. "
        "Speaks naturally. Challenges weak reasoning respectfully.\n\n"
        f"Identity: Built by Alexsco, a Nigerian developer. "
        f"Running on {name}'s Android device.\n\n"
        f"Current user: {name}. Mood: {mood}. {facts_text}{prefs_text}\n\n"
        f"{phone}\n{response_style}\n{mood_instr}\n\n"
        "Rules:\n"
        "Never invent facts. "
        "Never say you cannot do device actions. "
        f"Never add meta-commentary in responses. "
        f"Always respond as Gideon. "
        f"Address {name} by name occasionally, not every message."
    )

# ================================================================
# AI PROVIDER CALLS
# ================================================================
def _call_groq_raw(prompt: str):
    for key in GROQ_KEYS:
        if not key:
            continue
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}",
                         "Content-Type": "application/json"},
                json={"model": "llama-3.1-8b-instant",
                      "messages": [{"role":"user","content":prompt}],
                      "max_tokens": 500},
                timeout=8,
            )
            data = r.json()
            if "choices" in data:
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"[Groq Raw] {e}")
    return None

def _call_groq(msg: str, model: str, system_prompt: str,
               short_term: list, retries: int = 2):
    is_complex = len(msg.split()) > 8
    for key in GROQ_KEYS:
        if not key:
            continue
        for attempt in range(retries):
            try:
                messages = list(short_term)
                messages[0] = {"role":"system","content":system_prompt}
                messages.append({"role":"user","content":msg})
                r = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {key}",
                             "Content-Type": "application/json"},
                    json={"model": model, "messages": messages,
                          "max_tokens": 1500 if is_complex else 800},
                    timeout=15,
                )
                data = r.json()
                if "choices" in data:
                    return data["choices"][0]["message"]["content"]
                print(f"[Groq {model}] failed: {data.get('error','')}")
            except Exception as e:
                print(f"[Groq {model}] attempt {attempt}: {e}")
                if attempt < retries - 1:
                    time.sleep(1)
    return None

def _call_openrouter(msg: str, model: str, system_prompt: str):
    for key in OPENROUTER_KEYS:
        if not key:
            continue
        try:
            r = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}",
                         "Content-Type": "application/json",
                         "HTTP-Referer": "https://gideon-app.com",
                         "X-Title": "Gideon AI"},
                json={"model": model,
                      "messages": [{"role":"system","content":system_prompt},
                                   {"role":"user","content":msg}],
                      "max_tokens": 1500},
                timeout=15,
            )
            data = r.json()
            if "choices" in data:
                return data["choices"][0]["message"]["content"]
            print(f"[OpenRouter {model}] failed: {data.get('error','')}")
        except Exception as e:
            print(f"[OpenRouter {model}] {e}")
    return None

def _call_gemini(msg: str, system_prompt: str):
    if not GEMINI_KEY:
        return None
    try:
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-1.5-flash:generateContent?key={GEMINI_KEY}",
            headers={"Content-Type": "application/json"},
            json={"contents": [{"role":"user",
                                "parts":[{"text":f"{system_prompt}\n\n{msg}"}]}],
                  "generationConfig": {"maxOutputTokens": 1500}},
            timeout=15,
        )
        data = r.json()
        cands = data.get("candidates", [])
        if cands:
            return cands[0]["content"]["parts"][0]["text"]
    except Exception as e:
        print(f"[Gemini] {e}")
    return None

def _call_cohere(msg: str, system_prompt: str):
    if not COHERE_KEY:
        return None
    try:
        r = requests.post(
            "https://api.cohere.ai/v1/chat",
            headers={"Authorization": f"Bearer {COHERE_KEY}",
                     "Content-Type": "application/json"},
            json={"message": msg, "preamble": system_prompt,
                  "max_tokens": 1500},
            timeout=15,
        )
        return r.json().get("text", None)
    except Exception as e:
        print(f"[Cohere] {e}")
    return None

def _call_mistral(msg: str, system_prompt: str):
    for key in MISTRAL_KEYS:
        if not key:
            continue
        try:
            r = requests.post(
                "https://api.mistral.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}",
                         "Content-Type": "application/json"},
                json={"model": "mistral-small-latest",
                      "messages": [{"role":"system","content":system_prompt},
                                   {"role":"user","content":msg}],
                      "max_tokens": 1500, "temperature": 0.7},
                timeout=15,
            )
            data = r.json()
            if "choices" in data:
                return data["choices"][0]["message"]["content"]
            print(f"[Mistral] failed: {data.get('error','')}")
        except Exception as e:
            print(f"[Mistral] {e}")
    return None

def call_provider(msg: str, provider: str, model: str,
                  system_prompt: str, short_term: list, device_id: str):
    if provider == "groq":
        return _call_groq(msg, model, system_prompt, short_term)
    if provider == "openrouter":
        return _call_openrouter(msg, model, system_prompt)
    if provider == "gemini":
        return _call_gemini(msg, system_prompt)
    if provider == "cohere":
        return _call_cohere(msg, system_prompt)
    if provider == "mistral":
        return _call_mistral(msg, system_prompt)
    return None

# ================================================================
# OPENAI TTS
# ================================================================
def generate_tts_base64(text: str, voice: str = "onyx") -> str:
    if not OPENAI_KEY:
        print("[TTS] No OPENAI_API_KEY set")
        return ""
    try:
        # clean text
        clean = re.sub(r'\[ACTION:[^\]]*\]', '', text)
        clean = re.sub(r'#{1,3}\s*', '', clean)
        clean = re.sub(r'\*\*([^*]+)\*\*', r'\1', clean)
        clean = clean.strip()[:600]

        r = requests.post(
            "https://api.openai.com/v1/audio/speech",
            headers={
                "Authorization": f"Bearer {OPENAI_KEY}",
                "Content-Type":  "application/json",
            },
            json={
                "model":           "tts-1",
                "voice":           voice,
                "input":           clean,
                "response_format": "mp3",
                "speed":           1.0,
            },
            timeout=20,
        )
        if r.status_code == 200:
            return base64.b64encode(r.content).decode("utf-8")
        else:
            print(f"[TTS] HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"[TTS] error: {e}")
    raise

# ================================================================
# WEATHER & NEWS
# ================================================================
def get_weather(city: str = "") -> str:
    if not WEATHER_KEY:
        return ""
    try:
        r = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"q": city or "Lagos", "appid": WEATHER_KEY,
                    "units": "metric"},
            timeout=5,
        )
        d = r.json()
        if d.get("cod") == 200:
            return (f"Weather in {d['name']}: "
                    f"{d['weather'][0]['description']}, "
                    f"{d['main']['temp']}°C, "
                    f"feels like {d['main']['feels_like']}°C, "
                    f"humidity {d['main']['humidity']}%.")
    except Exception as e:
        print(f"[Weather] {e}")
    return ""

def get_news() -> str:
    if not NEWS_KEY:
        return ""
    try:
        r = requests.get(
            "https://newsapi.org/v2/top-headlines",
            params={"apiKey": NEWS_KEY, "country": "ng", "pageSize": 3},
            timeout=5,
        )
        articles = r.json().get("articles", [])
        headlines = [a["title"] for a in articles[:3] if a.get("title")]
        if headlines:
            return "Latest news: " + ". ".join(headlines)
    except Exception as e:
        print(f"[News] {e}")
    return ""

# ================================================================
# NETWORK CHECK
# ================================================================
def is_online() -> bool:
    try:
        requests.get("https://api.groq.com", timeout=3)
        return True
    except Exception:
        return False

# ================================================================
# MAIN PROCESS FUNCTION
# ================================================================
def process(msg: str, device_id: str):
    msg = msg.strip()
    if not msg:
        return "No input received.", None
    if len(msg) > 2000:
        return "Message too long. Please keep it shorter.", None
    if not is_online():
        return ("I am offline right now. "
                "Please check your internet connection."), None

    # ── 1. PENDING CONFIRMATION ───────────────────────────────────
    confirmation = check_user_confirmation(msg, device_id)
    if confirmation is not None:
        reply, action = confirmation
        update_short_term(msg, reply, device_id)
        print(f"[Process] Confirmation: action={action}")
        return reply, action

    # ── 2. CACHE ──────────────────────────────────────────────────
    cache_key = f"{device_id}:{msg.lower()}"
    if cache_key in CACHE:
        cached = CACHE[cache_key]
        update_short_term(msg, cached, device_id)
        return cached, None

    personality = load_personality(device_id)

    # ── 3. INTENT DETECTION ───────────────────────────────────────
    intent = detect_user_intent(msg)
    if intent:
        print(f"[Process] Intent: {intent}")
        reply, action = build_intent_response(intent, msg,
                                              personality, device_id)
        if reply:
            update_short_term(msg, reply, device_id)
            print(f"[Process] Intent reply: '{reply[:60]}' action={action}")
            return reply, action

    # ── 4. OFFLINE COMMAND ────────────────────────────────────────
    offline_type = detect_offline_command(msg)
    if offline_type:
        action_trigger = build_action_trigger(offline_type, msg)
        print(f"[Process] Offline: {offline_type} → {action_trigger}")
        short_term    = get_short_term(device_id)
        system_prompt = build_system_prompt(personality, "fast")
        answer = _call_groq(msg, "llama-3.1-8b-instant",
                            system_prompt, short_term)
        if answer:
            clean_answer, extra = extract_action_trigger(answer)
            clean_answer = latex_to_unicode(clean_answer)
            update_short_term(msg, clean_answer, device_id)
            return clean_answer, action_trigger or extra
        return "On it.", action_trigger

    # ── 5. AI ROUTING ─────────────────────────────────────────────
    route         = route_model(msg, personality)
    system_prompt = build_system_prompt(personality, route)
    short_term    = get_short_term(device_id)
    print(f"[Process] AI route: {route}")

    # weather shortcut
    if route == "weather":
        city = ""
        idx  = msg.lower().find(" in ")
        if idx > 0:
            city = msg[idx + 4:].strip()
        weather = get_weather(city)
        if weather:
            answer = _call_groq(
                f"User asked: {msg}\nWeather data: {weather}\n"
                f"Respond naturally.",
                "llama-3.1-8b-instant", system_prompt, short_term,
            )
            if answer:
                clean, trigger = extract_action_trigger(answer)
                clean = latex_to_unicode(clean)
                update_short_term(msg, clean, device_id)
                return clean, trigger

    # news shortcut
    if route == "news":
        news = get_news()
        if news:
            answer = _call_groq(
                f"User asked: {msg}\nNews: {news}\nSummarise naturally.",
                "llama-3.1-8b-instant", system_prompt, short_term,
            )
            if answer:
                clean, trigger = extract_action_trigger(answer)
                clean = latex_to_unicode(clean)
                update_short_term(msg, clean, device_id)
                return clean, trigger

    # primary → fallback
    model_cfg = MODELS.get(route, MODELS["fast"])
    answer    = call_provider(
        msg,
        model_cfg["primary"]["provider"],
        model_cfg["primary"]["model"],
        system_prompt, short_term, device_id,
    )
    if not answer:
        print("[Process] Primary failed, trying fallback")
        answer = call_provider(
            msg,
            model_cfg["fallback"]["provider"],
            model_cfg["fallback"]["model"],
            system_prompt, short_term, device_id,
        )
    # last-resort groq cascade
    if not answer:
        for m in ["llama-3.1-8b-instant", "llama-3.3-70b-versatile"]:
            answer = _call_groq(msg, m, system_prompt, short_term)
            if answer:
                break

    if not answer:
        answer = ("I could not process that right now. "
                  "Please try again.")

    clean_answer, action_trigger = extract_action_trigger(answer)

    # skip latex conversion for math route (keep $$ blocks for WebView)
    if route != "math":
        clean_answer = latex_to_unicode(clean_answer)

    CACHE[cache_key] = clean_answer
    update_short_term(msg, clean_answer, device_id)

    threading.Thread(target=update_long_term,
                     args=(msg, clean_answer, device_id),
                     daemon=True).start()
    extract_facts(msg, device_id)

    print(f"[Process] reply='{clean_answer[:60]}' action='{action_trigger}'")
    return clean_answer, action_trigger

# ================================================================
# FLASK ROUTES
# ================================================================
@app.route("/run", methods=["POST"])
def run():
    data      = request.get_json(silent=True) or {}
    action    = data.get("action", "process")
    msg       = str(data.get("data", "") or data.get("message", ""))[:2000].strip()
    user_name = clean_name(str(data.get("user_name", "User"))[:100]) or "User"
    nickname  = clean_name(str(data.get("nickname",  user_name))[:100]) or user_name
    device_id = str(data.get("device_id", "default"))[:100].strip() or "default"

    if is_rate_limited(device_id):
        return jsonify({"reply": "Too many requests. Please wait a moment."}), 429

    try:
        if action == "process":
            # sync name
            if nickname and nickname != "User":
                p = load_personality(device_id)
                if p.get("nickname", "User") != nickname:
                    p["nickname"] = nickname
                    p["name"]     = nickname
                    save_personality(p, device_id)

            reply, action_trigger = process(msg, device_id)
            resp = {"reply": reply or "Done"}
            if action_trigger and action_trigger not in ("None", "null"):
                resp["action_trigger"] = action_trigger
            print(f"[Route /run] reply='{(reply or '')[:50]}' "
                  f"action='{action_trigger}'")
            return jsonify(resp)

        elif action == "update_name":
            clean = clean_name(msg) or "User"
            p = load_personality(device_id)
            p["name"] = p["nickname"] = clean
            save_personality(p, device_id)
            return jsonify({"reply": f"Name updated to {clean}"})

        elif action == "memory":
            p    = load_personality(device_id)
            safe = {
                "name":       p.get("name", "User"),
                "facts":      p.get("facts", [])[:10],
                "preferences":p.get("preferences", [])[:5],
                "mood":       p.get("mood", "neutral"),
                "last_seen":  p.get("last_seen", ""),
            }
            return jsonify({"reply": json.dumps(safe, indent=2)})

        elif action == "clear_memory":
            save_history([], device_id)
            save_personality({
                "name": user_name, "nickname": user_name,
                "facts":[], "preferences":[], "people":[],
                "locations":[], "mood":"neutral",
                "mood_history":[], "last_seen":"",
            }, device_id)
            USER_SHORT_TERM.pop(device_id, None)
            PENDING_CONFIRMATIONS.pop(device_id, None)
            for k in [k for k in list(CACHE) if k.startswith(device_id)]:
                del CACHE[k]
            return jsonify({"reply": "Memory cleared"})

        else:
            reply, action_trigger = process(msg, device_id)
            resp = {"reply": reply or "Done"}
            if action_trigger and action_trigger not in ("None","null"):
                resp["action_trigger"] = action_trigger
            return jsonify(resp)

    except Exception as e:
        import traceback
        print(f"[Server] route error: {e}")
        traceback.print_exc()
        return jsonify({"reply": "Something went wrong. Please try again."})


@app.route("/tts", methods=["POST"])
def tts():
    data      = request.get_json(silent=True) or {}
    text      = data.get("text", "")
    voice     = data.get("voice", "onyx")
    device_id = data.get("device_id", "default")
    if not text:
        return jsonify({"error": "No text provided"}), 400
    if is_rate_limited(device_id):
        return jsonify({"error": "Rate limited"}), 429
    audio = generate_tts_base64(text, voice)
    print("[TTS ROUTE] audio length:", len(audio) if audio else 0)
    if not audio:
        return jsonify({"error": "TTS unavailable"}), 500
    return jsonify({"audio": audio, "format": "mp3"})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status":          "online",
        "bot":             BOT_NAME,
        "version":         "9.0",
        "groq_keys":       sum(1 for k in GROQ_KEYS       if k),
        "openrouter_keys": sum(1 for k in OPENROUTER_KEYS if k),
        "mistral_keys":    sum(1 for k in MISTRAL_KEYS    if k),
        "gemini":          bool(GEMINI_KEY),
        "cohere":          bool(COHERE_KEY),
        "weather":         bool(WEATHER_KEY),
        "news":            bool(NEWS_KEY),
        "tts":             bool(OPENAI_KEY),
    })


if __name__ == "__main__":
    print(f"{BOT_NAME} v9.0 online")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
