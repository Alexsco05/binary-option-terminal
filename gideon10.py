import os
import subprocess
import re
import time
import json
import sys
import shutil

# --- CONFIGURATION ---
USER_NAME = "Alexsco"
SECRET_PHRASE = "execute protocol"
WA_LINK = "whatsapp://send?phone=2348158051683"
MOVIE_LINK = "https://moviebox.ng/" 

# COLORS
C = '\033[1;36m' # Cyan
B = '\033[1;34m' # Blue
W = '\033[1;37m' # White
R = '\033[1;31m' # Red
G = '\033[1;32m' # Green
X = '\033[0m'    # Reset

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

def draw_mega_core(duration, theme_color=C):
    """Draws a large pulsing core centered vertically and horizontally"""
    cols, rows = shutil.get_terminal_size()
    # Vertical padding to hit the dead center
    v_padding = (rows // 2) - 3 
    
    frames = [
        [f"      {W}---{X}      ",
         f"    {B}/  {theme_color}●{B}  \\{X}    ",
         f"      {W}---{X}      "],
        
        [f"     {theme_color}-------{X}     ",
         f"   {B}((  {W}●{B}  )){X}   ",
         f"     {theme_color}-------{X}     "],
        
        [f"    {W}--------{X}    ",
         f"  {theme_color}(((  {W}●{theme_color}  ))){X}  ",
         f"    {W}--------{X}    "]
    ]
    
    end_time = time.time() + duration
    idx = 0
    while time.time() < end_time:
        frame = frames[idx % len(frames)]
        # Clear screen and move to center
        sys.stdout.write("\033[H" + "\n" * v_padding)
        for line in frame:
            h_padding = (cols - len(re.sub(r'\033\[[0-9;]*m', '', line))) // 2
            sys.stdout.write(" " * h_padding + line + "\n")
        sys.stdout.flush()
        time.sleep(0.15)
        idx += 1
    # Wipe the core after speaking
    sys.stdout.write("\033[H" + ("\n" * rows))

def gideon_speak(text, theme=C, stream="MUSIC"):
    print(f"\n{C}Gideon:{X} {text}")
    os.system(f"termux-volume {stream.lower()} 15")
    process = subprocess.Popen(["termux-tts-speak", "-p", "0.9", "-r", "1.2", "-s", stream, text])
    duration = len(text) / 10 + 1.2
    draw_mega_core(duration, theme_color=theme)
    process.wait()

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
        status = data.get("status")
        return percent, f"Battery is at {percent} percent and {status}."
    except:
        return 0, "Battery unavailable."

def listen_to_user():
    print(f"\n{G}[Listening...]{X}")
    try:
        result = subprocess.check_output(["termux-speech-to-text"]).decode("utf-8").strip()
        if result:
            print(f"{W}{USER_NAME}:{X} {result}")
            return result.lower()
        return ""
    except: return ""

def handle_commands(msg, start_batt):
    # STOP
    if any(word in msg for word in ["stop", "shutdown", "exit", "offline"]):
        end_batt, _ = get_battery_status()
        used = start_batt - end_batt
        gideon_speak(f"Shutting down. Final battery {end_batt} percent. Used {used} percent. Goodbye, {USER_NAME}.")
        os.system("termux-wake-unlock")
        exit()

    # IDENTITY
    if any(word in msg for word in ["identify", "who are you", "identity"]):
        gideon_speak(f"I am Gideon, your personal AI assistant. Running core protocols on itel P40.")
        return True

    # BATTERY
    if "battery" in msg:
        _, info = get_battery_status()
        gideon_speak(info)
        return True

    # FIND DEVICE
    if any(word in msg for word in ["find my device", "where are you"]):
        os.system("termux-vibrate -d 800")
        gideon_speak(f"I am here, {USER_NAME}!", stream="ALARM")
        return True

    # MOVIE
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
    
    target = msg.replace("open ", "").strip()
    gideon_speak(f"Searching web for {target}.")
    os.system(f"termux-open 'https://www.google.com/search?q={target}'")

def main():
    os.system("termux-wake-lock")
    os.system("clear")
    
    start_batt, battery_info = get_battery_status()
    greeting = get_time_greeting()
    current_time = time.strftime("%I:%M %p")
    
    gideon_speak(f"{greeting}, {USER_NAME}. I am Gideon.")
    gideon_speak(f"Time is {current_time}. {battery_info}")
    gideon_speak("Security systems active. Awaiting activation phrase.")

    # LOCKDOWN
    unlocked = False
    while not unlocked:
        msg = listen_to_user()
        if SECRET_PHRASE in msg:
            gideon_speak("Identity confirmed. Protocols unlocked.", theme=G)
            unlocked = True
        elif any(word in msg for word in ["stop", "shutdown"]):
            os.system("termux-wake-unlock")
            exit()
        elif msg != "":
            gideon_speak("Access denied.", theme=R)

    # COMMAND LOOP
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
