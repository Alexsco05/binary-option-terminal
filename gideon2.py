import os
import subprocess
import time
import json
from datetime import datetime

# --- CONFIGURATION ---
USER_NAME = "Alexsco"

# Working Deep Links
APPS = {
    "whatsapp": "whatsapp://send",
    "youtube": "https://www.youtube.com",
    "facebook": "fb://facewebmodal/f?href=https://www.facebook.com",
    "chrome": "googlechrome://",
    "gmail": "googlegmail://",
    "settings": "package:com.android.settings",
    "playstore": "market://details?id=com.termux"
}

def gideon_speak(text):
    """Voice Output"""
    print(f"\n\033[1;36mGideon:\033[0m {text}")
    subprocess.run(["termux-tts-speak", "-p", "0.8", "-r", "1.1", text])
    time.sleep(0.2)

def listen_to_user():
    """Voice Input"""
    print("\033[1;33m[Listening...]\033[0m")
    try:
        result = subprocess.check_output(["termux-speech-to-text"]).decode("utf-8").strip()
        if result:
            print(f"\033[1;32mYou said:\033[0m {result}")
            return result.lower()
        return ""
    except Exception:
        return ""

def get_status():
    """System Health Check"""
    now = datetime.now().strftime("%I:%M %p")
    try:
        batt = json.loads(subprocess.check_output(["termux-battery-status"]).decode("utf-8"))
        percent = batt['percentage']
        gideon_speak(f"Sir, it is {now}. Battery is at {percent} percent.")
    except:
        gideon_speak(f"Time is {now}. Battery sensors are restricted.")

def open_app(app_name):
    """The Working Launch Protocol"""
    link = APPS.get(app_name.lower())
    if link:
        gideon_speak(f"Initializing {app_name}, sir.")
        os.system(f"termux-open '{link}'")
    else:
        gideon_speak(f"Searching Google for {app_name}.")
        os.system(f"termux-open 'https://www.google.com/search?q={app_name}'")

def main():
    os.system("termux-wake-lock")
    gideon_speak(f"Gideon systems online. Standing by for {USER_NAME}.")
    
    while True:
        msg = listen_to_user()
        if not msg: continue
            
        # 1. STATUS REPORT
        if "status" in msg or "report" in msg:
            get_status()

        # 2. APP CONTROL
        elif "open" in msg:
            app = msg.replace("open ", "").strip()
            open_app(app)
            
        # 3. SECURITY BYPASS (Opens special permission page)
        elif "security" in msg or "permissions" in msg:
            gideon_speak("Opening special access settings. Ensure Termux is allowed, sir.")
            os.system("am start -a android.settings.USAGE_ACCESS_SETTINGS")

        # 4. SEARCH
        elif "search" in msg:
            query = msg.replace("search ", "").strip()
            gideon_speak(f"Finding {query}.")
            os.system(f"termux-open 'https://www.google.com/search?q={query}'")
            
        # 5. SHUTDOWN
        elif any(word in msg for word in ["exit", "stop", "off"]):
            gideon_speak("Powering down. Goodbye.")
            os.system("termux-wake-unlock")
            break
        
        else:
            gideon_speak(f"Standing by on: {msg}")

if __name__ == "__main__":
    main()
