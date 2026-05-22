import os
import subprocess
import re
import time
import json
import sys
import shutil

# --- CONFIGURATION & IDENTITY ---
CREATOR_NAME = "Alexander"
USER_DISPLAY = "Alexsco"
SECRET_PHRASE = "execute protocol"
WA_LINK = "whatsapp://send"
WA_BIZ_LINK = "whatsapp://send" 
MOVIE_LINK = "https://moviebox.ng/" 
VOICE_MALE = "en-us-x-sfg#male_1-local" 

# COLORS
C, B, W, R, G, X = '\033[1;36m', '\033[1;34m', '\033[1;37m', '\033[1;31m', '\033[1;32m', '\033[0m'

# APP LIBRARY
APPS = {
    "whatsapp": WA_LINK,
    "business": WA_BIZ_LINK,
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

def draw_mega_core(duration, theme_color=C):
    cols, rows = shutil.get_terminal_size()
    v_padding = max(0, (rows // 2) - 3)
    frames = [
        [f"      {W}---{X}      ", f"    {B}/  {theme_color}●{B}  \\{X}    ", f"      {W}---{X}      "],
        [f"     {theme_color}-------{X}     ", f"   {B}((  {W}●{B}  )){X}   ", f"     {theme_color}-------{X}     "],
        [f"    {W}--------{X}    ", f"  {theme_color}(((  {W}●{theme_color}  ))){X}  ", f"    {W}--------{X}    "]
    ]
    end_time = time.time() + duration
    idx = 0
    while time.time() < end_time:
        frame = frames[idx % len(frames)]
        sys.stdout.write("\033[H" + "\n" * v_padding)
        for line in frame:
            h_padding = max(0, (cols - len(re.sub(r'\033\[[0-9;]*m', '', line))) // 2)
            sys.stdout.write(" " * h_padding + line + "\n")
        sys.stdout.flush()
        time.sleep(0.15)
        idx += 1
    sys.stdout.write("\033[H" + ("\n" * rows))

def gideon_speak(text, theme=C, stream="MUSIC"):
    print(f"\n{C}Gideon:{X} {text}")
    os.system(f"termux-volume {stream.lower()} 15")
    subprocess.Popen(["termux-tts-speak", "-n", VOICE_MALE, "-p", "0.9", "-r", "1.1", "-s", stream, text])
    duration = len(text) / 10 + 1.2
    draw_mega_core(duration, theme_color=theme)

def get_battery_status():
    try:
        output = subprocess.check_output(["termux-battery-status"], timeout=2).decode("utf-8")
        data = json.loads(output)
        return data.get("percentage"), data.get("status")
    except: return 0, "Unknown"

def get_weather():
    try:
        res = subprocess.check_output(["curl", "-s", "wttr.in/Lagos?format=1"], timeout=5).decode("utf-8")
        return f"Current weather in Lagos: {res}"
    except: return "Weather data is currently unavailable."

def wiki_search(query):
    try:
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{query.replace(' ', '_')}"
        res = subprocess.check_output(["curl", "-s", url]).decode("utf-8")
        data = json.loads(res)
        return data.get("extract", "No information found.")
    except: return "I cannot reach the intelligence database right now."

def capture_photo():
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    save_path = os.path.expanduser(f"~/cap_{timestamp}.jpg")
    os.system(f"termux-camera-photo -c 1 {save_path}")

def listen_to_user():
    print(f"\n{G}[Gideon is listening...]{X}")
    try:
        return subprocess.check_output(["termux-speech-to-text"]).decode("utf-8").strip().lower()
    except: return ""

def handle_commands(msg, start_batt):
    # 1. SYSTEM CONTROL
    if "lock phone" in msg or "lock system" in msg:
        gideon_speak("Acknowledged. Locking system."); os.system("termux-lock"); return True

    if "lumos" in msg or "flashlight on" in msg:
        os.system("termux-torch on"); gideon_speak("Flashlight activated."); return True
    if "nox" in msg or "flashlight off" in msg:
        os.system("termux-torch off"); gideon_speak("Flashlight deactivated."); return True

    # 2. PICTURES
    if "show picture" in msg or "show pictures" in msg:
        gideon_speak("Opening capture logs."); os.system("termux-open ~"); return True
    if "backup picture" in msg:
        gideon_speak("Synchronizing pictures to gallery."); os.system("mv ~/cap_*.jpg /sdcard/DCIM/ 2>/dev/null"); return True
    if "clear picture" in msg:
        gideon_speak("Wiping picture logs."); os.system("rm ~/cap_*.jpg"); return True

    # 3. INFORMATION
    if "weather" in msg:
        gideon_speak(get_weather()); return True
    if "battery" in msg:
        p, s = get_battery_status(); gideon_speak(f"Battery is at {p} percent."); return True
    if any(x in msg for x in ["who is", "what is", "tell me about"]):
        q = msg.replace("who is","").replace("what is","").replace("tell me about","").strip()
        gideon_speak(wiki_search(q)); return True

    # 4. IDENTITY (Specific creator reference only here)
    if "identity" in msg or "who are you" in msg:
        gideon_speak(f"I am Gideon, a male AI system created by {CREATOR_NAME}. My protocols are initialized for {USER_DISPLAY}.")
        return True

    # 5. APPS
    if "search movie" in msg:
        q = msg.replace("search movie", "").strip()
        os.system(f"termux-open '{MOVIE_LINK}search/{q}'"); return True

    for name, target in APPS.items():
        if name in msg:
            gideon_speak(f"Opening {name}.")
            if target.startswith("am start"): os.system(target)
            else: os.system(f"termux-open '{target}'")
            return True

    # 6. SHUTDOWN
    if any(x in msg for x in ["stop", "shutdown", "offline"]):
        gideon_speak(f"Systems offline. Goodbye, {CREATOR_NAME}."); os.system("termux-wake-unlock"); exit()

    return False

def main():
    os.system("termux-wake-lock")
    os.system("clear")
    
    # Standard Greeting
    hr = int(time.strftime("%H"))
    greet = "Good morning" if hr < 12 else "Good afternoon" if hr < 18 else "Good evening"
    gideon_speak(f"{greet}, {CREATOR_NAME}. I am Gideon. Systems are standing by.")

    unlocked = False
    while not unlocked:
        msg = listen_to_user()
        if SECRET_PHRASE in msg:
            gideon_speak(f"Identity confirmed. Welcome, {CREATOR_NAME}.", theme=G); unlocked = True
        elif msg != "":
            gideon_speak("Access denied. Capturing picture.", theme=R); capture_photo()

    while True:
        msg = listen_to_user()
        if not msg: continue
        if not handle_commands(msg, 0):
            gideon_speak("Searching the web.")
            os.system(f"termux-open 'https://www.google.com/search?q={msg}'")

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: os.system("termux-wake-unlock")
