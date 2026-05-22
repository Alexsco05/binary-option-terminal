import os
import subprocess
import time
import requests
import json
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

# Reliable Package Names for itel P40
APP_PACKAGES = {
    "whatsapp": "com.whatsapp",
    "youtube": "com.google.android.youtube",
    "facebook": "com.facebook.katana",
    "chrome": "com.android.chrome",
    "settings": "com.android.settings",
    "gmail": "com.google.android.gm",
    "maps": "com.google.android.apps.maps"
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
            return result
        return ""
    except: return ""

def force_open_app(package_name):
    """The itel-tested launch protocol"""
    gideon_speak(f"Launching {package_name} protocol.")
    # Attempt 1: Universal URI
    if "whatsapp" in package_name:
        os.system("termux-open 'https://wa.me/'")
    else:
        # Attempt 2: Activity Manager Start
        os.system(f"am start --user 0 -n {package_name}/{package_name}.Main")
        # Attempt 3: Play Store Bridge (Forces Foreground)
        os.system(f"termux-open 'market://details?id={package_name}'")

def get_system_status():
    """Diagnostic for itel P40"""
    try:
        batt = json.loads(subprocess.check_output(["termux-battery-status"]).decode("utf-8"))
        percent = batt['percentage']
        temp = batt['temperature']
        gideon_speak(f"Sir, battery is at {percent} percent. System temperature is {temp} degrees.")
    except:
        gideon_speak("I am currently unable to access hardware sensors.")

def gideon_brain(user_input):
    global current_key_index
    
    # SYSTEM PROMPT: Define Gideon's soul and intelligence
    prompt_context = (
        f"You are {BOT_NAME}, the loyal AI partner of {USER_NAME}. "
        f"You are running on an itel P40 in Lagos. "
        "1. If the user wants to open an app/game, respond ONLY with 'ACTION: OPEN [appname]'. "
        "2. If the user asks a question, search your knowledge and give a direct, smart spoken answer. "
        "3. Do NOT provide links. Be helpful, concise, and recognize the user as {USER_NAME}."
    )

    for _ in range(len(API_KEYS)):
        active_key = API_KEYS[current_key_index]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={active_key}"
        payload = {"contents": [{"parts": [{"text": f"{prompt_context}\nUser: {user_input}"}]}]}

        try:
            response = requests.post(url, json=payload, timeout=15)
            if response.status_code in [429, 403]:
                current_key_index = (current_key_index + 1) % len(API_KEYS)
                continue
            
            data = response.json()
            answer = data['candidates'][0]['content']['parts'][0]['text'].strip()

            if "ACTION: OPEN" in answer.upper():
                app_name = answer.split()[-1].lower().strip("[]")
                package = APP_PACKAGES.get(app_name)
                if package:
                    force_open_app(package)
                else:
                    gideon_speak(f"I don't have the package for {app_name}, opening system search.")
                    os.system(f"termux-open 'https://www.google.com/search?q={app_name}'")
            else:
                gideon_speak(answer)
            return 
        except Exception:
            time.sleep(1)

def main():
    os.system("termux-wake-lock")
    # Personalized morning/night greeting
    hour = datetime.now().hour
    time_greet = "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening"
    gideon_speak(f"{time_greet}, {USER_NAME}. Gideon is fully synchronized with your itel hardware. How shall we begin?")
    
    while True:
        msg = listen_to_user()
        if not msg: continue
        
        # Shutdown
        if any(word in msg.lower() for word in ["shutdown", "offline", "go to sleep"]):
            gideon_speak(f"Powering down. Stay safe, {USER_NAME}.")
            os.system("termux-wake-unlock")
            break
        
        # Manual status check
        if "status" in msg.lower() or "battery" in msg.lower():
            get_system_status()
            continue
            
        # All other logic handled by AI
        gideon_brain(msg)

if __name__ == "__main__":
    main()
