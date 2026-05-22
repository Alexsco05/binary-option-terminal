import os
import subprocess
import re
import time
import json
import sys
import shutil

# --- CONFIGURATION & IDENTITY ---
CREATOR_NAME = "Alexander"
USER_NICKNAME = "Alexsco"
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

# KEYWORD MAPPING
COMMAND_MAP = {
    "lock": ["lock", "secure", "shut down system"],
    "light_on": ["lumos", "light on", "flashlight", "torch"],
    "light_off": ["nox", "light off", "dark"],
    "pictures": ["show picture", "photo", "log", "captured"],
    "backup": ["backup", "sync", "save gallery"],
    "identity": ["who are you", "identity", "your name"],
    "battery": ["battery", "power", "percent"],
    "weather": ["weather", "temperature", "lagos"]
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
        time.sleep(0.1)
        idx += 1
    sys.stdout.write("\033[H" + ("\n" * rows))

def gideon_speak(text, theme=C):
    print(f"\n{C}Gideon:{X} {text}")
    os.system("termux-volume music 15")
    subprocess.Popen(["termux-tts-speak", "-n", VOICE_MALE, "-r", "1.25", text])
    draw_mega_core(len(text)/12 + 0.5, theme_color=theme)

def web_intel(query):
    gideon_speak("Searching intelligence database...")
    try:
        wiki_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{query.replace(' ', '_')}"
        res = subprocess.check_output(["curl", "-s", wiki_url]).decode("utf-8")
        data = json.loads(res)
        answer = data.get("extract")
        if not answer:
            ddg_url = f"https://api.duckduckgo.com/?q={query}&format=json&no_html=1"
            res_ddg = subprocess.check_output(["curl", "-s", ddg_url]).decode("utf-8")
            answer = json.loads(res_ddg).get("AbstractText")
        return answer if answer else "I found no direct data. Opening web search."
    except: return "Intelligence connection failed."

def listen_to_user():
    print(f"{G}[Gideon listening...]{X}", end="\r")
    try:
        return subprocess.check_output(["termux-speech-to-text"]).decode("utf-8").strip().lower()
    except: return ""

def capture_photo():
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    save_path = os.path.expanduser(f"~/cap_{timestamp}.jpg")
    os.system(f"termux-camera-photo -c 1 {save_path}")

def handle_logic(msg):
    # 1. COMMAND KEYWORDS
    if any(k in msg for k in COMMAND_MAP["lock"]):
        gideon_speak("Engaging system lock."); os.system("termux-lock"); return True
    if any(k in msg for k in COMMAND_MAP["light_on"]):
        os.system("termux-torch on"); gideon_speak("Lumos."); return True
    if any(k in msg for k in COMMAND_MAP["light_off"]):
        os.system("termux-torch off"); gideon_speak("Nox."); return True
    if any(k in msg for k in COMMAND_MAP["pictures"]):
        gideon_speak("Opening capture logs."); os.system("termux-open ~"); return True
    if any(k in msg for k in COMMAND_MAP["identity"]):
        gideon_speak(f"I am Gideon. A male AI interface created by {CREATOR_NAME}."); return True
    if any(k in msg for k in COMMAND_MAP["battery"]):
        output = subprocess.check_output(["termux-battery-status"]).decode("utf-8")
        p = json.loads(output).get("percentage")
        gideon_speak(f"Battery is at {p} percent."); return True

    # 2. APP LAUNCHING (Restored)
    for app_name, target in APPS.items():
        if app_name in msg:
            gideon_speak(f"Opening {app_name}.")
            if target.startswith("am start"): os.system(target)
            else: os.system(f"termux-open '{target}'")
            return True

    # 3. GOODBYE
    if any(x in msg for x in ["stop", "shutdown", "offline"]):
        gideon_speak(f"Session ended. Goodbye {CREATOR_NAME}."); os.system("termux-wake-unlock"); exit()

    # 4. WEB SEARCH (Direct Answer)
    if msg:
        result = web_intel(msg)
        if "Opening web search" in result:
            gideon_speak(result)
            os.system(f"termux-open 'https://www.google.com/search?q={msg}'")
        else:
            gideon_speak(result)
        return True
    return False

def main():
    os.system("termux-wake-lock")
    os.system("clear")
    
    # PERMANENT GREETING
    hr = int(time.strftime("%H"))
    greet = "Good morning" if hr < 12 else "Good afternoon" if hr < 18 else "Good evening"
    gideon_speak(f"{greet}, {CREATOR_NAME}. I am Gideon. Protocols active.")

    unlocked = False
    while not unlocked:
        msg = listen_to_user()
        if SECRET_PHRASE in msg:
            gideon_speak(f"Identity confirmed. Welcome, {USER_NICKNAME}.", theme=G); unlocked = True
        elif msg != "":
            gideon_speak("Access denied. Capturing picture.", theme=R); capture_photo()

    while True:
        msg = listen_to_user()
        if not msg: continue
        handle_logic(msg)

def run_from_android():
    import sys
    if len(sys.argv) > 1:
        msg = " ".join(sys.argv[1:]).lower()
        handle_logic(msg)
        return True
    return False

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: os.system("termux-wake-unlock")
