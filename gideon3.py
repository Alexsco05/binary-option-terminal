import os
import subprocess
import time
import json
import webbrowser
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
}

def gideon_speak(text):
    """Voice Output with Logic Processing Display"""
    print(f"\n\033[1;36mGideon:\033[0m {text}")
    subprocess.run(["termux-tts-speak", "-p", "0.8", "-r", "1.1", text])

def listen_to_user():
    """Voice Input Bridge"""
    print("\033[1;33m[Listening...]\033[0m")
    try:
        result = subprocess.check_output(["termux-speech-to-text"]).decode("utf-8").strip()
        if result:
            print(f"\033[1;32m{USER_NAME}:\033[0m {result}")
            return result.lower()
        return ""
    except Exception:
        return ""

def get_smart_greeting():
    """Logic based on current time in Lagos"""
    hour = datetime.now().hour
    if hour < 12:
        return f"Good morning, {USER_NAME}. Systems are fresh and ready."
    elif 12 <= hour < 18:
        return f"Good afternoon, {USER_NAME}. Standing by for mid-day instructions."
    else:
        return f"Good evening, {USER_NAME}. Power consumption is optimized for the night shift."

def get_status():
    """Diagnostic Report"""
    now = datetime.now().strftime("%I:%M %p")
    try:
        batt = json.loads(subprocess.check_output(["termux-battery-status"]).decode("utf-8"))
        percent = batt['percentage']
        health = "optimal" if percent > 20 else "critical"
        gideon_speak(f"It is {now}. Battery is at {percent} percent. System health is {health}.")
    except:
        gideon_speak(f"It is {now}. I am currently unable to reach the hardware sensors.")

def open_app(app_name):
    """The Working Launch Protocol"""
    link = APPS.get(app_name.lower())
    if link:
        gideon_speak(f"Initializing {app_name} protocol. Accessing now.")
        os.system(f"termux-open '{link}'")
    else:
        gideon_speak(f"Searching for {app_name} in the global database.")
        os.system(f"termux-open 'https://www.google.com/search?q={app_name}'")

def main():
    os.system("termux-wake-lock")
    # Start with a Smart Greeting
    gideon_speak(get_smart_greeting())
    
    while True:
        msg = listen_to_user()
        if not msg: continue
            
        # 1. THE STATUS CHECK
        if any(word in msg for word in ["status", "how are you", "report"]):
            get_status()

        # 2. THE APP HANDLER
        elif "open" in msg:
            app = msg.replace("open ", "").strip()
            open_app(app)

        # 3. THE TIME INQUIRY
        elif "time" in msg:
            now = datetime.now().strftime("%I:%M %p")
            gideon_speak(f"The current time is {now}, sir.")

        # 4. WEB SEARCH / KNOWLEDGE TRIGGER
        elif any(word in msg for word in ["who is", "what is", "where is", "search"]):
            query = msg.replace("search ", "").strip()
            gideon_speak(f"Accessing web archives for {query}.")
            os.system(f"termux-open 'https://www.google.com/search?q={query.replace(' ', '+')}'")

        # 5. SECURITY & SETTINGS
        elif "security" in msg or "permissions" in msg:
            gideon_speak("Opening usage access settings to verify protocols.")
            os.system("am start -a android.settings.USAGE_ACCESS_SETTINGS")
            
        # 6. SHUTDOWN
        elif any(word in msg for word in ["exit", "stop", "off", "goodbye"]):
            gideon_speak("Gideon systems standing down. Goodbye, sir.")
            os.system("termux-wake-unlock")
            break
        
        # 7. LOGIC FALLBACK (Conversational Echo)
        else:
            gideon_speak(f"I am processing your statement: '{msg}'. Would you like me to search the web for more details?")

if __name__ == "__main__":
    main()
