from flask import Flask, request, jsonify
import os

app = Flask(__name__)

# Optional app map (cleaner control)
APPS = {
    "whatsapp": "com.whatsapp/.Main",
    "youtube": "com.google.android.youtube/.HomeActivity",
    "settings": "com.android.settings/.Settings"
}

@app.route("/run", methods=["POST"])
def run():
    data = request.get_json(silent=True) or {}

    action = data.get("action", "")
    value = data.get("data", "")

    print(f"[Gideon] Action: {action} | Data: {value}")

    try:
        # Text output
        if action == "say":
            os.system(f'termux-tts-speak "{value}"')

        # Toast message
        elif action == "toast":
            os.system(f'termux-toast "{value}"')

        # Open URL
        elif action == "open_url":
            os.system(f'am start -a android.intent.action.VIEW -d "{value}"')

        # Open app safely
        elif action == "open_app":
            component = APPS.get(value)
            if component:
                os.system(f"am start -n {component}")
            else:
                print("Unknown app:", value)

        return jsonify({"status": "ok"})

    except Exception as e:
        print("Error:", str(e))
        return jsonify({"status": "error", "message": str(e)})

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
