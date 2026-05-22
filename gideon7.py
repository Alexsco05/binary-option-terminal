import os
import subprocess
import re

# --- CONFIGURATION ---
USER_NAME = "Alexsco"

# THE THREE APPS WE FIXED
# WhatsApps use the International Format link that finally worked
WA_LINK = "https://api.whatsapp.com/send?phone=2348158051683"
# TikTok uses a standard direct web link
TIKTOK_LINK = "https://www.tiktok.com/"

# RESTORED APP LIBRARY (Original working links for everything else)
APPS = {
    "whatsapp": WA_LINK,
    "business": WA_LINK,
    "tiktok": TIKTOK_LINK,
    "youtube": "vnd.youtube://",
    "facebook": "fb://feed",
    "chrome": "googlechrome://",
    "settings": "package:com.android.settings",
    "phone": "tel:",
    "messages": "sms:",
    "audiomack": "audiomack://",
    "gallery": "content://media/external/images/media",
    "ai gallery": "com.gallery20", 
    "moviebox": "com.enjoy.moviebox",
    "opay": "opay://",
    "palmpay": "palmpay://"
}

def gideon_speak(text):
    print(f"\n\033[1;36mGideon:\033[0m {text}")
    subprocess.run(["termux-tts-speak", "-p", "0.8", "-r", "1.1", text])

def listen_to_user():
    print("\033[1;33m[Listening...]\033[0m")
    try:
        result = subprocess.check_output(["termux-speech-to-text"]).decode("utf-8").strip()
        if result:
            print(f"\033[1;32m{USER_NAME}:\033[0m {result}")
            return result.lower()
        return ""
    except: return ""

def handle_comms(msg):
    # SIMPLE CALL: "call 081..."
    if "call" in msg:
        number = re.sub(r"\D", "", msg)
        if number:
            gideon_speak(f"Calling {number} now.")
            os.system(f"termux-telephony-call {number}")
            return True
    # SIMPLE SMS: "message 081... hello"
    if "message" in msg or "sms" in msg:
        parts = msg.split(" ", 2)
        if len(parts) >= 3:
            number = re.sub(r"\D", "", parts[1])
            text = parts[2]
            gideon_speak(f"Sending message to {number}.")
            os.system(f"termux-sms-send -n {number} '{text}'")
            return True
    return False

def open_app(msg):
    for name, target in APPS.items():
        if name in msg:
            gideon_speak(f"Opening {name}, Alexsco.")
            # For Gallery/Moviebox/Settings, we use the simple launcher
            if "." in target and "://" not in target:
                 os.system(f"monkey -p {target} -c android.intent.category.LAUNCHER 1")
            else:
                os.system(f"termux-open '{target}'")
            return
    
    # If not in list, search web
    target = msg.replace("open", "").strip()
    gideon_speak(f"Searching for {target}.")
    os.system(f"termux-open 'https://www.google.com/search?q={target}'")

def main():
    os.system("termux-wake-lock")
    gideon_speak(f"Settings restored. Only the requested three are changed, {USER_NAME}.")
    while True:
        msg = listen_to_user()
        if not msg: continue
        if any(word in msg for word in ["shutdown", "offline", "stop"]):
            gideon_speak("Offline. See you later.")
            os.system("termux-wake-unlock")
            break
        if handle_comms(msg): continue
        if "open" in msg or "launch" in msg:
            open_app(msg)
        elif "search" in msg:
            query = msg.replace("search ", "").strip()
            gideon_speak(f"Searching {query}.")
            os.system(f"termux-open 'https://www.google.com/search?q={query}'")

if __name__ == "__main__":
    main()
