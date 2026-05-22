import os
import subprocess
import time
import requests
import json
from datetime import datetime

# ---------------- CONFIGURATION ----------------

USER_NAME = "Alexsco"
BOT_NAME = "Gideon"

MODEL_GEMINI = "gemini-2.5-flash"

API_KEYS = [
    "YOUR_GEMINI_KEY_1",
    "YOUR_GEMINI_KEY_2"
]

GROQ_KEYS = [
    "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",
    "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"
]

OPENROUTER_KEYS = [
    "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",
    "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"
]

current_gemini_index = 0
current_groq_index = 0
current_or_index = 0

APPS = {
    "whatsapp": "whatsapp://send",
    "youtube": "https://www.youtube.com",
    "facebook": "fb://feed",
    "chrome": "googlechrome://",
    "gmail": "googlegmail://",
    "settings": "android.settings.SETTINGS"
}

# ---------------- CORE UTILITIES ----------------

def speak(text):
    print(f"\n\033[1;36m{BOT_NAME}:\033[0m {text}")
    subprocess.run(["termux-tts-speak", text])


def listen():
    print("\033[1;33m[Listening...]\033[0m")
    try:
        result = subprocess.check_output(
            ["termux-speech-to-text"],
            timeout=10
        ).decode().strip()

        if result:
            print(f"\033[1;32m{USER_NAME}:\033[0m {result}")
            return result
        return ""
    except:
        return ""


# ---------------- MODEL CALLERS ----------------

def ask_gemini(prompt):
    global current_gemini_index

    for _ in range(len(API_KEYS)):
        key = API_KEYS[current_gemini_index]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_GEMINI}:generateContent?key={key}"

        payload = {
            "contents": [
                {"parts": [{"text": prompt}]}
            ]
        }

        try:
            r = requests.post(url, json=payload, timeout=15)

            if r.status_code in [403, 429]:
                current_gemini_index = (current_gemini_index + 1) % len(API_KEYS)
                continue

            data = r.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]

        except:
            time.sleep(1)

    return None


def ask_groq(prompt):
    global current_groq_index

    for _ in range(len(GROQ_KEYS)):
        key = GROQ_KEYS[current_groq_index]
        url = "https://api.groq.com/openai/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "llama-3.1-8b-instant",
            "messages": [{"role": "user", "content": prompt}]
        }

        try:
            r = requests.post(url, headers=headers, json=payload, timeout=15)

            if r.status_code in [429, 403]:
                current_groq_index = (current_groq_index + 1) % len(GROQ_KEYS)
                continue

            return r.json()["choices"][0]["message"]["content"]

        except:
            time.sleep(1)

    return None


def ask_openrouter(prompt):
    global current_or_index

    for _ in range(len(OPENROUTER_KEYS)):
        key = OPENROUTER_KEYS[current_or_index]
        url = "https://openrouter.ai/api/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://gideon.local",
            "X-Title": "Gideon AI"
        }

        payload = {
            "model": "anthropic/claude-3-haiku",
            "messages": [{"role": "user", "content": prompt}]
        }

        try:
            r = requests.post(url, headers=headers, json=payload, timeout=15)

            if r.status_code in [429, 403]:
                current_or_index = (current_or_index + 1) % len(OPENROUTER_KEYS)
                continue

            return r.json()["choices"][0]["message"]["content"]

        except:
            time.sleep(1)

    return None


# ---------------- INTELLIGENCE ROUTER ----------------

def gideon_brain(user_input):

    system_prompt = (
        f"You are {BOT_NAME}, an advanced assistant for {USER_NAME}. "
        "If the user requests an app, respond ONLY like: COMMAND: OPEN [appname]. "
        "Otherwise respond normally and clearly."
    )

    prompt = f"{system_prompt}\nUser: {user_input}"

    # 1. Groq (fast brain)
    response = ask_groq(prompt)
    if response:
        return process_response(response)

    # 2. OpenRouter (reasoning fallback)
    response = ask_openrouter(prompt)
    if response:
        return process_response(response)

    # 3. Gemini (backup brain)
    response = ask_gemini(prompt)
    if response:
        return process_response(response)

    speak("All systems are currently unavailable.")
    return


# ---------------- RESPONSE HANDLER ----------------

def process_response(answer):

    upper = answer.upper()

    if "COMMAND: OPEN" in upper:
        app = answer.split()[-1].lower().strip("[]")

        if app in APPS:
            speak(f"Opening {app}.")
            os.system(f"termux-open '{APPS[app]}'")
        else:
            speak(f"Searching for {app}.")
            os.system(f"termux-open 'https://www.google.com/search?q={app}'")
    else:
        speak(answer)


# ---------------- MAIN LOOP ----------------

def main():
    os.system("termux-wake-lock")

    hour = datetime.now().hour
    greeting = (
        "Good morning" if hour < 12 else
        "Good afternoon" if hour < 18 else
        "Good evening"
    )

    speak(f"{greeting}, {USER_NAME}. Gideon is active.")

    while True:
        msg = listen()
        if not msg:
            continue

        if any(word in msg.lower() for word in ["shutdown", "sleep", "offline"]):
            speak("Shutting down systems.")
            os.system("termux-wake-unlock")
            break

        gideon_brain(msg)


def run_cli():
    import sys
    if len(sys.argv) > 1:
        gideon_brain(" ".join(sys.argv[1:]))
        return True
    return False


if __name__ == "__main__":
    try:
        if not run_cli():
            main()
    except KeyboardInterrupt:
        os.system("termux-wake-unlock")
