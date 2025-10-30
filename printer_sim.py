#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PrinterChess Pathfinding Simulator — Drag to Move (Mac windowed)
Crash-safe on captures (incl. en passant) + corridor routing.

- Drag pieces with the mouse (only the side to move). Release on a target square.
- Also supports typing UCI (e.g., e2e4, g1f3, e1g1, e7e8q) and pressing Enter.

Path rules:
- Corridor routing between squares for all pieces.
- Knights: 3-leg on-line route (1/2-square sidestep → 2 squares long leg → 1/2-square into center).
- Captures: remove enemy first → exit to nearest margin → outside perimeter to 1" sidebar → drop
            → return → move own piece to destination. (Now robust to en passant.)
- Castling: rook first (corridor), then king (corridor).

Viz:
- Magnet dot: RED = magnet on (dragging), BLACK = off.
- Red polyline shows current move path and clears for the next move.
- Right sidebar is exactly 1 inch (96 px) for captured piece markers.

Run:
  python3 printer_sim.py

Requires:
  pip install pygame python-chess
"""

import math
import sys
import pygame
import chess
import heapq

# ------------------ Window & Board Geometry ------------------
INCH_PX = 96  # exact 1-inch sidebar

BOARD_PIXELS = 640
MARGIN = 32
SQUARE = (BOARD_PIXELS - 2 * MARGIN) // 8
BOARD_PIXELS = 2 * MARGIN + SQUARE * 8  # snap

SIDEBAR_W = INCH_PX
INPUT_H = 56
WIN_W = BOARD_PIXELS + SIDEBAR_W
WIN_H = BOARD_PIXELS + INPUT_H

# Magnet animation speeds
TRAVEL_SPEED_PX = 8.0   # no piece
DRAG_SPEED_PX   = 5.0   # dragging a piece

# Colors
COL_BG     = (24, 24, 28)
COL_LIGHT  = (240, 217, 181)
COL_DARK   = (181, 136, 99)
COL_GRID   = (70, 70, 72)
COL_TEXT   = (230, 230, 235)
COL_DOT    = (32, 32, 32)
COL_RED    = (230, 60, 60)
COL_SIDEBAR= (30, 30, 34)
COL_PATH   = (235, 65, 65)
COL_INPUT  = (36, 36, 40)
COL_BORDER = (70, 70, 80)
COL_SEL    = (112, 162, 255)

FILES = "abcdefgh"

# ------------------ Chess / Mapping Helpers ------------------
def sq_to_rc(square: chess.Square):
    f = chess.square_file(square)  # 0..7
    r = chess.square_rank(square)  # 0..7
    return (r, f)

def rc_to_sq(r, c):
    return chess.square(c, r)

def rc_to_center_xy(r, c):
    cx = MARGIN + c * SQUARE + SQUARE / 2
    cy_from_top = MARGIN + (7 - r) * SQUARE + SQUARE / 2
    return (cx, cy_from_top)

def mouse_to_square(mx, my):
    """Return a chess.Square or None if outside board."""
    if not (MARGIN <= mx < BOARD_PIXELS - MARGIN and MARGIN <= my < BOARD_PIXELS - MARGIN):
        return None
    c = int((mx - MARGIN) // SQUARE)
    r_from_top = int((my - MARGIN) // SQUARE)
    r = 7 - r_from_top
    if 0 <= r <= 7 and 0 <= c <= 7:
        return rc_to_sq(r, c)
    return None

def board_occupied_rc(board: chess.Board):
    occ = set()
    for sq in chess.SQUARES:
        if board.piece_at(sq):
            occ.add(sq_to_rc(sq))
    return occ

# Safe en passant detector (no reliance on board.is_en_passant)
def is_en_passant(board: chess.Board, move: chess.Move) -> bool:
    p = board.piece_at(move.from_square)
    if not p or p.piece_type != chess.PAWN:
        return False
    # must move diagonally
    if chess.square_file(move.from_square) == chess.square_file(move.to_square):
        return False
    # destination must be empty and equal to ep target
    return board.piece_at(move.to_square) is None and board.ep_square == move.to_square

# ------------------ Corridor Graph (centers + midpoints) ------------------
# Nodes:
#  ("C", r, c): center of (r,c)
#  ("H", r, c): midpoint between (r,c) and (r,c+1)
#  ("V", r, c): midpoint between (r,c) and (r+1,c)

def build_corridor_graph():
    nodes = set()
    edges = {}

    def add(n):
        if n not in nodes:
            nodes.add(n); edges[n] = set()

    def link(a, b):
        edges[a].add(b); edges[b].add(a)

    for r in range(8):
        for c in range(8):
            add(("C", r, c))

    for r in range(8):
        for c in range(7):
            n = ("H", r, c)
            add(n)
            link(n, ("C", r, c))
            link(n, ("C", r, c+1))

    for r in range(7):
        for c in range(8):
            n = ("V", r, c)
            add(n)
            link(n, ("C", r, c))
            link(n, ("C", r+1, c))

    return nodes, edges

NODES, EDGES = build_corridor_graph()

def node_xy(node):
    t, r, c = node
    if t == "C":
        return rc_to_center_xy(r, c)
    elif t == "H":
        x1, y1 = rc_to_center_xy(r, c)
        x2, y2 = rc_to_center_xy(r, c+1)
        return ((x1 + x2) / 2, (y1 + y2) / 2)
    elif t == "V":
        x1, y1 = rc_to_center_xy(r, c)
        x2, y2 = rc_to_center_xy(r+1, c)
        return ((x1 + x2) / 2, (y1 + y2) / 2)

def nearest_node_to_xy(xy):
    best = None
    bestd = 1e18
    for n in NODES:
        nx, ny = node_xy(n)
        d = abs(nx - xy[0]) + abs(ny - xy[1])
        if d < bestd:
            bestd = d
            best = n
    return best

def heuristic(a, b):
    ax, ay = node_xy(a); bx, by = node_xy(b)
    return abs(ax - bx) + abs(ay - by)

def a_star(start, goal, is_blocked_center):
    openh = []
    heapq.heappush(openh, (0, start))
    came = {start: None}
    g = {start: 0}

    while openh:
        _, cur = heapq.heappop(openh)
        if cur == goal:
            path = []
            n = cur
            while n is not None:
                path.append(n)
                n = came[n]
            path.reverse()
            return path
        for nb in EDGES[cur]:
            if nb[0] == "C":
                rr, cc = nb[1], nb[2]
                if is_blocked_center(rr, cc) and nb != goal:
                    continue
            t = g[cur] + 1
            if t < g.get(nb, 1e18):
                g[nb] = t
                came[nb] = cur
                f = t + heuristic(nb, goal)
                heapq.heappush(openh, (f, nb))
    return None

def plan_corridor_path(board: chess.Board, src_sq: chess.Square, dst_sq: chess.Square):
    occ = board_occupied_rc(board)
    rs, cs = sq_to_rc(src_sq)
    rd, cd = sq_to_rc(dst_sq)
    start = ("C", rs, cs)
    goal  = ("C", rd, cd)

    def blocked(r, c):
        return (r, c) in occ and not (r == rs and c == cs)

    nodes = a_star(start, goal, blocked)
    if not nodes:
        raise RuntimeError("No corridor path found.")
    return [node_xy(n) for n in nodes]

def corridor_between_points(board: chess.Board, xy_start, xy_end):
    occ = board_occupied_rc(board)
    start = nearest_node_to_xy(xy_start)
    goal  = nearest_node_to_xy(xy_end)

    # It's possible that the nearest node to either endpoint is the center of
    # an occupied square (for example, when starting outside the board near a
    # piece).  We still need to allow entering/exiting through that square, so
    # exempt those centers from the blocked set.
    exempt = set()
    if start[0] == "C":
        exempt.add((start[1], start[2]))
    if goal[0] == "C":
        exempt.add((goal[1], goal[2]))

    def blocked(r, c):
        return (r, c) in occ and (r, c) not in exempt

    nodes = a_star(start, goal, blocked)
    if not nodes:
        raise RuntimeError("No path between points.")
    return [node_xy(n) for n in nodes]

def corridor_to_point(board: chess.Board, from_sq: chess.Square, xy_end):
    rs, cs = sq_to_rc(from_sq)
    start = ("C", rs, cs)
    goal  = nearest_node_to_xy(xy_end)
    occ = board_occupied_rc(board)

    def blocked(r, c):
        return (r, c) in occ and not (r == rs and c == cs)

    nodes = a_star(start, goal, blocked)
    if not nodes:
        raise RuntimeError("No path to point.")
    return [node_xy(n) for n in nodes]

# ------------------ Special Knight Route (on lines) ------------------
def plan_knight_route_on_lines(board: chess.Board, move: chess.Move):
    """
    Knight path that stays on corridors:
      1) 1/2-square sidestep to nearest corridor (small leg direction),
      2) 2-square long leg straight along that corridor,
      3) 1/2-square into destination center.
    """
    src, dst = move.from_square, move.to_square
    r0, c0 = sq_to_rc(src); r1, c1 = sq_to_rc(dst)
    dr = r1 - r0; dc = c1 - c0
    x0, y0 = rc_to_center_xy(r0, c0)
    x1, y1 = rc_to_center_xy(r1, c1)

    half = SQUARE * 0.5
    two  = SQUARE * 2.0
    pts = []

    if abs(dr) == 2 and abs(dc) == 1:  # vertical long leg
        dir_x = 1 if dc > 0 else -1
        lane_x = x0 + dir_x * half
        pts += [(x0, y0), (lane_x, y0)]
        dir_y = -1 if dr > 0 else 1  # screen Y down is +
        pts += [(lane_x, y0 + dir_y * two), (x1, y1)]
        return pts

    if abs(dr) == 1 and abs(dc) == 2:  # horizontal long leg
        dir_y = -1 if dr > 0 else 1
        lane_y = y0 + dir_y * half
        pts += [(x0, y0), (x0, lane_y)]
        dir_x = 1 if dc > 0 else -1
        pts += [(x0 + dir_x * two, lane_y), (x1, y1)]
        return pts

    return plan_corridor_path(board, src, dst)

# ------------------ Capture: Margin/Perimeter Route ------------------
def plan_margin_escape_path(cap_xy, grave_xy):
    """
    From captured square center:
      -> nearest edge via 1/2-square sidestep,
      -> step just OUTSIDE the board,
      -> along outside perimeter toward graveyard,
      -> into graveyard center.
    """
    cx, cy = cap_xy
    x_left   = MARGIN
    x_right  = BOARD_PIXELS - MARGIN
    y_top    = MARGIN
    y_bottom = BOARD_PIXELS - MARGIN

    d_left   = abs(cx - x_left)
    d_right  = abs(x_right - cx)
    d_top    = abs(cy - y_top)
    d_bottom = abs(y_bottom - cy)

    edge = min(
        [("left", d_left), ("right", d_right), ("top", d_top), ("bottom", d_bottom)],
        key=lambda t: t[1]
    )[0]

    outside = SQUARE * 0.6
    pts = [(cx, cy)]

    if edge in ("left", "right"):
        dir_x = -1 if edge == "left" else 1
        lane_x = cx + dir_x * (SQUARE * 0.5)
        pts.append((lane_x, cy))
        border_x = x_left if edge == "left" else x_right
        outside_x = border_x + dir_x * outside
        pts.append((outside_x, cy))
        gx, gy = grave_xy
        pts.append((gx, cy))
        pts.append((gx, gy))
    else:
        dir_y = -1 if edge == "top" else 1
        lane_y = cy + dir_y * (SQUARE * 0.5)
        pts.append((cx, lane_y))
        border_y = y_top if edge == "top" else y_bottom
        outside_y = border_y + dir_y * outside
        pts.append((cx, outside_y))
        gx, gy = grave_xy
        pts.append((cx, gy))
        pts.append((gx, gy))

    return pts

# ------------------ Move Planning: normal / capture / castling ------------------
GRAVE_COLS = 2
grave_positions = []
captured_white = []
captured_black = []

def init_grave_positions():
    global grave_positions
    grave_positions = []
    col_w = SIDEBAR_W / GRAVE_COLS
    x0 = BOARD_PIXELS
    y0 = MARGIN
    for r in range(10):
        for c in range(GRAVE_COLS):
            cx = x0 + c * col_w + col_w / 2
            cy = y0 + r * (SQUARE * 0.9) + SQUARE * 0.45
            grave_positions.append((cx, cy))

def next_grave_xy(color: chess.Color):
    arr = captured_white if color == chess.WHITE else captured_black
    idx = len(arr)
    if idx < len(grave_positions):
        return grave_positions[idx]
    return (BOARD_PIXELS + SIDEBAR_W/2, WIN_H - INPUT_H - 20 - idx * 10)

def plan_capture_sequence(board: chess.Board, move: chess.Move):
    """
    Remove enemy first via margin/perimeter, then move own piece.
    Returns (segments, captured_color, grave_xy).
    """
    src, dst = move.from_square, move.to_square
    temp = board.copy()

    # Determine captured square (safe en passant handling)
    if is_en_passant(board, move):
        # captured pawn sits on the file of dst, rank of src
        cap_sq = chess.square(chess.square_file(dst), chess.square_rank(src))
    else:
        cap_sq = dst

    captured_piece = board.piece_at(cap_sq)
    captured_color = captured_piece.color if captured_piece else chess.WHITE

    # to target (OFF), grab (ON)
    path_to_target = plan_corridor_path(board, src, cap_sq)
    if not path_to_target:
        raise RuntimeError("No path to captured piece.")
    cap_xy = rc_to_center_xy(*sq_to_rc(cap_sq))
    grave_xy = next_grave_xy(captured_color)

    # remove captured from temp BEFORE planning own path
    temp.remove_piece_at(cap_sq)

    # margin/perimeter for the captured piece
    margin_path = plan_margin_escape_path(cap_xy, grave_xy)
    if not margin_path:
        margin_path = [cap_xy, grave_xy]  # extreme fallback (shouldn't happen)

    # back to src (OFF)
    src_xy = rc_to_center_xy(*sq_to_rc(src))
    path_back = corridor_between_points(temp, grave_xy, src_xy)

    # move own piece
    piece = board.piece_at(src)
    if piece and piece.piece_type == chess.KNIGHT:
        path_src_to_dst = plan_knight_route_on_lines(temp, move)
    else:
        path_src_to_dst = plan_corridor_path(temp, src, dst)

    segments = [
        {"waypoints": path_to_target, "magnet_on": False},
        {"waypoints": [path_to_target[-1]], "magnet_on": True},
        {"waypoints": margin_path, "magnet_on": True},
        {"waypoints": [margin_path[-1]], "magnet_on": False},
        {"waypoints": path_back, "magnet_on": False},
        {"waypoints": path_src_to_dst, "magnet_on": True},
        {"waypoints": [path_src_to_dst[-1]], "magnet_on": False},
    ]
    return segments, captured_color, grave_xy

def plan_normal_move(board: chess.Board, move: chess.Move):
    piece = board.piece_at(move.from_square)
    if piece and piece.piece_type == chess.KNIGHT:
        path = plan_knight_route_on_lines(board, move)
    else:
        path = plan_corridor_path(board, move.from_square, move.to_square)
    return [
        {"waypoints": path, "magnet_on": True},
        {"waypoints": [path[-1]], "magnet_on": False},
    ]

def plan_castling(board: chess.Board, move: chess.Move):
    src, dst = move.from_square, move.to_square
    king_rank = chess.square_rank(src)
    kingside = chess.square_file(dst) > chess.square_file(src)

    if kingside:
        rook_from = chess.square(chess.FILE_NAMES.index('h'), king_rank)
        rook_to   = chess.square(chess.FILE_NAMES.index('f'), king_rank)
    else:
        rook_from = chess.square(chess.FILE_NAMES.index('a'), king_rank)
        rook_to   = chess.square(chess.FILE_NAMES.index('d'), king_rank)

    rook_path = plan_corridor_path(board, rook_from, rook_to)
    tmp = board.copy()
    tmp.push(chess.Move(rook_from, rook_to))
    king_path = plan_corridor_path(tmp, src, dst)

    return [
        {"waypoints": rook_path, "magnet_on": True},
        {"waypoints": [rook_path[-1]], "magnet_on": False},
        {"waypoints": king_path, "magnet_on": True},
        {"waypoints": [king_path[-1]], "magnet_on": False},
    ]

# ------------------ Rendering ------------------
def draw_board(surface):
    surface.fill(COL_BG)
    board_rect = pygame.Rect(0, 0, BOARD_PIXELS, BOARD_PIXELS)
    pygame.draw.rect(surface, COL_BORDER, board_rect, 2)
    for c in range(8):
        for r in range(8):
            x = MARGIN + c * SQUARE
            y = MARGIN + (7 - r) * SQUARE
            color = COL_LIGHT if (r + c) % 2 else COL_DARK
            pygame.draw.rect(surface, color, (x, y, SQUARE, SQUARE))
    sidebar = pygame.Rect(BOARD_PIXELS, 0, SIDEBAR_W, BOARD_PIXELS)
    pygame.draw.rect(surface, COL_SIDEBAR, sidebar)
    for i in range(9):
        x = MARGIN + i * SQUARE
        pygame.draw.line(surface, COL_GRID, (x, MARGIN), (x, BOARD_PIXELS - MARGIN), 1)
        y = MARGIN + i * SQUARE
        pygame.draw.line(surface, COL_GRID, (MARGIN, y), (MARGIN + 8 * SQUARE, y), 1)

def draw_labels(surface, font_small):
    for i, f in enumerate(FILES):
        lx = MARGIN + i * SQUARE + SQUARE // 2
        ly = BOARD_PIXELS - 14
        lab = font_small.render(f, True, COL_TEXT)
        surface.blit(lab, (lx - lab.get_width()//2, ly))
    for r in range(8):
        txt = str(r + 1)
        lx = 10
        ly = MARGIN + (7 - r) * SQUARE + SQUARE // 2 - 8
        lab = font_small.render(txt, True, COL_TEXT)
        surface.blit(lab, (lx, ly))

PIECE_CHARS = {
    chess.PAWN:   {True: "♙", False: "♟"},
    chess.KNIGHT: {True: "♘", False: "♞"},
    chess.BISHOP: {True: "♗", False: "♝"},
    chess.ROOK:   {True: "♖", False: "♜"},
    chess.QUEEN:  {True: "♕", False: "♛"},
    chess.KING:   {True: "♔", False: "♚"},
}

def draw_pieces(surface, board, font_piece, skip_sq=None, dragging_glyph=None, drag_pos=None):
    for sq in chess.SQUARES:
        if skip_sq is not None and sq == skip_sq:
            continue
        piece = board.piece_at(sq)
        if not piece: continue
        r, c = sq_to_rc(sq)
        cx, cy = rc_to_center_xy(r, c)
        glyph = PIECE_CHARS[piece.piece_type][piece.color]
        surf  = font_piece.render(glyph, True, (15,15,15))
        surface.blit(surf, (cx - surf.get_width()/2, cy - surf.get_height()/2))
    # draw dragging piece on top
    if dragging_glyph and drag_pos:
        surf = dragging_glyph
        surface.blit(surf, (drag_pos[0] - surf.get_width()/2, drag_pos[1] - surf.get_height()/2))

def draw_graveyard(surface, font_small):
    header = font_small.render("Captured", True, COL_TEXT)
    surface.blit(header, (BOARD_PIXELS + (SIDEBAR_W - header.get_width())//2, 8))
    for arr, color in ((captured_white, True), (captured_black, False)):
        for (x, y) in arr:
            surf = font_small.render("●", True, (220,220,220) if color else (80,80,80))
            surface.blit(surf, (x - surf.get_width()/2, y - surf.get_height()/2))

def draw_input_bar(surface, font_ui, text, error_msg=""):
    rect = pygame.Rect(0, BOARD_PIXELS, WIN_W, INPUT_H)
    pygame.draw.rect(surface, COL_INPUT, rect)
    pygame.draw.line(surface, COL_BORDER, (0, BOARD_PIXELS), (WIN_W, BOARD_PIXELS), 2)
    prompt = font_ui.render("Type UCI (or drag pieces):", True, COL_TEXT)
    surface.blit(prompt, (10, BOARD_PIXELS + 10))
    inp = font_ui.render(text, True, COL_TEXT)
    surface.blit(inp, (10, BOARD_PIXELS + 28))
    if error_msg:
        err = font_ui.render(error_msg, True, COL_RED)
        surface.blit(err, (WIN_W - err.get_width() - 10, BOARD_PIXELS + 10))

def draw_path(surface, points):
    if len(points) >= 2:
        pygame.draw.lines(surface, COL_PATH, False, points, 3)

def draw_magnet(surface, pos, on):
    color = COL_RED if on else COL_DOT
    pygame.draw.circle(surface, color, (int(pos[0]), int(pos[1])), 6)

def draw_selection(surface, sq):
    if sq is None: return
    r, c = sq_to_rc(sq)
    x = MARGIN + c * SQUARE
    y = MARGIN + (7 - r) * SQUARE
    pygame.draw.rect(surface, COL_SEL, (x+2, y+2, SQUARE-4, SQUARE-4), width=3, border_radius=6)

# ------------------ Animator ------------------
class Animator:
    def __init__(self):
        self.segments = []
        self.cur_seg_i = 0
        self.cur_wp_i  = 0
        self.pos = None
        self.done = True
        self.last_draw_path = []

    def load(self, segments, start_pos=None):
        self.segments = segments or []
        self.cur_seg_i = 0
        self.cur_wp_i = 0
        self.done = len(self.segments) == 0
        if start_pos is None and self.segments and self.segments[0]["waypoints"]:
            self.pos = self.segments[0]["waypoints"][0]
        else:
            self.pos = start_pos
        self.last_draw_path = []

    def current_magnet_on(self):
        if self.done or not self.segments: return False
        return self.segments[self.cur_seg_i]["magnet_on"]

    def step(self):
        if self.done or not self.segments:
            return self.last_draw_path

        seg = self.segments[self.cur_seg_i]
        wps = seg["waypoints"]
        if not wps:
            self._advance_segment()
            return self.last_draw_path

        if self.pos is None:
            self.pos = wps[0]

        speed = DRAG_SPEED_PX if seg["magnet_on"] else TRAVEL_SPEED_PX

        target = wps[self.cur_wp_i]
        dx = target[0] - self.pos[0]
        dy = target[1] - self.pos[1]
        dist = math.hypot(dx, dy)

        if dist < 1e-3:
            if seg["magnet_on"]:
                self.last_draw_path.append((target[0], target[1]))
            self.cur_wp_i += 1
            if self.cur_wp_i >= len(wps):
                self._advance_segment()
            return self.last_draw_path

        step = min(speed, dist)
        nx = self.pos[0] + (dx / (dist + 1e-9)) * step
        ny = self.pos[1] + (dy / (dist + 1e-9)) * step
        self.pos = (nx, ny)

        if seg["magnet_on"]:
            if not self.last_draw_path:
                self.last_draw_path.append((nx, ny))
            else:
                lastx, lasty = self.last_draw_path[-1]
                if abs(nx - lastx) + abs(ny - lasty) > 0.5:
                    self.last_draw_path.append((nx, ny))

        return self.last_draw_path

    def _advance_segment(self):
        self.cur_seg_i += 1
        self.cur_wp_i = 0
        if self.cur_seg_i >= len(self.segments):
            self.done = True

# ------------------ Main App (with Mouse Drag) ------------------
def main():
    pygame.init()
    pygame.display.set_caption("PrinterChess Pathfinding Simulator — Drag to Move")
    screen = pygame.display.set_mode((WIN_W, WIN_H), flags=0)  # windowed

    # Fonts
    font_piece = pygame.font.SysFont("DejaVu Sans", int(SQUARE * 0.82))
    font_small = pygame.font.SysFont("DejaVu Sans", 16)
    font_ui    = pygame.font.SysFont("DejaVu Sans", 18)

    clock = pygame.time.Clock()

    board = chess.Board()
    init_grave_positions()
    animator = Animator()

    input_text = ""
    error_msg = ""
    running = True

    # Mouse drag state
    dragging = False
    drag_sq = None
    drag_glyph = None
    drag_pos = None
    selected_sq = None

    while running:
        dt = clock.tick(60)

        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False

            elif ev.type == pygame.MOUSEMOTION:
                if dragging:
                    drag_pos = ev.pos

            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                mx, my = ev.pos
                sq = mouse_to_square(mx, my)
                if sq is not None and animator.done:
                    piece = board.piece_at(sq)
                    if piece and piece.color == board.turn:
                        dragging = True
                        drag_sq = sq
                        selected_sq = sq
                        glyph = PIECE_CHARS[piece.piece_type][piece.color]
                        drag_glyph = font_piece.render(glyph, True, (15,15,15))
                        drag_pos = (mx, my)

            elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
                if dragging:
                    mx, my = ev.pos
                    drop_sq = mouse_to_square(mx, my)
                    dragging = False
                    selected_sq = None

                    if drop_sq is None or drop_sq == drag_sq:
                        drag_sq = None; drag_glyph = None; drag_pos = None
                    else:
                        mv = chess.Move(drag_sq, drop_sq)
                        piece = board.piece_at(drag_sq)
                        if piece and piece.piece_type == chess.PAWN and (chess.square_rank(drop_sq) in (0,7)):
                            mv = chess.Move.from_uci(chess.square_name(drag_sq) + chess.square_name(drop_sq) + "q")

                        if mv in board.legal_moves:
                            try:
                                # plan segments
                                if board.is_castling(mv):
                                    segments = plan_castling(board, mv)
                                    cap_color = None; cap_xy = None
                                elif board.is_capture(mv):
                                    segments, cap_color, cap_xy = plan_capture_sequence(board, mv)
                                else:
                                    segments = plan_normal_move(board, mv)
                                    cap_color = None; cap_xy = None

                                start_pos = segments[0]["waypoints"][0] if segments and segments[0]["waypoints"] else None
                                animator.load(segments, start_pos=start_pos)

                                if cap_xy is not None and cap_color is not None:
                                    if cap_color == chess.WHITE:
                                        captured_white.append(cap_xy)
                                    else:
                                        captured_black.append(cap_xy)

                                board.push(mv)

                            except Exception as e:
                                # Show a small message, don't crash the app
                                error_msg = f"Capture path error: {e}"
                        # clear drag sprites either way
                        drag_sq = None; drag_glyph = None; drag_pos = None

            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    running = False
                elif ev.key == pygame.K_BACKSPACE:
                    input_text = input_text[:-1]
                elif ev.key == pygame.K_RETURN:
                    move_str = input_text.strip().lower()
                    error_msg = ""
                    input_text = ""

                    try:
                        mv = chess.Move.from_uci(move_str)
                    except Exception:
                        error_msg = "Bad UCI. Try: e2e4, g1f3, e1g1, e7e8q"
                        continue

                    if mv not in board.legal_moves:
                        error_msg = "Illegal move in current position."
                        continue

                    try:
                        if board.is_castling(mv):
                            segments = plan_castling(board, mv)
                            cap_color = None; cap_xy = None
                        elif board.is_capture(mv):
                            segments, cap_color, cap_xy = plan_capture_sequence(board, mv)
                        else:
                            segments = plan_normal_move(board, mv)
                            cap_color = None; cap_xy = None

                        start_pos = segments[0]["waypoints"][0] if segments and segments[0]["waypoints"] else None
                        animator.load(segments, start_pos=start_pos)

                        if cap_xy is not None and cap_color is not None:
                            if cap_color == chess.WHITE:
                                captured_white.append(cap_xy)
                            else:
                                captured_black.append(cap_xy)

                        board.push(mv)

                    except Exception as e:
                        error_msg = f"Capture path error: {e}"

                else:
                    ch = ev.unicode
                    if ch and (ch.isalnum() or ch in "=- "):
                        input_text += ch.lower()

        # update animation
        current_path_points = animator.step()
        magnet_on = animator.current_magnet_on()
        magnet_pos = animator.pos if animator.pos else (MARGIN, BOARD_PIXELS - MARGIN)

        # draw
        screen.fill(COL_BG)
        draw_board(screen)
        draw_labels(screen, pygame.font.SysFont("DejaVu Sans", 16))
        if selected_sq is not None:
            draw_selection(screen, selected_sq)
        skip = drag_sq if dragging else None
        draw_pieces(screen, board, pygame.font.SysFont("DejaVu Sans", int(SQUARE * 0.82)),
                    skip_sq=skip, dragging_glyph=(drag_glyph if dragging else None),
                    drag_pos=(drag_pos if dragging else None))
        draw_graveyard(screen, pygame.font.SysFont("DejaVu Sans", 16))
        draw_path(screen, current_path_points)
        draw_magnet(screen, magnet_pos, magnet_on)
        draw_input_bar(screen, pygame.font.SysFont("DejaVu Sans", 18), input_text, error_msg)

        pygame.display.flip()

    pygame.quit()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("Error:", e)
        pygame.quit()
        sys.exit(1)
