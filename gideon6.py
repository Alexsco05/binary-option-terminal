import os
import subprocess
import time

# --- CONFIGURATION ---
USER_NAME = "Alexsco"

# VERIFIED LINKS (Lagos + International Format)
WA_LINK = "https://api.whatsapp.com/send?phone=2348158051683"
# Business link using the same verified domain
WAB_LINK = "https://api.whatsapp.com/send?phone=2348158051683"

# APP LIBRARY
APPS = {
    "whatsapp": WA_LINK,
    "business": WAB_LINK,
    "youtube": "vnd.youtube://",
    "facebook": "fb://feed",
    "chrome": "googlechrome://",
    "gmail": "googlegmail://",
    "settings": "package:com.android.settings",
    # TikTok Direct Intent - Bypasses Browser entirely
    "tiktok": "intent:#Intent;package=com.zhiliaoapp.musically;action=android.intent.action.MAIN;category=android.intent.category.LAUNCHER;end",
    "opay": "team.opay.pay",
    "palmpay": "com.transsnet.palmpay"
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
    except Exception:
        return ""

def open_app(msg):
    found = False
    for name, target in APPS.items():
        if name in msg:
            gideon_speak(f"Opening {name}, sir.")
            
            # Use 'monkey' for banking/settings, 'termux-open' for the Rest
            if name in ["opay", "palmpay", "settings"]:
                 os.system(f"monkey -p {target} -c android.intent.category.LAUNCHER 1")
            else:
                # This opens the WA links and TikTok Direct Intent
                os.system(f"termux-open '{target}'")
            
            found = True
            break
    
    if not found:
        target = msg.replace("open", "").strip()
        gideon_speak(f"Searching web for {target}.")
        os.system(f"termux-open 'https://www.google.com/search?q={target}'")

def main():
    os.system("termux-wake-lock")
    gideon_speak(f"Gideon is fully optimized. Both WhatsApps and TikTok are ready, {USER_NAME}.")
    
    while True:
        msg = listen_to_user()
        if not msg: continue
            
        if any(word in msg for word in ["shutdown", "offline", "stop"]):
            gideon_speak("Powering down. Stay safe.")
            os.system("termux-wake-unlock")
            break
            
        elif "open" in msg or "launch" in msg:
            open_app(msg)
            
        elif "search" in msg:
            query = msg.replace("search ", "").strip()
            gideon_speak(f"Searching for {query}.")
            os.system(f"termux-open 'https://www.google.com/search?q={query}'")

if __name__ == "__main__":
    main()
