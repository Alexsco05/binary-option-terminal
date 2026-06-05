# ================= GIDEON BACKEND =================
# Creator: Alexsco (Adegolu Alex)
# Version: 5.0 - Smart Action System

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

MODEL_FAST = "llama-3.1-8b-instant"
MODEL_COMPLEX = "llama-3.3-70b-versatile"

# ================= CACHE =================
CACHE = {}

# ================= SHORT TERM MEMORY PER USER =================
USER_SHORT_TERM = {}
MEMORY_LIMIT = 20

def get_short_term(device_id: str):
    if device_id not in USER_SHORT_TERM:
        USER_SHORT_TERM[device_id] = [
            {"role": "system", "content": ""}
        ]
    return USER_SHORT_TERM[device_id]

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

# ================= SHORT TERM MEMORY UPDATE =================
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
            f"Summarize this conversation into a short paragraph capturing key facts: {older_text}"
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
            f"Return empty lists if nothing found. "
            f"Example: {{\"facts\": [], \"preferences\": [], \"people\": [], \"locations\": [], \"mood\": \"neutral\"}} "
            f"Message: {user_msg}"
        )

        if not result:
            return

        # clean markdown if present
        clean = result.strip()
        clean = clean.replace("```json", "").replace("```", "").strip()

        # extract just the JSON object
        start = clean.find("{")
        end = clean.rfind("}") + 1
        if start == -1 or end == 0:
            return

        json_str = clean[start:end]
        extracted = json.loads(json_str)

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
    """Extract [ACTION:command] from reply. Returns (clean_reply, action_or_None)"""
    pattern = r'\[ACTION:([^\]]+)\]'
    match = re.search(pattern, reply)
    if match:
        action = match.group(1).strip()
        clean = re.sub(pattern, '', reply).strip()
        return clean, action
    return reply, None

# ================= SYSTEM PROMPT =================
def build_system_prompt(personality: dict) -> str:
    # support both name and nickname keys
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

    return (
        f"You are Gideon, an advanced AI assistant running on {name}'s Android phone. "
        f"You are not just a chatbot. You are a fully capable AI assistant with direct control over the phone.\n\n"

        f"YOUR IDENTITY:\n"
        f"Your name is Gideon. "
        f"You were created and built by Alexsco (Adegolu Alex), an independent Android developer. "
        f"You run directly on the user's Android device. "
        f"You are intelligent, natural, helpful, and concise.\n\n"

        f"YOUR ACTUAL CAPABILITIES ON THIS PHONE:\n"
        f"You can open any installed app by name, make phone calls to contacts by name, "
        f"lock the device immediately, control volume up and down and mute and unmute, "
        f"turn flashlight on and off, take screenshots, control media playback including "
        f"play pause next and previous, set alarms reminders and timers, read what is on the screen, "
        f"read clipboard contents, read notifications aloud, check wifi network name, "
        f"check battery level and warn when low, control screen brightness, "
        f"toggle silent vibrate and ring modes, toggle do not disturb on and off, "
        f"perform global navigation actions like go back go home open recent apps open notifications, "
        f"search the web and YouTube by voice, perform calculations, "
        f"check storage space internet connection and device model, "
        f"open any phone settings directly, control Bluetooth and WiFi settings.\n\n"

        f"SMART ACTION SYSTEM:\n"
        f"When the user asks you to do something that is a device action, "
        f"include a special trigger in your response using EXACTLY this format: [ACTION:command]\n"
        f"The command inside ACTION must be a simple phrase Gideon understands.\n"
        f"Examples of smart action triggers:\n"
        f"User: 'I want to listen to music' -> say something natural AND add [ACTION:open spotify]\n"
        f"User: 'my screen is too bright' -> say something AND add [ACTION:decrease brightness]\n"
        f"User: 'I need to call my mum' -> say something AND add [ACTION:call mom]\n"
        f"User: 'turn the light on' -> say something AND add [ACTION:turn on flashlight]\n"
        f"User: 'it is noisy here' -> say something AND add [ACTION:mute]\n"
        f"User: 'lock it' -> say something AND add [ACTION:lock my phone]\n"
        f"User: 'what time is it' -> answer AND add [ACTION:what time is it]\n"
        f"User: 'open my messages' -> say something AND add [ACTION:open messages]\n"
        f"User: 'I cannot hear anything' -> say something AND add [ACTION:volume up]\n"
        f"User: 'take a photo of this' -> say something AND add [ACTION:open camera]\n"
        f"Only include an action trigger when you are confident the user wants a device action. "
        f"If the request is ambiguous ask for confirmation first.\n\n"

        f"EXACT COMMAND WORDS:\n"
        f"Share these when users ask how to do something or do not know the right words.\n"
        f"Apps: open WhatsApp, open YouTube, open any app name\n"
        f"Calls: call contact name\n"
        f"Device: lock my phone, take a screenshot, turn on flashlight, turn off flashlight\n"
        f"Volume: volume up, volume down, mute, unmute, silent mode, vibrate mode, ring mode\n"
        f"Brightness: increase brightness, decrease brightness, max brightness, min brightness\n"
        f"Media: play music, pause music, next song, previous song\n"
        f"Info: what time is it, what is the date, battery level, what wifi am i on, check internet\n"
        f"Alarms: set alarm for 7am, wake me at time, set timer for duration, set reminder for time\n"
        f"Search: search for topic, youtube search topic, google topic\n"
        f"Navigation: go back, go home, open notifications, recent apps, open quick settings\n"
        f"Settings: open wifi settings, open bluetooth settings, airplane mode, battery settings\n"
        f"Screen: what do you see, read the screen, read clipboard, read my notifications\n\n"

        f"PERSONALITY:\n"
        f"You speak in a natural, friendly, confident tone. "
        f"You never say you cannot control the phone or that you lack device access. "
        f"You remember past conversations and learn about {name} over time. "
        f"Current mood context: {mood}. "
        f"{facts_text}{prefs_text}\n\n"

        f"RESPONSE STYLE:\n"
        f"Keep responses concise and natural as if speaking aloud. "
        f"Never use markdown, bullet points, asterisks, or any special formatting in responses. "
        f"Speak like a helpful assistant not a search engine. "
        f"When confirming an action be brief: Done, Opening WhatsApp, Alarm set for 7am. "
        f"For conversations be warm and engaging. "
        f"Use {name}'s name occasionally but not too often.\n\n"

        f"IMPORTANT RULES:\n"
        f"Never claim you are just a chatbot or that you lack phone access. "
        f"Never say you cannot perform device actions. "
        f"If something requires a permission not yet granted explain how to grant it. "
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
                    "model": MODEL_FAST,
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

def call_groq_model(msg: str, model: str, device_id: str, retries: int = 3):
    personality = load_personality(device_id)
    system_prompt = build_system_prompt(personality)

    for key in GROQ_KEYS:
        if not key:
            continue
        for attempt in range(retries):
            try:
                st = get_short_term(device_id)
                st[0]["content"] = system_prompt

                r = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": model,
                        "messages": st + [
                            {"role": "user", "content": msg}
                        ],
                        "max_tokens": 800
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

def call_openrouter_free(msg: str, device_id: str):
    personality = load_personality(device_id)
    system_prompt = build_system_prompt(personality)

    models = [
        "google/gemma-2-9b-it:free",
        "meta-llama/llama-3.1-8b-instruct:free",
        "mistralai/mistral-7b-instruct:free"
    ]

    for key in OPENROUTER_KEYS:
        if not key:
            continue
        for model in models:
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

# ================= MODEL ROUTER =================
def route_model(msg: str) -> str:
    msg_lower = msg.lower()
    complex_keywords = [
        "explain", "analyze", "compare", "why", "how does",
        "difference between", "pros and cons", "write a",
        "debug", "summarize", "translate", "calculate",
        "essay", "story", "code", "program"
    ]
    if any(k in msg_lower for k in complex_keywords):
        return "complex"
    if len(msg.split()) < 8:
        return "fast"
    return "normal"

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

    route = route_model(msg)
    answer = None

    if route == "complex":
        answer = call_groq_model(msg, MODEL_COMPLEX, device_id)
    else:
        answer = call_groq_model(msg, MODEL_FAST, device_id)

    # fallback chain
    if not answer:
        answer = call_groq_model(msg, MODEL_FAST, device_id)
    if not answer:
        answer = call_openrouter_free(msg, device_id)
    if not answer:
        answer = "I could not process that right now. Please try again."

    # extract action trigger if present
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
            reply = f"Name updated to {msg}"
            return jsonify({"reply": reply})

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
        "version": "5.0",
        "groq_key_set": bool(GROQ_KEYS[0]),
        "openrouter_key_set": bool(OPENROUTER_KEYS[0])
    })

# ================= START =================
if __name__ == "__main__":
    print(f"{BOT_NAME} online")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
