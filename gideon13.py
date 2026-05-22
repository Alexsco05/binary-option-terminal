import os
import subprocess
import re
import time
import json
import sys
import shutil
import requests

# --- CONFIGURATION & IDENTITY ---
CREATOR_NAME = "Alexander"
USER_NICKNAME = "Alexsco"
SECRET_PHRASE = "execute protocol"
WA_LINK = "whatsapp://send"
WA_BIZ_LINK = "whatsapp://send"

# --- NEURAL KEY ARRAY (10-CORE) ---
API_KEYS = [
    "AIzaSyCXuNKuIIKKSWHChgURgsZ9gPG-vS5KIBk", "AIzaSyBvzJ9YhqWN_AnRokXfi7ZMQRjjSss5eVM",
    "AIzaSyBmWJASebqXUvuVlV7kPnFI6qS6UYryGUw", "AIzaSyAo_aaUmC3MfEciN0a2r3mriCT3A5WNr7M",
    "AIzaSyCAE5Xt_hekbWo8gWM78FE9jsjw6Q7T3c0", "AIzaSyBst4ScDBDRl5GjACuNgsZeevA787TwH_Q",
    "AIzaSyBECZkoIglcm410s0uullilcFM6S0zQmow", "AIzaSyBOrJwiR81GN23a4iDflwMd7ky7y4SEj_E",
    "AIzaSyDSuSZyGPAkkmfYDLHzAM7wBD8RLcb5GRA", "AIzaSyBF1lxIiA_85VATGwB7S0vPwWRLD22Zstc"
]

# --- DYNAMIC CONFIG ---
V_PITCH = "1.0"; V_RATE = "1.10" 
VOICE_MALE = "en-us-x-sfg#male_1-local"
CURRENT_THEME = '\033[1;36m' 

# COLORS
C, B, W, R, G, Y, P, X = '\033[1;36m', '\033[1;34m', '\033[1;37m', '\033[1;31m', '\033[1;32m', '\033[1;33m', '\033[1;35m', '\033[0m'

APPS = {
    "whatsapp": WA_LINK, "business": WA_BIZ_LINK, "tiktok": "https://www.tiktok.com/",
    "settings": "am start -a android.settings.SETTINGS",
    "gallery": "am start -a android.intent.action.VIEW -t image/*",
    "youtube": "vnd.youtube://", "facebook": "fb://feed", "chrome": "googlechrome://",
    "audiomack": "audiomack://", "moviebox": "https://moviebox.ng/", "opay": "opay://",
    "palmpay": "palmpay://", "phone": "tel:", "messages": "sms:"
}

chat_history = []
last_response = "Gideon standby."
WORKING_MODEL = "gemini-1.5-flash"

def draw_mega_core(duration, theme_color=C):
    cols, rows = shutil.get_terminal_size()
    v_padding = max(0, (rows // 2) - 4)
    frames = [[f"    {B}/  {theme_color}*{B}  \\{X}    "], [f"   {B}(  {W}*{B}  ){X}   "], [f"  {theme_color}((  {W}*{theme_color}  )){X}  "]]
    end_time = time.time() + duration
    idx = 0
    while time.time() < end_time:
        sys.stdout.write("\033[H" + "\n" * v_padding)
        line = frames[idx % 3][0]
        h_padding = max(0, (cols - len(re.sub(r'\033\[[0-9;]*m', '', line))) // 2)
        sys.stdout.write(" " * h_padding + line + "\n")
        sys.stdout.flush(); time.sleep(0.1); idx += 1

def gideon_speak(text, theme=None):
    global last_response, CURRENT_THEME
    if theme: CURRENT_THEME = theme
    last_response = text
    print(f"\n{CURRENT_THEME}Gideon:{X} {text}")
    os.system("termux-volume music 15")
    process = subprocess.Popen(["termux-tts-speak", "-n", VOICE_MALE, "-p", V_PITCH, "-r", V_RATE, text])
    wait_time = max(2.5, len(text.split()) * 0.5) 
    draw_mega_core(wait_time, theme_color=CURRENT_THEME)
    process.wait()

def get_ai_brain(prompt, retry_count=0):
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
    ]
    
    wrapped_prompt = prompt
    if retry_count > 0:
        wrapped_prompt = f"Please provide a simple, helpful response to: {prompt}"

    for i, current_key in enumerate(API_KEYS):
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{WORKING_MODEL}:generateContent?key={current_key}"
            payload = {
                "contents": chat_history[-6:] + [{"role": "user", "parts": [{"text": wrapped_prompt}]}],
                "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1024},
                "safetySettings": safety_settings
            }
            # LONG-RANGE FIX: Increased timeout to 60 seconds
            res = requests.post(url, json=payload, timeout=60)
            data = res.json()
            
            if 'candidates' in data and data['candidates'][0].get('content'):
                ans = data['candidates'][0]['content']['parts'][0]['text']
                chat_history.append({"role": "user", "parts": [{"text": prompt}]})
                chat_history.append({"role": "model", "parts": [{"text": ans}]})
                return ans
            continue
        except:
            continue
            
    if retry_count == 0:
        return get_ai_brain(prompt, retry_count=1)

    return "Alexander, the signal is too weak for a neural link. Let's try once more."

def handle_logic(msg):
    global V_PITCH, CURRENT_THEME
    
    # RECONNECT COMMAND
    if "reconnect" in msg or "reset signal" in msg:
        gideon_speak("Flushing neural buffers and reconnecting.", theme=Y)
        os.system("termux-telephony-deviceinfo"); return True

    if "whisper mode" in msg:
        V_PITCH = "1.2"; gideon_speak("Whisper protocol active.", theme=W); return True
    if "serious mode" in msg:
        V_PITCH = "0.7"; gideon_speak("Serious protocols active.", theme=P); return True
    if "friendly mode" in msg:
        V_PITCH = "1.0"; gideon_speak("Normal mode restored.", theme=C); return True
    if any(x in msg for x in ["repeat", "say that again"]):
        gideon_speak(f"Repeating: {last_response}"); return True
    if "lock" in msg: gideon_speak("Locked."); os.system("termux-lock"); return True
    if "lumos" in msg: os.system("termux-torch on"); gideon_speak("Lumos."); return True
    if "nox" in msg: os.system("termux-torch off"); gideon_speak("Nox."); return True
    
    for app in APPS:
        if app in msg:
            gideon_speak(f"Opening {app}."); target = APPS[app]
            os.system(target if target.startswith("am") else f"termux-open '{target}'")
            return True

    if any(x in msg for x in ["stop", "shutdown"]):
        gideon_speak(f"Goodbye, {CREATOR_NAME}."); os.system("termux-wake-unlock"); exit()

    if msg:
        reply = get_ai_brain(msg)
        gideon_speak(reply)
        return True
    return False

def listen_to_user():
    print(f"{G}[ GIDEON IS LISTENING ]{X}", end="\r")
    try:
        raw_msg = subprocess.check_output(["termux-speech-to-text"]).decode("utf-8").strip()
        if raw_msg:
            print(f"{Y}Transcript:{X} {raw_msg}") 
            return raw_msg.lower()
    except: pass
    return ""

def main():
    os.system("termux-wake-lock; clear")
    gideon_speak(f"Signal recovery active. All 10 cores online, {CREATOR_NAME}.")
    unlocked = False
    while not unlocked:
        msg = listen_to_user()
        if SECRET_PHRASE in msg:
            gideon_speak(f"Welcome, {USER_NICKNAME}.", theme=G); unlocked = True
    while True:
        msg = listen_to_user()
        if not msg: continue
        handle_logic(msg)

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: os.system("termux-wake-unlock")
