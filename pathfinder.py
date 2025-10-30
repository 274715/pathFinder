#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pathfinder.py
Returns safe corridor-based waypoints in BOARD-UNIT space (one square = 1x1).
We keep all geometry here unitless; chess_bridge converts to millimeters.

Conventions:
- Files a..h -> f = 0..7
- Ranks 1..8 -> r = 0..7
- Square center (f+0.5, r+0.5)
- Vertical corridor lines are at integer x (0..8); horizontal corridor lines are at integer y (0..8).
"""

from typing import List, Tuple, Optional
import chess

Point = Tuple[float, float]  # (x_units, y_units)

def fr_from_alg(a: str) -> Tuple[int, int]:
    f = ord(a[0].lower()) - ord('a')
    r = int(a[1]) - 1
    return f, r

def center_of(fr: Tuple[int, int]) -> Point:
    f, r = fr
    return (f + 0.5, r + 0.5)

def corridor_to_x(x_line: float, y: float) -> Point:
    # x_line is integer corridor between files (e.g. 2.0 is between file b and c)
    return (float(x_line), float(y))

def corridor_to_y(x: float, y_line: float) -> Point:
    # y_line is integer corridor between ranks (e.g. 3.0 is between rank 3 and 4)
    return (float(x), float(y_line))

class CaptureGraveyard:
    """
    Simple right-side lineup. We place pieces at x = 8 + margin_units + 0.5,
    and advance y in 0.9-square increments from 0.5 upward.
    When we hit the top, we start a second column (0.9*8 ≈ 7.2 tall).
    """
    def __init__(self, margin_units: float = 0.125, spacing_units: float = 0.9):
        self.margin = float(margin_units)
        self.spacing = float(spacing_units)
        self.count = 0  # total captured pieces so far

    def next_slot(self) -> Point:
        col = self.count // 8
        row = self.count % 8
        x = 8.0 + self.margin + 0.5 + col * 0.9  # second col nudged to the right
        y = 0.5 + row * self.spacing
        self.count += 1
        return (x, y)

class PathFinder:
    """
    Produces corridor-safe waypoints for special cases:
      - Knight moves
      - King (castling)
      - Captured piece removal to graveyard (via corridors)
    Other sliding pieces (rook/bishop/queen) and normal pawn moves return [src_center, dst_center].
    """
    def __init__(self, margin_mm: float = 10.0, square_mm: float = 40.0):
        # Convert a physical margin (mm) into board units (squares)
        self.margin_units = float(margin_mm) / float(square_mm)
        self.graveyard = CaptureGraveyard(self.margin_units)

    # ---------------- KNIGHT ----------------
    def path_knight_units(self, fr_from: Tuple[int,int], fr_to: Tuple[int,int]) -> List[Point]:
        (fx, fy) = fr_from
        (tx, ty) = fr_to
        sx, sy = center_of(fr_from)
        dx, dy = center_of(fr_to)

        # L move: (±2,±1) or (±1,±2). We go horizontally first, then vertically.
        # Step 1: move to vertical corridor between file min+1
        if fx < tx:
            x_line = fx + 1.0
        else:
            x_line = tx + 1.0
        # Step 2: move up/down to horizontal corridor between rank min+1
        if fy < ty:
            y_line = fy + 1.0
        else:
            y_line = ty + 1.0

        return [
            (sx, sy),
            corridor_to_x(x_line, sy),
            corridor_to_y(x_line, y_line),
            (dx, dy),
        ]

    # ---------------- KING CASTLING ----------------
    def path_king_castle_units(self, fr_from: Tuple[int,int], fr_to: Tuple[int,int]) -> List[Point]:
        # King moves two squares horizontally: e.g., e1(4,0)->g1(6,0)
        sx, sy = center_of(fr_from)
        dx, dy = center_of(fr_to)
        # Move through the two vertical corridor lines between the three files.
        step = 1 if fr_to[0] > fr_from[0] else -1
        mid1 = float(min(fr_from[0], fr_to[0])) + 1.0 if step > 0 else float(max(fr_from[0], fr_to[0]))  # first corridor
        mid2 = mid1 + 1.0 * step
        return [
            (sx, sy),
            corridor_to_x(mid1, sy),
            corridor_to_x(mid2, sy),
            (dx, dy),
        ]

    # ---------------- ROOK (as part of castling) ----------------
    def path_rook_castle_units(self, fr_from: Tuple[int,int], fr_to: Tuple[int,int]) -> List[Point]:
        # Rook slides horizontally 2 or 3 squares; push via corridor lines for symmetry with "around the margins".
        sx, sy = center_of(fr_from)
        dx, dy = center_of(fr_to)
        step = 1 if fr_to[0] > fr_from[0] else -1
        # move through each vertical corridor line between from and to
        pts: List[Point] = [(sx, sy)]
        x0 = fr_from[0]
        x1 = fr_to[0]
        # Go corridor-by-corridor (between files) until near dst, then center.
        c = min(x0, x1) + 1 if step > 0 else max(x0, x1)
        while True:
            pts.append(corridor_to_x(float(c), sy))
            if (step > 0 and c >= x1) or (step < 0 and c <= x1):
                break
            c += step
        pts.append((dx, dy))
        return pts

    # ---------------- STRAIGHT / DIAGONAL DEFAULT ----------------
    def path_direct_units(self, fr_from: Tuple[int,int], fr_to: Tuple[int,int]) -> List[Point]:
        return [center_of(fr_from), center_of(fr_to)]

    # ---------------- CAPTURED PIECE REMOVAL ----------------
    def path_remove_captured_units(self, fr_target: Tuple[int,int]) -> List[Point]:
        # Pick at center, then go via corridors to graveyard, then drop at slot center.
        tx, ty = center_of(fr_target)
        gx, gy = self.graveyard.next_slot()

        # Corridor path: move to nearest vertical corridor from target center, then run outside to x=gx, then up/down to gy.
        # Choose nearest vertical corridor to the right (so we head outwards).
        # The corridor lines to the RIGHT of a center at tx are at math.ceil(tx-0.5)+? But easier:
        # if at file f -> centers at f+0.5; next right corridor is x = f+1
        f, r = fr_target
        x_line_out = float(f + 1)  # corridor right of the target square
        path = [
            (tx, ty),                          # center of the captured piece
            corridor_to_x(x_line_out, ty),     # slide to corridor
            corridor_to_x(8.0, ty),            # go to board's outer edge corridor
            corridor_to_x(8.0 + self.margin_units, ty),  # into margin
            corridor_to_y(8.0 + self.margin_units, gy),  # along margin to slot y
            (gx, gy),                          # slot center
        ]
        return path

    # ---------------- DISPATCH ----------------
    def path_for_move_units(self,
                            piece_type: int,
                            fr_from: Tuple[int,int],
                            fr_to: Tuple[int,int],
                            is_capture: bool,
                            is_castling: bool) -> List[Point]:
        # Knights always use corridors
        if piece_type == chess.KNIGHT:
            return self.path_knight_units(fr_from, fr_to)
        # King castling: corridor path
        if piece_type == chess.KING and is_castling:
            return self.path_king_castle_units(fr_from, fr_to)
        # Otherwise straight/diag is fine (board guarantees line is clear)
        return self.path_direct_units(fr_from, fr_to)
