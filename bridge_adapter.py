#!/usr/bin/env python3
"""
bridge_adapter.py
Compatibility shim that forwards to the real Moonraker bridge.
No dummy mode; everything goes straight to chess_bridge.
"""

import chess_bridge as _hw

class _MoonrakerBridge:
    def __init__(self):
        # put any one-time init here if you need it later
        pass

    # optional “lifecycle” hook for old code; no-op here
    def start(self):
        return

    # --- direct forwards to chess_bridge public API ---
    def set_workarea(self, xmin, ymin, width, height):
        _hw.set_workarea(xmin, ymin, width, height)

    def home_xy(self):
        _hw.home_xy()

    def goto_xy(self, x_mm, y_mm, feed=None):
        if feed is None:
            _hw.goto_xy(x_mm, y_mm)
        else:
            _hw.goto_xy(x_mm, y_mm, feed)

    def magnet(self, enable: bool):
        _hw.magnet(enable)

    def move_piece(self, src_alg: str, dst_alg: str,
                   feed=None, dwell_pick_ms=None, dwell_drop_ms=None):
        kwargs = {}
        if feed is not None:
            kwargs["feed"] = feed
        if dwell_pick_ms is not None:
            kwargs["dwell_pick_ms"] = dwell_pick_ms
        if dwell_drop_ms is not None:
            kwargs["dwell_drop_ms"] = dwell_drop_ms
        _hw.move_piece(src_alg, dst_alg, **kwargs)

def make_bridge():
    """Return a bridge instance compatible with older code."""
    return _MoonrakerBridge()
