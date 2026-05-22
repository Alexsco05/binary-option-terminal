from fastapi import FastAPI
import subprocess
import json

app = FastAPI()

# 1. Device Control Logic (The "Hands")
def get_battery():
    result = subprocess.run(['termux-battery-status'], capture_output=True, text=True)
    return json.loads(result.stdout)

def set_vibration(duration: int):
    subprocess.run(['termux-vibrate', '-d', str(duration)])
    return {"status": "success", "action": "vibrate"}

# 2. API Endpoints (The "Ears")
@app.get("/")
def home():
    return {"message": "Companion Server is Online"}

@app.get("/status")
def status():
    battery_data = get_battery()
    return {
        "battery": battery_data['percentage'],
        "plugged": battery_data['status']
    }

@app.post("/action/vibrate")
def vibrate(duration: int = 500):
    return set_vibration(duration)

@app.post("/action/say")
def say_text(text: str):
    # This makes the phone actually speak out loud
    subprocess.run(['termux-tts-speak', text])
    return {"status": "speaking", "text": text}
