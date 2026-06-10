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
        "fallback": {"provider": "openrouter", "model": "google/gemma-2-9b-it:free"}
    },
    "creative": {
        "primary": {"provider": "groq", "model": "llama-3.3-70b-versatile"},
        "fallback": {"provider": "openrouter", "model": "mistralai/mistral-7b-instruct:free"}
    },
    "empathetic": {
        "primary": {"provider": "groq", "model": "llama-3.3-70b-versatile"},
        "fallback": {"provider": "openrouter", "model": "google/gemma-2-9b-it:free"}
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
        "primary": {"provider": "openrouter", "model": "google/gemma-3-12b-it:free"},
        "fallback": {"provider": "groq", "model": "llama-3.1-8b-instant"}
    },
    "coding": {
        "primary": {"provider": "openrouter", "model": "deepseek/deepseek-coder:free"},
        "fallback": {"provider": "groq", "model": "llama-3.3-70b-versatile"}
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

OFFLINE_COMMAND_ACTIONS = {
    "open": "open {app}",
    "call": "call {contact}",
    "alarm": "set alarm",
    "timer": "set timer",
    "screenshot": "take screenshot",
    "lock": "lock my phone",
    "flashlight": "flashlight on",
    "volume": "volume up",
    "brightness": "increase brightness",
    "silent": "silent mode",
    "wifi": "wifi settings",
    "bluetooth": "bluetooth settings",
    "battery": "battery level",
    "tasks": "show my tasks",
    "screen": "read my screen",
    "back": "go back",
    "home": "go home",
    "recents": "recent apps",
    "search": "search for",
    "media_play": "play music",
    "media_pause": "pause music",
    "media_next": "next song",
}

def build_action_trigger(offline_type: str, msg: str) -> str:
    """Build a clean action trigger command from the offline type and message."""
    msg_lower = msg.lower()

    if offline_type == "open":
        # extract app name
        for word in ["open", "launch", "start"]:
            if word in msg_lower:
                app = msg_lower.replace(word, "").strip()
                # clean common words
                app = app.replace("the", "").replace("app", "").strip()
                if app:
                    return f"open {app}"
        return "open"

    if offline_type == "call":
        for word in ["call", "dial", "phone"]:
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

    # for most commands just return the matching pattern directly
    action_map = {
        "lock": "lock my phone",
        "screenshot": "take screenshot",
        "flashlight": "flashlight on",
        "battery": "battery level",
        "tasks": "show my tasks",
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
    }

    return action_map.get(offline_type, msg_lower)

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
        return "I am offline right now. Please check your internet connection.", None

    cache_key = f"{device_id}:{msg.lower()}"
    if cache_key in CACHE:
        cached = CACHE[cache_key]
        update_short_term(msg, cached, device_id)
        return cached, None

    # detect if this should trigger an offline command on Android
    offline_type = detect_offline_command(msg)
    if offline_type:
        personality = load_personality(device_id)
        system_prompt = build_system_prompt(personality, "fast")
        short_term = get_short_term(device_id)

        # build a clean action trigger
        action_trigger = build_action_trigger(offline_type, msg)

        # get AI to respond naturally about what it is doing
        answer = _call_groq(
            msg, "llama-3.1-8b-instant", system_prompt, short_term
        )

        if answer:
            clean_answer, _ = extract_action_trigger(answer)
            update_short_term(msg, clean_answer, device_id)
            return clean_answer, action_trigger

        return "On it.", action_trigger

    personality = load_personality(device_id)
    route = route_model(msg, personality)
    system_prompt = build_system_prompt(personality, route)
    short_term = get_short_term(device_id)

    model_config = MODELS.get(route, MODELS["fast"])
    primary = model_config["primary"]
    fallback = model_config["fallback"]

    print(f"[Router] Route: {route}, Model: {primary['model']}")

    answer = call_provider(
        msg,
        primary["provider"],
        primary["model"],
        system_prompt,
        short_term,
        device_id
    )

    if not answer:
        print(f"[Router] Primary failed, trying: {fallback['model']}")
        answer = call_provider(
            msg,
            fallback["provider"],
            fallback["model"],
            system_prompt,
            short_term,
            device_id
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
