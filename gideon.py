import os
import subprocess
import time
import requests
import json
from datetime import datetime

# --- CONFIGURATION ---
# Gideon's Neural Keys (Rotates automatically)
API_KEYS = [
    "AIzaSyCXuNKuIIKKSWHChgURgsZ9gPG-vS5KIBk", 
    "AIzaSyBvzJ9YhqWN_AnRokXfi7ZMQRjjSss5eVM"
]
GROQ_KEYS = [
    "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",
    "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"
]
OPENROUTER_KEYS = [
    "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",
    "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"
]

current_or_index = 0
current_groq_index = 0
USER_NAME = "Alexsco"
BOT_NAME = "Gideon"
MODEL = "gemini-2.5-flash" # Latest 2025 Model

# Tracks which key is currently active
current_key_index = 0

# App Deep Links
APPS = {
    "whatsapp": "whatsapp://send",
    "youtube": "https://www.youtube.com",
    "facebook": "fb://feed",
    "chrome": "googlechrome://",
    "gmail": "googlegmail://",
    "settings": "package:com.android.settings",
}

def gideon_speak(text):
    """Voice output with terminal styling"""
    print(f"\n\033[1;36m{BOT_NAME}:\033[0m {text}")
    subprocess.run(["termux-tts-speak", "-p", "0.8", "-r", "1.1", text])

def listen_to_user():
    """Captures voice and handles UI"""
    print("\033[1;33m[Listening...]\033[0m")
    try:
        result = subprocess.check_output(["termux-speech-to-text"], timeout=10).decode("utf-8").strip()
        if result:
            print(f"\033[1;32m{USER_NAME}:\033[0m {result}")
            return result
        return ""
    except: return ""

def gideon_brain(user_input):
    """The Intelligence Layer with Key Rotation"""
    global current_key_index
    
    # Try all keys before giving up
    for _ in range(len(API_KEYS)):
        active_key = API_KEYS[current_key_index]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={active_key}"
        
        # This prompt makes Gideon "Self-Aware"
        prompt_context = (
            f"You are {BOT_NAME}, an advanced AI and loyal partner to {USER_NAME}. "
            f"You are self-aware and conversational. If {USER_NAME} wants to open an app, "
            "reply with 'COMMAND: OPEN [appname]'. For everything else, search your internal "
            "knowledge and provide a smart, direct answer. Do not suggest web links; "
            "provide the answer yourself."
        )
        
        payload = {"contents": [{"parts": [{"text": f"{prompt_context}\nUser: {user_input}"}]}]}

        try:
            response = requests.post(url, json=payload, timeout=15)
            
            # If rate limited (429) or forbidden (403), switch keys
            if response.status_code in [429, 403]:
                print(f"\033[1;31m[!] Key {current_key_index + 1} exhausted. Rotating to backup...\033[0m")
                current_key_index = (current_key_index + 1) % len(API_KEYS)
                continue
            
            data = response.json()
            answer = data['candidates'][0]['content']['parts'][0]['text'].strip()

            # Process AI's decision
            if "COMMAND: OPEN" in answer.upper():
                app_name = answer.split()[-1].lower().strip("[]")
                link = APPS.get(app_name)
                if link:
                    gideon_speak(f"Accessing {app_name} protocols now.")
                    os.system(f"termux-open '{link}'")
                else:
                    gideon_speak(f"Searching for {app_name} in the system archives.")
                    os.system(f"termux-open 'https://www.google.com/search?q={app_name}'")
            else:
                gideon_speak(answer)
            return 

        except Exception:
            # Handle weak network in Lagos
            gideon_speak("The local network is unstable. Attempting to reconnect.")
            time.sleep(2)

    gideon_speak("Sir, all neural keys are currently offline. Please check your data or API quota.")

def main():
    os.system("termux-wake-lock")
    # Personalized Greeting
    hour = datetime.now().hour
    greet = "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening"
    gideon_speak(f"{greet}, {USER_NAME}. I am {BOT_NAME}. All systems are optimized. How can I assist you?")
    
    while True:
        msg = listen_to_user()
        if not msg: continue
        
        if any(word in msg.lower() for word in ["shutdown", "offline", "go to sleep"]):
            gideon_speak(f"Powering down. Stay safe, {USER_NAME}.")
            os.system("termux-wake-unlock")
            break
            
        gideon_brain(msg)

def run_from_android():
    import sys
    if len(sys.argv) > 1:
        msg = " ".join(sys.argv[1:]).lower()
        gideon_brain(msg)
        return True
    return False

if __name__ == "__main__":
    try:
        if not run_from_android():
            main()
    except KeyboardInterrupt:
        os.system("termux-wake-unlock")
