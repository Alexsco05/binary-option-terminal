import os
import subprocess
import re
import time
import json

# --- CONFIGURATION ---
USER_NAME = "Alexsco"
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
    subprocess.run(["termux-tts-speak", "-p", "0.8", "-r", "1.1", "-s", stream, text])

def get_battery_status():
    try:
        output = subprocess.check_output(["termux-battery-status"]).decode("utf-8")
        data = json.loads(output)
        percent = data.get("percentage")
        status = data.get("status")
        return f"Battery is currently at {percent} percent and {status}."
    except:
        return "Battery diagnostic unavailable."

def listen_to_user():
    print("\033[1;33m[Listening...]\033[0m")
    try:
        result = subprocess.check_output(["termux-speech-to-text"]).decode("utf-8").strip()
        if result:
            print(f"\033[1;32m{USER_NAME}:\033[0m {result}")
            return result.lower()
        return ""
    except: return ""

def find_my_device():
    print("\033[1;31m[FIND DEVICE ACTIVE]\033[0m")
    for _ in range(3):
        os.system("termux-vibrate -d 800")
        gideon_speak(f"I am right here, {USER_NAME}! Follow the sound of my voice!", stream="ALARM")
        time.sleep(0.5)

def handle_commands(msg):
    if any(word in msg for word in ["stop", "shutdown", "exit", "offline"]):
        gideon_speak("Understood. Gideon going offline. Stay safe in Lagos, Alexsco.")
        os.system("termux-wake-unlock")
        exit()

    if "battery" in msg:
        gideon_speak(get_battery_status())
        return True

    if "search movie" in msg:
        query = msg.replace("search movie", "").strip()
        gideon_speak(f"Searching MovieBox for {query}.")
        os.system(f"termux-open 'https://moviebox.ng/search/{query}'")
        return True

    if any(word in msg for word in ["find my device", "where are you", "find my phone"]):
        find_my_device()
        return True

    if "call" in msg:
        num = re.sub(r"\D", "", msg)
        if num:
            gideon_speak(f"Dialing {num}.")
            os.system(f"termux-telephony-call {num}")
            return True
    
    if "message" in msg or "sms" in msg:
        match = re.search(r'(?:message|sms)\s+(\d+)\s+(.+)', msg)
        if match:
            num, body = match.group(1), match.group(2)
            gideon_speak(f"Sending message to {num}.")
            os.system(f"termux-sms-send -n {num} '{body}'")
            return True
    return False

def open_app(msg):
    for name, target in APPS.items():
        if name in msg:
            gideon_speak(f"Opening {name}.")
            if target.startswith("am start"):
                os.system(target)
            else:
                os.system(f"termux-open '{target}'")
            return
    
    target = msg.replace("open", "").strip()
    gideon_speak(f"Direct link not found. Searching web for {target}.")
    os.system(f"termux-open 'https://www.google.com/search?q={target}'")

def main():
    os.system("termux-wake-lock")
    
    # --- NEW GREETING & INTRODUCTION ---
    battery_info = get_battery_status()
    current_time = time.strftime("%I:%M %p")
    
    gideon_speak(f"Good day, {USER_NAME}. I am Gideon, your personal AI assistant.")
    gideon_speak(f"The time is {current_time}. {battery_info}")
    gideon_speak("All system protocols are initialized and I am ready for your command.")
    
    while True:
        msg = listen_to_user()
        if not msg: continue
        
        if not handle_commands(msg):
            if "open" in msg or "launch" in msg:
                open_app(msg)
            elif "search" in msg:
                query = msg.replace("search ", "").strip()
                gideon_speak(f"Searching for {query}.")
                os.system(f"termux-open 'https://www.google.com/search?q={query}'")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        os.system("termux-wake-unlock")
