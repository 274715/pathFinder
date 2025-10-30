#!/usr/bin/env python3
import requests
import sys
import time

# ==== SETTINGS ====
MOONRAKER_URL = "http://192.168.1.78:7125"  # change if needed
API_KEY = None                               # e.g., "your-moonraker-api-key" or leave None
SAFE_Z = 10                                  # mm to lift before fast XY moves (if you have Z)
XY_FEED = 9000                               # mm/min (150 mm/s) adjust if needed
DWELL_MS = 1200                              # default magnet on time if not provided via args

def send_gcode(script: str):
    """Send one or multiple G-code lines to Moonraker."""
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["X-Api-Key"] = API_KEY
    r = requests.post(f"{MOONRAKER_URL}/printer/gcode/script",
                      headers=headers, json={"script": script})
    if r.status_code != 200:
        print(f"❌ {r.status_code}: {r.text}")
        sys.exit(1)
    print(f"✅ Sent:\n{script}")

def main():
    if len(sys.argv) < 3:
        print("Usage: python3 bridge_move_test.py <X> <Y> [dwell_ms]")
        print("Example: python3 bridge_move_test.py 100 100 1500")
        sys.exit(1)

    try:
        x = float(sys.argv[1]); y = float(sys.argv[2])
        dwell = int(sys.argv[3]) if len(sys.argv) >= 4 else DWELL_MS
    except ValueError:
        print("X and Y must be numbers; dwell_ms must be integer milliseconds.")
        sys.exit(1)

    # Build a safe, simple script:
    # - Absolute mode, mm, home XY
    # - (Optional Z lift if your Z is still installed; harmless if ignored by config)
    # - Move to target, toggle magnet, wait, magnet off, return near home
    lines = [
        "G90",                          # absolute
        "G21",                          # mm
        "M400",                         # wait for moves to finish
        "G28 X Y",                      # home XY (avoid Z to keep it simple)
        f"G0 X{x:.2f} Y{y:.2f} F{XY_FEED}",
        "SET_FAN_SPEED FAN=magnet SPEED=1",
        f"G4 P{dwell}",                 # dwell milliseconds
        "SET_FAN_SPEED FAN=magnet SPEED=0",
        "M400",
        "G0 X10 Y10 F6000"              # return somewhere safe/visible
    ]
    send_gcode("\n".join(lines))

if __name__ == "__main__":
    main()
