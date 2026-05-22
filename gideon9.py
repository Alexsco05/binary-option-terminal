import os
import subprocess
import re
import time
import json

# --- CONFIGURATION ---
USER_NAME = "Alexsco"
SECRET_PHRASE = "execute protocol"
WA_LINK = "whatsapp://send?phone=2348158051683"
MOVIE_LINK = "https://moviebox.ng/" 

# APP LIBRARY
APPS = {
    "whatsapp": WA_LINK,
    "business": WA_LINK,
    "tiktok": "https://www.tiktok.com/",
    "settings": "am start -a android.settings.SETTINGS",
    "gallery": "am start -a android.intent.action.VIEW -t image/*",
    "ai gallery": "am start -n com.gallery20/.MainActivity",
    "youtube": "vnd.youtube://",
    "facebook": "fb://feed",
    "chrome": "googlechrome://",
    "audiomack": "audiomack://",
    "moviebox": MOVIE_LINK,
    "opay": "opay://",
    "palmpay": "palmpay://",
    "phone": "tel:",
    "messages": "sms:"
}

def gideon_speak(text, stream="MUSIC"):
    print(f"\n\033[1;36mGideon:\033[0m {text}")
    os.system(f"termux-volume {stream.lower()} 15")
    # Increased rate (-r 1.2) for faster response feel
    subprocess.run(["termux-tts-speak", "-p", "0.9", "-r", "1.2", "-s", stream, text])

def get_time_greeting():
    hour = int(time.strftime("%H"))
    if hour < 12: return "Good morning"
    elif 12 <= hour < 18: return "Good afternoon"
    else: return "Good evening"

def get_battery_status():
    try:
        output = subprocess.check_output(["termux-battery-status"], timeout=2).decode("utf-8")
        data = json.loads(output)
        percent = data.get("percentage")
        return percent, f"Battery is at {percent} percent."
    except:
        return 0, "Battery diagnostic unavailable."

def listen_to_user():
    print("\033[1;33m[Listening...]\033[0m")
    try:
        result = subprocess.check_output(["termux-speech-to-text"]).decode("utf-8").strip()
        if result:
            print(f"\033[1;32m{USER_NAME}:\033[0m {result}")
            return result.lower()
        return ""
    except: return ""

def handle_commands(msg, start_batt):
    # 1. STOP COMMAND
    if any(word in msg for word in ["stop", "shutdown", "exit", "offline"]):
        end_batt, _ = get_battery_status()
        gideon_speak(f"Shutting down. Final battery level is {end_batt} percent. Goodbye, {USER_NAME}.")
        os.system("termux-wake-unlock")
        exit()

    # 2. IDENTITY COMMAND
    if any(word in msg for word in ["identify", "who are you", "identity"]):
        gideon_speak(f"I am Gideon, an advanced AI interface developed for {USER_NAME}.")
        gideon_speak("My core functions include system automation, communication management, and media retrieval.")
        gideon_speak("I am currently operating on the itel P40 mobile platform.")
        return True

    # 3. BATTERY CHECK
    if "battery" in msg:
        _, info = get_battery_status()
        gideon_speak(info)
        return True

    # 4. FIND DEVICE
    if any(word in msg for word in ["find my device", "where are you"]):
        os.system("termux-vibrate -d 800")
        gideon_speak(f"I am here, {USER_NAME}!", stream="ALARM")
        return True

    # 5. MOVIE SEARCH
    if "search movie" in msg:
        query = msg.replace("search movie", "").strip()
        gideon_speak(f"Searching MovieBox for {query}.")
        os.system(f"termux-open 'https://moviebox.ng/search/{query}'")
        return True

    return False

def open_app(msg):
    for name, target in APPS.items():
        if name in msg:
            gideon_speak(f"Opening {name}.")
            if target.startswith("am start"): os.system(target)
            else: os.system(f"termux-open '{target}'")
            return
    
    target = msg.replace("open", "").strip()
    gideon_speak(f"Searching web for {target}.")
    os.system(f"termux-open 'https://www.google.com/search?q={target}'")

def main():
    os.system("termux-wake-lock")
    
    # --- STARTUP SEQUENCE ---
    start_batt, battery_info = get_battery_status()
    greeting = get_time_greeting()
    current_time = time.strftime("%I:%M %p")
    
    gideon_speak(f"{greeting}, {USER_NAME}. I am Gideon.")
    gideon_speak(f"The time is {current_time}. {battery_info}")
    gideon_speak("System is locked. Awaiting activation phrase.")

    # --- LOCKDOWN ---
    unlocked = False
    while not unlocked:
        msg = listen_to_user()
        if SECRET_PHRASE in msg:
            gideon_speak("Identity confirmed. Protocols unlocked. Ready for command.")
            unlocked = True
        elif any(word in msg for word in ["stop", "shutdown"]):
            os.system("termux-wake-unlock")
            exit()
        elif msg != "":
            gideon_speak("Access denied.")

    # --- MAIN LOOP ---
    while True:
        msg = listen_to_user()
        if not msg: continue
        
        if not handle_commands(msg, start_batt):
            if "open" in msg or "launch" in msg:
                open_app(msg)
            elif "search" in msg:
                query = msg.replace("search ", "").strip()
                gideon_speak(f"Searching for {query}.")
                os.system(f"termux-open 'https://www.google.com/search?q={query}'")

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: os.system("termux-wake-unlock")
