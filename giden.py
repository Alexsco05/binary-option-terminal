import os
import json
import requests
import subprocess
import time
import socket
import threading

# --- CONFIGURATION ---
API_KEY = "AIzaSyCXuNKuIIKKSWHChgURgsZ9gPG-vS5KIBk"
USER_NAME = "Alexsco"

# Simplified Package List (No activities needed)
APPS = {
    "whatsapp": "com.whatsapp",
    "youtube": "com.google.android.youtube",
    "chrome": "com.android.chrome",
    "camera": "com.android.camera2",
    "facebook": "com.facebook.katana",
    "settings": "com.android.settings",
    "gmail": "com.google.android.gm",
    "maps": "com.google.android.apps.maps"
}

def gideon_vibrate(ms=300):
    os.system(f"termux-vibrate -d {ms}")

def gideon_speak(text):
    """Deep Voice Interface"""
    clean_text = str(text).replace('*', '').replace('#', '').strip()
    print(f"\n\033[1;36mGideon:\033[0m {clean_text}")
    os.system(f"termux-tts-speak -p 0.8 -r 1.1 '{clean_text}'")
    time.sleep(1)

def listen_to_user():
    """Android Voice Listener Bridge"""
    print("\033[1;33m[Listening...]\033[0m")
    try:
        result = subprocess.check_output(["termux-speech-to-text"]).decode("utf-8").strip()
        if result:
            print(f"\033[1;32mYou said:\033[0m {result}")
            return result.lower()
        return ""
    except:
        return ""

def open_app(app_name):
    """Launches apps using the most compatible method for Android 12+"""
    package = APPS.get(app_name.lower())
    if package:
        gideon_speak(f"Opening {app_name}, sir.")
        # Using 'monkey' via cmd to bypass typical permission denials
        os.system(f"cmd strategy 1") # Wakes up system
        os.system(f"monkey -p {package} -c android.intent.category.LAUNCHER 1 > /dev/null 2>&1")
    else:
        gideon_speak(f"I don't have the package for {app_name} in my database.")

def start_timer(seconds):
    """Background timer so it doesn't block the main loop"""
    def timer_thread():
        time.sleep(seconds)
        gideon_vibrate(1000)
        gideon_speak("Sir, the timer has expired.")
    
    gideon_speak(f"Timer set for {seconds} seconds.")
    threading.Thread(target=timer_thread).start()

def main():
    os.system("termux-wake-lock")
    gideon_vibrate(500)
    gideon_speak(f"Gideon is online. Hands-free protocols active for {USER_NAME}.")
    
    while True:
        msg = listen_to_user()
        if not msg: continue
            
        # 1. STOP COMMANDS
        if any(word in msg for word in ["exit", "stop", "off"]):
            gideon_speak("Standing down.")
            os.system("termux-wake-unlock")
            break
            
        # 2. OPEN APPS
        elif "open" in msg:
            app = msg.replace("open ", "").strip()
            open_app(app)
            
        # 3. SET TIMER (e.g., 'set timer for 10 seconds')
        elif "timer" in msg:
            try:
                # Extracts numbers from the voice command
                seconds = int(''.join(filter(str.isdigit, msg)))
                start_timer(seconds)
            except:
                gideon_speak("I couldn't understand the duration, sir.")

        # 4. WEB SEARCH
        elif "search" in msg or "find" in msg:
            query = msg.replace("search ", "").replace("find ", "").strip()
            gideon_speak(f"Searching for {query}.")
            os.system(f"termux-open 'https://www.google.com/search?q={query.replace(' ', '+')}'")
        
        # 5. GENERAL AI BRAIN
        else:
            gideon_speak("Processing command...")
            # Simple relay back to Gemini
            os.system(f"termux-vibrate -d 100")
            gideon_speak(f"I heard you say {msg}. Should I search that for you?")

if __name__ == "__main__":
    main()
