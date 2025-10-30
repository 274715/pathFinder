]#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Minimal Moonraker bridge for PrinterChess.

- Sends G-code to Moonraker so the toolhead moves to chess squares.
- Magnet is a Klipper FAN (name configurable).
- XY only. No Z.
- Includes simple calibrate + quick CLI tests.
"""

import os, time, json
import requests
from typing import Tuple

# ---------------- Moonraker endpoint ----------------
# If running on the Pi, default is fine. From a laptop, set:
#   export MOONRAKER_URL=http://<PI-IP>:7125
MOONRAKER_URL = os.environ.get("MOONRAKER_URL", "http://127.0.0.1:7125")
TIMEOUT_S     = 15
RETRIES       = 2

# ---------------- Work area (millimeters) ----------------
# a1 lower-left corner, width/height cover the 8x8 board.
WORK_X_MIN = float(os.environ.get("CHESS_X_MIN", "10"))
WORK_Y_MIN = float(os.environ.get("CHESS_Y_MIN", "10"))
WORK_W     = float(os.environ.get("CHESS_W",     "320"))
WORK_H     = float(os.environ.get("CHESS_H",     "320"))

# Magnet control (uses Klipper FAN named 'magnet' by default)
MAGNET_FAN = os.environ.get("MAGNET_FAN", "magnet")
MAGNET_ON  = 1.0
MAGNET_OFF = 0.0

# Speeds / dwells
FEED_MOVE   = int(float(os.environ.get("CHESS_FEED",  "4200")))  # mm/min
DWELL_PICK  = int(float(os.environ.get("CHESS_PICK",  "120")))   # ms
DWELL_DROP  = int(float(os.environ.get("CHESS_DROP",  "100")))   # ms


# ==================== Low-level helpers ====================

def _post_gcode(script: str):
    """POST a G-code script to Moonraker with simple retries."""
    url = f"{MOONRAKER_URL}/printer/gcode/script"
    last_err = None
    for _ in range(1 + RETRIES):
        try:
            r = requests.post(url, json={"script": script}, timeout=TIMEOUT_S)
            r.raise_for_status()
            return
        except Exception as e:
            last_err = e
            time.sleep(0.4)
    raise RuntimeError(f"Moonraker error for '{script}': {last_err}")

def _send(cmd: str):
    print(f"[GCODE] {cmd}")
    _post_gcode(cmd)


# ==================== Work area / mapping ====================

def set_workarea(xmin: float, ymin: float, width: float, height: float):
    """Update board rectangle in mm (persist only for this process)."""
    global WORK_X_MIN, WORK_Y_MIN, WORK_W, WORK_H
    WORK_X_MIN, WORK_Y_MIN, WORK_W, WORK_H = xmin, ymin, width, height
    print(f"[bridge] workarea = origin({xmin:.1f},{ymin:.1f}) size({width:.1f}×{height:.1f})")

def _square_center_mm(square: str) -> Tuple[float, float]:
    """
    'a1'..'h8' -> (x_mm, y_mm) at the center of the square, a1 is lower-left.
    """
    square = square.strip().lower()
    if len(square) != 2 or not ('a' <= square[0] <= 'h') or not ('1' <= square[1] <= '8'):
        raise ValueError(f"Bad square '{square}'")
    file_i = ord(square[0]) - ord('a')   # 0..7
    rank_i = int(square[1]) - 1          # 0..7
    sq_w = WORK_W / 8.0
    sq_h = WORK_H / 8.0
    x = WORK_X_MIN + (file_i + 0.5) * sq_w
    y = WORK_Y_MIN + (rank_i + 0.5) * sq_h
    return x, y


# ==================== Public API ====================

def home_xy():
    """Home X and Y axes (absolute mode, motors on)."""
    _send("M17")
    _send("G90")
    _send("G28 X Y")

def goto_xy(x_mm: float, y_mm: float, feed: float = FEED_MOVE):
    """Rapid move to XY in ABS mode."""
    _send(f"G0 X{x_mm:.3f} Y{y_mm:.3f} F{int(feed)}")

def magnet(enable: bool):
    """Turn magnet fan ON/OFF."""
    spd = MAGNET_ON if enable else MAGNET_OFF
    _send(f"SET_FAN_SPEED FAN={MAGNET_FAN} SPEED={spd}")

def dwell_ms(ms: int):
    _send(f"G4 P{int(ms)}")

def move_piece(src_alg: str, dst_alg: str,
               feed: float = FEED_MOVE,
               dwell_pick_ms: int = DWELL_PICK,
               dwell_drop_ms: int = DWELL_DROP):
    """
    Move one piece from src->dst:
      1) go to source center
      2) magnet ON + dwell
      3) go to dest center
      4) magnet OFF + dwell
    """
    x1, y1 = _square_center_mm(src_alg)
    x2, y2 = _square_center_mm(dst_alg)
    print(f"[bridge] move {src_alg}->{dst_alg}  ({x1:.1f},{y1:.1f})→({x2:.1f},{y2:.1f})")

    goto_xy(x1, y1, feed)
    magnet(True)
    dwell_ms(dwell_pick_ms)

    goto_xy(x2, y2, feed)
    magnet(False)
    dwell_ms(dwell_drop_ms)


# ==================== CLI for quick testing ====================

def _cli():
    import argparse
    ap = argparse.ArgumentParser(description="PrinterChess Moonraker bridge")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("home", help="Home X/Y")

    p_set = sub.add_parser("setwork", help="Set work area mm")
    p_set.add_argument("xmin", type=float)
    p_set.add_argument("ymin", type=float)
    p_set.add_argument("w", type=float)
    p_set.add_argument("h", type=float)

    p_goto = sub.add_parser("goto", help="Goto XY mm")
    p_goto.add_argument("x", type=float)
    p_goto.add_argument("y", type=float)

    p_mag = sub.add_parser("magnet", help="Magnet on/off")
    p_mag.add_argument("state", choices=["on","off"])

    p_mv = sub.add_parser("move", help="Move piece src dst (e2 e4)")
    p_mv.add_argument("src")
    p_mv.add_argument("dst")

    args = ap.parse_args()

    if args.cmd == "home":
        home_xy()
    elif args.cmd == "setwork":
        set_workarea(args.xmin, args.ymin, args.w, args.h)
    elif args.cmd == "goto":
        goto_xy(args.x, args.y)
    elif args.cmd == "magnet":
        magnet(args.state == "on")
    elif args.cmd == "move":
        move_piece(args.src, args.dst)
    else:
        ap.print_help()

if __name__ == "__main__":
    _cli()
