import subprocess
import json

def check_battery():
    # Get battery status via Termux-API
    result = subprocess.run(['termux-battery-status'], capture_output=True, text=True)
    data = json.loads(result.stdout)
    return data['percentage']

def vibrate_phone():
    # Make the phone vibrate for 500ms
    subprocess.run(['termux-vibrate', '-d', '500'])

battery = check_battery()
print(f"Companion connected. Your battery is at {battery}%.")
vibrate_phone()
print("Vibration test successful.")
