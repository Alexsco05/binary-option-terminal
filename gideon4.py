import os
import subprocess
import time
import requests
from datetime import datetime

# --- CONFIGURATION ---
API_KEYS = [
    "AIzaSyCXuNKuIIKKSWHChgURgsZ9gPG-vS5KIBk", 
    "AIzaSyBvzJ9YhqWN_AnRokXfi7ZMQRjjSss5eVM"
]

USER_NAME = "Alexsco"
BOT_NAME = "Gideon"
MODEL = "gemini-2.5-flash"
current_key_index = 0

# Package names for itel P40
APP_PACKAGES = {
    "whatsapp": "com.whatsapp",
    "youtube": "com.google.android.youtube",
    "facebook": "com.facebook.katana",
    "chrome": "com.android.chrome",
    "settings": "com.android.settings",
    "gmail": "com.google.android.gm"
}

def gideon_speak(text):
    print(f"\n\033[1;36m{BOT_NAME}:\033[0m {text}")
    subprocess.run(["termux-tts-speak", "-p", "0.8", "-r", "1.1", text])

def listen_to_user():
    print("\033[1;33m[Listening...]\033[0m")
    try:
        result = subprocess.check_output(["termux-speech-to-text"], timeout=12).decode("utf-8").strip()
        if result:
            print(f"\033[1;32m{USER_NAME}:\033[0m {result}")
            return result.lower()
        return ""
    except: return ""

def force_open_app(package_name):
    """Uses Activity Manager to launch the app package directly"""
    gideon_speak(f"Accessing {package_name} internals...")
    # 'am start' is the standard Android command to launch a package
    # We use 'termux-open' as a fallback because it handles intent resolving
    os.system(f"termux-open --view 'market://details?id={package_name}'") 
    # The line above opens the store/app page which forces the OS to recognize the app
    # Alternatively, we try to trigger the MAIN intent:
    os.system(f"am start --user 0 -n {package_name}/{package_name}.Main")
    # If the above fails, we use the simple URI bridge
    os.system(f"termux-open-url 'https://wa.me/'") if "whatsapp" in package_name else None

def gideon_brain(user_input):
    global current_key_index
    
    # Direct trigger for WhatsApp
    if "whatsapp" in user_input:
        force_open_app(APP_PACKAGES["whatsapp"])
        return

    for _ in range(len(API_KEYS)):
        active_key = API_KEYS[current_key_index]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={active_key}"
        prompt_context = f"You are {BOT_NAME}, an AI for {USER_NAME}. If he wants an app, say 'OPEN [appname]'. Otherwise answer yourself."
        payload = {"contents": [{"parts": [{"text": f"{prompt_context}\nUser: {user_input}"}]}]}

        try:
            response = requests.post(url, json=payload, timeout=15)
            if response.status_code in [429, 403]:
                current_key_index = (current_key_index + 1) % len(API_KEYS)
                continue
            
            data = response.json()
            answer = data['candidates'][0]['content']['parts'][0]['text'].strip()

            if "OPEN" in answer.upper():
                app_name = answer.split()[-1].lower().strip("[]")
                package = APP_PACKAGES.get(app_name)
                if package:
                    force_open_app(package)
                else:
                    gideon_speak(f"Searching for {app_name}.")
                    os.system(f"termux-open 'https://www.google.com/search?q={app_name}'")
            else:
                gideon_speak(answer)
            return 
        except Exception:
            time.sleep(1)

def main():
    os.system("termux-wake-lock")
    gideon_speak(f"Systems stabilized. I am ready, {USER_NAME}.")
    while True:
        msg = listen_to_user()
        if not msg: continue
        if any(word in msg for word in ["shutdown", "offline", "goodbye"]):
            gideon_speak("Powering down. Goodbye.")
            os.system("termux-wake-unlock")
            break
        gideon_brain(msg)

if __name__ == "__main__":
    main()
