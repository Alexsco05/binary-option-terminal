from flask import Flask, request, jsonify
import os
import subprocess
import json

app = Flask(__name__)

# OPTIONAL APP SHORTCUTS
APPS = {
    "whatsapp": "am start -n com.whatsapp/.Main",
    "youtube": "am start -n com.google.android.youtube/.HomeActivity",
    "settings": "am start -a android.settings.SETTINGS"
}

# SPEAK FUNCTION (clean and reusable)
def gideon_speak(text):
    print("Gideon:", text)
    os.system(f'termux-tts-speak "{text}"')

# MAIN COMMAND BRAIN
def process_command(msg):
    msg = msg.lower().strip()

    # GREETING
    if "hello" in msg:
        gideon_speak("Hello. How can I assist you?")
        return

    # OPEN GOOGLE
    if "open google" in msg or "launch google" in msg:
        gideon_speak("Opening Google.")
        os.system("termux-open 'https://google.com'")
        return

    # FLASHLIGHT
    if "light on" in msg or "torch" in msg:
        os.system("termux-torch on")
        gideon_speak("Flashlight activated.")
        return

    if "light off" in msg:
        os.system("termux-torch off")
        gideon_speak("Flashlight turned off.")
        return

    # BATTERY
    if "battery" in msg:
        output = subprocess.check_output(["termux-battery-status"]).decode("utf-8")
        percent = json.loads(output).get("percentage")
        gideon_speak(f"Battery is at {percent} percent.")
        return

    # OPEN APPS
    for app_name, command in APPS.items():
        if app_name in msg:
            gideon_speak(f"Opening {app_name}.")
            os.system(command)
            return

    # FALLBACK
    gideon_speak("Command not recognized.")

# MAIN ROUTE
@app.route("/run", methods=["POST"])
def run():
    data = request.get_json(silent=True) or {}

    action = data.get("action", "")
    msg = data.get("data", "")

    print(f"[Gideon] Action: {action} | Data: {msg}")

    try:
        if action == "say":
            gideon_speak(msg)

        elif action == "toast":
            os.system(f'termux-toast "{msg}"')

        else:
            process_command(msg)

        return jsonify({"status": "ok"})

    except Exception as e:
        print("Error:", e)
        return jsonify({"status": "error", "message": str(e)})

# START SERVER
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
