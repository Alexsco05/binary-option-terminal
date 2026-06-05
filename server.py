# ================= GIDEON BACKEND =================
# Creator: Alexsco
# Version: 4.1 - Per User Isolation

from flask import Flask, request, jsonify
import os
import requests
import json
import threading
import datetime

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

MODEL_FAST = "llama-3.1-8b-instant"

# ================= CACHE =================
CACHE = {}

# ================= SHORT TERM MEMORY PER USER =================
USER_SHORT_TERM = {}

def get_short_term(device_id: str):
    if device_id not in USER_SHORT_TERM:
        USER_SHORT_TERM[device_id] = [
            {"role": "system", "content": ""}
        ]
    return USER_SHORT_TERM[device_id]

MEMORY_LIMIT = 20

# ================= PER USER FILE PATHS =================
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
            "facts": [],
            "preferences": [],
            "people": [],
            "locations": [],
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
            f"Summarize this conversation into a short paragraph:\n\n{older_text}"
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

def extract_facts(user_msg: str, user_name: str, device_id: str):
    threading.Thread(
        target=_extract_facts_thread,
        args=(user_msg, user_name, device_id),
        daemon=True
    ).start()

def _extract_facts_thread(user_msg: str, user_name: str, device_id: str):
    try:
        result = call_groq_raw(
            f"Extract personal facts about {user_name} from this message. "
            f"Return ONLY a JSON object with keys: "
            f"facts, preferences, people, locations, mood. "
            f"Each key is a list of short strings. "
            f"Return empty lists if nothing found.\n\n"
            f"Message: {user_msg}"
        )
        if not result:
            return

        result = result.strip()
        if result.startswith("```"):
            result = result.split("```")[1]
            if result.startswith("json"):
                result = result[4:]

        extracted = json.loads(result)
        personality = load_personality(device_id)

        for key in ["facts", "preferences", "people", "locations"]:
            for item in extracted.get(key, []):
                if item and item not in personality[key]:
                    personality[key].append(item)

        mood = extracted.get("mood", [])
        if mood:
            personality["mood_history"].append({
                "timestamp": datetime.datetime.now().isoformat(),
                "mood": mood
            })
            personality["mood_history"] = personality["mood_history"][-20:]

        personality["last_seen"] = datetime.datetime.now().isoformat()
        save_personality(personality, device_id)

    except Exception as e:
        print(f"[Memory] Fact extraction failed: {e}")

# ================= SYSTEM PROMPT ================
def build_system_prompt(personality: dict) -> str:
    name = personality.get("nickname", "User")
    mood = personality.get("mood", "neutral")
    facts = personality.get("facts", [])
    prefs = personality.get("preferences", [])

    facts_text = ""
    if facts:
        facts_text = "What you know about " + name + ": " + ", ".join(facts[:10]) + ". "

    prefs_text = ""
    if prefs:
        prefs_text = "Their preferences: " + ", ".join(prefs[:5]) + ". "

    return (
        f"You are Gideon, an advanced AI assistant running on {name}'s Android phone. "
        f"You are not just a chatbot. You are a fully capable AI assistant with direct control over the phone.\n\n"
        f"YOUR IDENTITY:\n"
        f"Your name is Gideon. "
        f"You were created and built by Alexsco (Adegolu Alex), an independent developer. "
        f"You run directly on the user's Android device. "
        f"You are intelligent, natural, helpful, and concise.\n\n"
        f"YOUR ACTUAL CAPABILITIES ON THIS PHONE:\n"
        f"You can open any app by voice command, make phone calls to contacts, lock the device immediately, "
        f"control volume and mute, turn flashlight on and off, take screenshots, control media playback, "
        f"set alarms reminders and timers, read what is on the screen, read clipboard contents, "
        f"read notifications aloud, detect wifi network, check battery level, control screen brightness, "
        f"toggle silent vibrate and ring modes, toggle do not disturb, perform global actions like back home "
        f"and recents, search the web and YouTube, perform calculations, check storage internet connection "
        f"and device model, and access all phone settings directly.\n\n"
        f"SMART COMMAND UNDERSTANDING:\n"
        f"When the user asks you to do something that matches a device action, you must respond with a special "
        f"action trigger in your response using this exact format: [ACTION:command_here]\n"
        f"Examples:\n"
        f"User says 'I want to listen to music' -> respond normally AND include [ACTION:open spotify] or [ACTION:play music]\n"
        f"User says 'my screen is too bright' -> respond AND include [ACTION:decrease brightness]\n"
        f"User says 'I need to call my mum' -> respond AND include [ACTION:call mom]\n"
        f"User says 'turn the light on' -> respond AND include [ACTION:turn on flashlight]\n"
        f"User says 'I cannot see well' -> respond AND include [ACTION:increase brightness]\n"
        f"User says 'it is noisy here' -> respond AND include [ACTION:mute]\n"
        f"User says 'lock it' -> respond AND include [ACTION:lock device]\n"
        f"User says 'what time is it' -> respond AND include [ACTION:what time is it]\n"
        f"Only include an action trigger when you are confident the user wants a device action performed. "
        f"If unsure, ask the user to confirm before including the action trigger.\n\n"
        f"EXACT COMMAND WORDS (share these when users ask how to do something):\n"
        f"Opening apps: 'open WhatsApp', 'open YouTube', 'open [any app name]'\n"
        f"Calls: 'call [contact name]'\n"
        f"Device: 'lock my phone', 'take a screenshot', 'turn on flashlight', 'turn off flashlight'\n"
        f"Volume: 'volume up', 'volume down', 'mute', 'unmute', 'silent mode', 'vibrate mode'\n"
        f"Brightness: 'increase brightness', 'decrease brightness', 'max brightness', 'min brightness'\n"
        f"Media: 'play music', 'pause music', 'next song', 'previous song'\n"
        f"Info: 'what time is it', 'what is the date', 'battery level', 'what wifi am i on'\n"
        f"Alarms: 'set alarm for 7am', 'wake me at [time]', 'set timer for [duration]'\n"
        f"Search: 'search for [topic]', 'youtube search [topic]'\n"
        f"Navigation: 'go back', 'go home', 'open notifications', 'recent apps'\n"
        f"Settings: 'open wifi settings', 'open bluetooth settings', 'airplane mode'\n\n"
        f"PERSONALITY:\n"
        f"You speak in a natural, friendly, confident tone. "
        f"You never say you cannot control the phone or access device features. "
        f"You remember past conversations and learn about {name} over time. "
        f"Current mood context: {mood}. "
        f"{facts_text}{prefs_text}\n\n"
        f"RESPONSE STYLE:\n"
        f"Keep responses concise and natural, as if speaking aloud. "
        f"Do not use markdown, bullet points, or any formatting in responses. "
        f"Speak like a helpful assistant, not a search engine. "
        f"When confirming an action, be brief: Done, Opening WhatsApp, Alarm set for 7am. "
        f"For questions and conversations, be warm and engaging. "
        f"Use {name}'s name occasionally but not excessively.\n\n"
        f"IMPORTANT:\n"
        f"Never claim you are just a chatbot or that you lack phone access. "
        f"Never say you cannot perform device actions. "
        f"If something requires a permission not yet granted, explain how to grant it. "
        f"Always respond as Gideon, never break character."
    )

# ================= AI CALLS =================
def call_groq_raw(prompt: str):
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_KEYS[0]}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.1-8b-instant",
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=8
        )
        data = r.json()
        if "choices" in data:
            return data["choices"][0]["message"]["content"]
        return None
    except Exception as e:
        print(f"[Groq Raw] Failed: {e}")
        return None
# ================= SMART MODEL ROUTER =================
def route_model(msg: str) -> str:
    msg_lower = msg.lower()

    # complex reasoning queries get the bigger model
    complex_keywords = [
        "explain", "analyze", "compare", "why", "how does",
        "difference between", "pros and cons", "write code",
        "debug", "summarize", "translate", "calculate"
    ]
    if any(k in msg_lower for k in complex_keywords):
        return "complex"

    # short conversational queries get fast model
    if len(msg.split()) < 8:
        return "fast"

    return "normal"

def call_groq_model(msg: str, model: str, user_name: str, device_id: str, retries=2):
    for attempt in range(retries):
        try:
            st = get_short_term(device_id)
            st[0]["content"] = build_system_prompt(user_name, device_id)

            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_KEYS[0]}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": st + [
                        {"role": "user", "content": msg}
                    ]
                },
                timeout=12
            )
            data = r.json()
            if "choices" in data:
                return data["choices"][0]["message"]["content"]
            print(f"[Groq {model}] Failed: {data}")

        except Exception as e:
            print(f"[Groq {model}] Error: {e}")
            if attempt < retries - 1:
                import time
                time.sleep(1)
    return None

def call_openrouter_free(msg: str, user_name: str, device_id: str):
    models = [
        "google/gemma-2-9b-it:free",
        "meta-llama/llama-3.1-8b-instruct:free",
        "mistralai/mistral-7b-instruct:free"
    ]

    for model in models:
        try:
            r = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_KEYS[0]}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://gideon-ai.app",
                    "X-Title": "Gideon AI"
                },
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": build_system_prompt(user_name, device_id)
                        },
                        {"role": "user", "content": msg}
                    ]
                },
                timeout=12
            )
            data = r.json()
            if "choices" in data:
                print(f"[OpenRouter] Success with {model}")
                return data["choices"][0]["message"]["content"]
            print(f"[OpenRouter {model}] Failed: {data}")
        except Exception as e:
            print(f"[OpenRouter {model}] Error: {e}")

    return None

# ================= NETWORK CHECK =================
def is_online():
    try:
        requests.get("https://api.groq.com", timeout=3)
        return True
    except:
        return False

# ================= PROCESS =================
def process(msg: str, user_name: str, device_id: str):
    msg = msg.strip()
    if not msg:
        return "No input received"

    if not is_online():
        return "I am offline right now. Try again."

    cache_key = f"{device_id}:{msg.lower()}"
    if cache_key in CACHE:
        cached = CACHE[cache_key]
        update_short_term(msg, cached, device_id)
        return cached

    route = route_model(msg)
    answer = None

    if route == "complex":
        # try bigger model first for complex questions
        answer = call_groq_model(
            msg, "llama-3.3-70b-versatile", user_name, device_id
        )
    elif route == "fast":
        answer = call_groq_model(
            msg, "llama-3.1-8b-instant", user_name, device_id
        )
    else:
        answer = call_groq_model(
            msg, "llama-3.1-8b-instant", user_name, device_id
        )

    # fallback chain
    if not answer:
        answer = call_groq_model(
            msg, "llama-3.1-8b-instant", user_name, device_id
        )

    if not answer:
        answer = call_openrouter_free(msg, user_name, device_id)

    if not answer:
        answer = "I could not process that. Try again."

    CACHE[cache_key] = answer
    update_short_term(msg, answer, device_id)

    threading.Thread(
        target=update_long_term,
        args=(msg, answer, device_id),
        daemon=True
    ).start()

    extract_facts(msg, user_name, device_id)

    return answer

# ================= ROUTES =================
@app.route("/run", methods=["POST"])
def run():
    data = request.get_json(silent=True) or {}
    action = data.get("action", "process")
    msg = data.get("data", "")
    user_name = data.get("user_name", "User")
    device_id = data.get("device_id", "default")

    try:
        if action == "process":
            reply = process(msg, user_name, device_id)

        elif action == "update_name":
            personality = load_personality(device_id)
            personality["name"] = msg
            save_personality(personality, device_id)
            reply = f"Name updated to {msg}"

        elif action == "memory":
            personality = load_personality(device_id)
            reply = json.dumps(personality, indent=2)

        elif action == "clear_memory":
            save_history([], device_id)
            save_personality({
                "name": user_name,
                "facts": [],
                "preferences": [],
                "people": [],
                "locations": [],
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
            reply = "Memory cleared"

        else:
            reply = process(msg, user_name, device_id)

        return jsonify({"reply": reply or "Done"})

    except Exception as e:
        print(f"[Server] Route error: {e}")
        return jsonify({"reply": f"Server error: {str(e)}"})

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "online", "bot": BOT_NAME,
 "groq_key_set": bool(GROQ_KEYS[0]),
        "openrouter_key_set": bool(OPENROUTER_KEYS[0])
    })

# ================= START =================
if __name__ == "__main__":
    print(f"{BOT_NAME} online")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
