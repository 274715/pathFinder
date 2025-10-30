#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, sys, shutil, threading, queue
import pygame, chess, chess.engine

# -------------------- Printer bridge --------------------
try:
    import chess_bridge  # must live next to this file
except Exception as e:
    chess_bridge = None
    print(f"[bridge] warning: chess_bridge import failed: {e}")

VERSION = "v3.5-menu-center+undo-phys+status-wrap"

# -------------------- Engine discovery --------------------
def discover_engine_path():
    for p in [
        os.environ.get("STOCKFISH"),
        "/usr/games/stockfish",
        "/usr/bin/stockfish",
        shutil.which("stockfish"),
        "/opt/homebrew/bin/stockfish",
        "/usr/local/bin/stockfish",
    ]:
        if p and os.path.exists(p):
            return p
    return None

ENGINE_PATH = discover_engine_path()
print(f"[engine] using: {ENGINE_PATH or 'NOT FOUND'}")

# -------------------- Logical canvas --------------------
BOARD_PIXELS = 640
UI_PAD       = 56
UI_HEIGHT    = 112
WIN_W, WIN_H = BOARD_PIXELS, BOARD_PIXELS + UI_PAD + UI_HEIGHT
MARGIN       = 40
SQUARE       = (BOARD_PIXELS - 2 * MARGIN) // 8

# -------------------- Colors --------------------
COL_BG     = (24, 24, 24)
COL_LIGHT  = (240, 217, 181)
COL_DARK   = (181, 136, 99)
COL_TEXT   = (230, 230, 230)
COL_BTN    = (62, 62, 62)
COL_BTN_H  = (92, 92, 92)
COL_ACC    = (180, 255, 180)
COL_DOT    = (120, 120, 120)
COL_SEL    = (112, 162, 255)
COL_HI     = (246, 246, 105, 110)
COL_CHECK  = (255, 80, 80, 140)
COL_OVER   = (16, 16, 16, 200)

DRAG_THRESH_PX = 6
MATE_LOSS_DELAY_MS = 2000

# -------------------- Fonts --------------------
def _render_has_glyphs(font):
    try:
        s = font.render("♔♕♖♗♘♙", True, (0, 0, 0))
        return s.get_width() > 0
    except Exception:
        return False

def _try_load_bundled_font(filename, size):
    here = os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(here, "assets", filename)
    if os.path.exists(p):
        try:
            f = pygame.font.Font(p, size)
            if _render_has_glyphs(f):
                return f
        except Exception:
            pass
    return None

def get_fonts():
    size_piece = int(SQUARE * 0.82)
    pygame.font.init()
    # Bundled first
    for ttf in ("FreeSerif.ttf", "DejaVuSans.ttf"):
        f = _try_load_bundled_font(ttf, size_piece)
        if f:
            return (
                f,
                pygame.font.SysFont(None, 18),
                pygame.font.SysFont(None, 22),
                pygame.font.SysFont(None, 42),
                True,
            )
    # System candidates
    for name in [
        "FreeSerif", "DejaVu Sans", "Noto Sans Symbols", "Noto Sans",
        "Arial Unicode MS", "Symbola", "Segoe UI Symbol", None
    ]:
        try:
            fp = pygame.font.SysFont(name, size_piece)
            if _render_has_glyphs(fp):
                return (
                    fp,
                    pygame.font.SysFont(name, 18),
                    pygame.font.SysFont(name, 22),
                    pygame.font.SysFont(name, 42, bold=False),
                    True,
                )
        except Exception:
            continue
    # Fallback
    base = pygame.font.SysFont(None, size_piece)
    return (
        base,
        pygame.font.SysFont(None, 18),
        pygame.font.SysFont(None, 22),
        pygame.font.SysFont(None, 42, bold=False),
        False,
    )

# -------------------- Piece glyphs --------------------
UNICODE = {
    chess.PAWN:   {chess.WHITE: "♙", chess.BLACK: "♟"},
    chess.KNIGHT: {chess.WHITE: "♘", chess.BLACK: "♞"},
    chess.BISHOP: {chess.WHITE: "♗", chess.BLACK: "♝"},
    chess.ROOK:   {chess.WHITE: "♖", chess.BLACK: "♜"},
    chess.QUEEN:  {chess.WHITE: "♕", chess.BLACK: "♛"},
    chess.KING:   {chess.WHITE: "♔", chess.BLACK: "♚"},
}
LETTER = {
    chess.PAWN:   {chess.WHITE: "P", chess.BLACK: "p"},
    chess.KNIGHT: {chess.WHITE: "N", chess.BLACK: "n"},
    chess.BISHOP: {chess.WHITE: "B", chess.BLACK: "b"},
    chess.ROOK:   {chess.WHITE: "R", chess.BLACK: "r"},
    chess.QUEEN:  {chess.WHITE: "Q", chess.BLACK: "q"},
    chess.KING:   {chess.WHITE: "K", chess.BLACK: "k"},
}

# -------------------- Rotation + scaling mapper --------------------
def norm_angle(a):
    try:
        a = int(a)
    except Exception:
        a = 0
    a = a % 360
    return {0:0,90:90,180:180,270:270}.get(a, 0)

class Mapper:
    """
    Maps physical screen coords <-> logical canvas coords with rotation + scale + letterboxing.
    Also provides a function to convert normalized FINGER coords -> physical pixels.
    """
    def __init__(self, screen_size, logical_size, angle_deg,
                 touch_swap_xy=False, touch_invert_x=False, touch_invert_y=False):
        self.sw, self.sh = screen_size
        self.lw, self.lh = logical_size
        self.angle = norm_angle(angle_deg)

        # optional touch transforms (for mismatched controllers)
        self.tswap = bool(int(touch_swap_xy))
        self.tix   = bool(int(touch_invert_x))
        self.tiy   = bool(int(touch_invert_y))

        # Size after rotation
        if self.angle in (0, 180):
            rw, rh = self.lw, self.lh
        else:
            rw, rh = self.lh, self.lw

        # Scale to fit, keep aspect
        scale = min(self.sw / rw, self.sh / rh)
        self.scale = scale
        self.dst_w, self.dst_h = int(round(rw * scale)), int(round(rh * scale))
        self.dst_x = (self.sw - self.dst_w) // 2
        self.dst_y = (self.sh - self.dst_h) // 2

        print(f"[mapper] angle={self.angle} scale={self.scale:.3f} dst={self.dst_x},{self.dst_y},{self.dst_w}x{self.dst_h} "
              f"touch swapXY={self.tswap} invX={self.tix} invY={self.tiy}")

    def finger_norm_to_phys(self, nx, ny):
        # Controller quirks first
        if self.tswap:
            nx, ny = ny, nx
        if self.tix:
            nx = 1.0 - nx
        if self.tiy:
            ny = 1.0 - ny
        nx = max(0.0, min(1.0, float(nx)))
        ny = max(0.0, min(1.0, float(ny)))
        px = int(round(nx * (self.sw - 1)))
        py = int(round(ny * (self.sh - 1)))
        return px, py

    def phys_to_logical(self, px, py):
        if px < self.dst_x or py < self.dst_y or px >= self.dst_x + self.dst_w or py >= self.dst_h:
            return None
        rx = (px - self.dst_x) / self.scale
        ry = (py - self.dst_y) / self.scale

        W, H = self.lw, self.lh
        if self.angle == 0:
            lx, ly = rx, ry
        elif self.angle == 90:   # CCW
            lx, ly = W - ry, rx
        elif self.angle == 180:
            lx, ly = W - rx, H - ry
        elif self.angle == 270:
            lx, ly = ry, H - rx
        else:
            lx, ly = rx, ry
        return (float(lx), float(ly))

    def blit_rotated_scaled(self, screen, logical_surface):
        surf = logical_surface
        if self.angle:
            surf = pygame.transform.rotate(surf, self.angle)
        if (surf.get_width(), surf.get_height()) != (self.dst_w, self.dst_h):
            surf = pygame.transform.smoothscale(surf, (self.dst_w, self.dst_h))
        screen.fill((0,0,0))
        screen.blit(surf, (self.dst_x, self.dst_y))

# -------------------- Geometry helpers --------------------
def board_to_screen_fr(file_i, rank_i, bottom_color_white):
    return (file_i, rank_i) if bottom_color_white else (7 - file_i, 7 - rank_i)

def screen_to_board_fr(sf, sr, bottom_color_white):
    return (sf, sr) if bottom_color_white else (7 - sf, 7 - sr)

def fr_to_xy(sf, sr):
    x = MARGIN + sf * SQUARE
    y = MARGIN + (7 - sr) * SQUARE
    return x, y

def mouse_to_board_square(mx, my, bottom_color_white):
    if not (MARGIN <= mx < MARGIN + 8 * SQUARE and MARGIN <= my < MARGIN + 8 * SQUARE):
        return None
    sf = (mx - MARGIN) // SQUARE
    sr_from_top = (my - MARGIN) // SQUARE
    sr = 7 - sr_from_top
    file_i, rank_i = screen_to_board_fr(sf, sr, bottom_color_white)
    return chess.square(int(file_i), int(rank_i))

# -------------------- Drawing --------------------
def draw_button(screen, rect, text, font, hovered=False):
    pygame.draw.rect(screen, COL_BTN_H if hovered else COL_BTN, rect, border_radius=10)
    label = font.render(text, True, COL_TEXT)
    screen.blit(label, (rect.centerx - label.get_width()//2, rect.centery - label.get_height()//2))

def draw_board_squares(screen):
    for sf in range(8):
        for sr in range(8):
            x, y = fr_to_xy(sf, sr)
            color = COL_DARK if (sf + sr) % 2 == 0 else COL_LIGHT
            pygame.draw.rect(screen, color, (x, y, SQUARE, SQUARE))

def draw_file_labels(screen, font_small, bottom_color_white):
    files = "abcdefgh" if bottom_color_white else "hgfedcba"
    for i, letter in enumerate(files):
        lx = MARGIN + i * SQUARE + SQUARE//2
        ly = BOARD_PIXELS - 14
        lab = font_small.render(letter, True, COL_TEXT)
        screen.blit(lab, (lx - lab.get_width()//2, ly))

def draw_rank_labels(screen, font_small, bottom_color_white):
    for sr in range(8):
        number = str(sr + 1) if bottom_color_white else str(8 - sr)
        lx = 12
        ly = MARGIN + (7 - sr) * SQUARE + SQUARE//2 - 8
        lab = font_small.render(number, True, COL_TEXT)
        screen.blit(lab, (lx, ly))

def draw_last_move(screen, move, bottom_color_white):
    if not move:
        return
    for sq in (move.from_square, move.to_square):
        fi = chess.square_file(sq); ri = chess.square_rank(sq)
        sf, sr = board_to_screen_fr(fi, ri, bottom_color_white)
        x, y = fr_to_xy(sf, sr)
        hi = pygame.Surface((SQUARE, SQUARE), pygame.SRCALPHA)
        hi.fill(COL_HI)
        screen.blit(hi, (x, y))

def draw_selection_outline(screen, sel_sq, bottom_color_white):
    if sel_sq is None:
        return
    fi = chess.square_file(sel_sq); ri = chess.square_rank(sel_sq)
    sf, sr = board_to_screen_fr(fi, ri, bottom_color_white)
    x, y = fr_to_xy(sf, sr)
    pygame.draw.rect(screen, COL_SEL, (x+2, y+2, SQUARE-4, SQUARE-4), width=3, border_radius=6)

def draw_legal_dots(screen, legal_targets, bottom_color_white):
    dot_r = max(6, SQUARE // 8)
    for tsq in list(legal_targets):
        try:
            fi = chess.square_file(tsq); ri = chess.square_rank(tsq)
            sf, sr = board_to_screen_fr(fi, ri, bottom_color_white)
            cx = MARGIN + sf * SQUARE + SQUARE // 2
            cy = MARGIN + (7 - sr) * SQUARE + SQUARE // 2
            pygame.draw.circle(screen, COL_DOT, (cx, cy), dot_r)
        except Exception:
            legal_targets.discard(tsq)

def draw_check_overlay(screen, board, bottom_color_white):
    if board.is_check():
        ksq = board.king(board.turn)
        if ksq is not None:
            kf = chess.square_file(ksq); kr = chess.square_rank(ksq)
            sf, sr = board_to_screen_fr(kf, kr, bottom_color_white)
            x, y = fr_to_xy(sf, sr)
            chk = pygame.Surface((SQUARE, SQUARE), pygame.SRCALPHA)
            chk.fill(COL_CHECK)
            screen.blit(chk, (x, y))

def draw_pieces(screen, board, font_piece, use_unicode, bottom_color_white, skip_sq=None):
    for sq in chess.SQUARES:
        if skip_sq is not None and sq == skip_sq:
            continue
        piece = board.piece_at(sq)
        if not piece:
            continue
        fi = chess.square_file(sq); ri = chess.square_rank(sq)
        sf, sr = board_to_screen_fr(fi, ri, bottom_color_white)
        x, y = fr_to_xy(sf, sr)
        glyph = UNICODE[piece.piece_type][piece.color] if use_unicode else LETTER[piece.piece_type][piece.color]
        surf  = font_piece.render(glyph, True, (15, 15, 15))
        screen.blit(surf, (x + (SQUARE - surf.get_width())//2, y + (SQUARE - surf.get_height())//2))

# -------------------- Moves --------------------
def try_make_move(board, from_sq, to_sq):
    if from_sq == to_sq: return False
    uci = chess.square_name(from_sq) + chess.square_name(to_sq)
    move = chess.Move.from_uci(uci)
    piece = board.piece_at(from_sq)
    if piece and piece.piece_type == chess.PAWN and chess.square_rank(to_sq) in (0, 7):
        move = chess.Move.from_uci(uci + "q")
    if move in board.legal_moves:
        board.push(move)
        print("move:", move.uci())
        return True
    return False

def undo_smart_pair(board, human_color_white):
    popped = []
    if board.move_stack:
        popped.append(board.pop())   # last (engine if it just moved)
    if board.turn != human_color_white and board.move_stack:
        popped.append(board.pop())   # also undo the human move
    return popped

# -------------------- Game over --------------------
def game_over_reason(board):
    if board.is_checkmate():
        winner = "White" if board.turn == chess.BLACK else "Black"
        result = "1-0" if winner == "White" else "0-1"
        return True, f"Checkmate — {winner} wins", result
    if board.is_stalemate(): return True, "Stalemate — draw", "1/2-1/2"
    if hasattr(board, "is_seventyfive_moves") and board.is_seventyfive_moves(): return True, "75-move rule — draw", "1/2-1/2"
    if hasattr(board, "is_fivefold_repetition") and board.is_fivefold_repetition(): return True, "Fivefold repetition — draw", "1/2-1/2"
    if board.is_insufficient_material(): return True, "Insufficient material — draw", "1/2-1/2"
    if board.is_repetition(3) or board.can_claim_threefold_repetition(): return True, "Threefold repetition — draw", "1/2-1/2"
    return False, "", "*"

def draw_game_over_overlay(screen, fonts, reason_text):
    _, _, font_ui, font_title, _ = fonts
    overlay = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
    overlay.fill(COL_OVER)
    screen.blit(overlay, (0,0))
    box_w, box_h = 520, 220
    rect = pygame.Rect((WIN_W - box_w)//2, (WIN_H - box_h)//2 - 20, box_w, box_h)
    pygame.draw.rect(screen, (40,40,44), rect, border_radius=12)
    pygame.draw.rect(screen, (70,70,74), rect, width=2, border_radius=12)

    title = font_title.render("Game Over", True, COL_TEXT)
    screen.blit(title, (rect.centerx - title.get_width()//2, rect.y + 18))

    reason = font_ui.render(reason_text, True, COL_ACC)
    screen.blit(reason, (rect.centerx - reason.get_width()//2, rect.y + 78))

    btn = pygame.Rect(rect.centerx - 100, rect.bottom - 70, 200, 48)
    pygame.draw.rect(screen, COL_BTN, btn, border_radius=10)
    label = font_ui.render("New Game", True, COL_TEXT)
    screen.blit(label, (btn.centerx - label.get_width()//2, btn.centery - label.get_height()//2))
    return btn

# -------------------- Tiny menu (centered, evenly spaced) --------------------
def show_menu_quick(mapper, screen, canvas, f_ui, f_title, cur_color, cur_diff):
    clock = pygame.time.Clock()
    color = cur_color
    diff  = cur_diff

    title_text = "Choose Color & Difficulty"
    title_h = f_title.get_height()

    color_btn_w, color_btn_h = 170, 56
    cell_w, cell_h = 60, 48
    start_btn_w, start_btn_h = 180, 56

    gap_y = 40  # vertical gap between rows

    # Grid dims
    gap_x, gap_grid_y = 16, 12
    grid_w = 4*cell_w + 3*gap_x
    grid_h = 2*cell_h + 1*gap_grid_y

    block_h = title_h + gap_y + color_btn_h + gap_y + grid_h + gap_y + start_btn_h
    top_y = (WIN_H - block_h) // 2

    title_pos_y = top_y

    color_y = title_pos_y + title_h + gap_y
    color_gap = 40
    white_btn = pygame.Rect(0, 0, color_btn_w, color_btn_h)
    black_btn = pygame.Rect(0, 0, color_btn_w, color_btn_h)
    white_btn.center = (WIN_W//2 - (color_btn_w//2 + color_gap//2), color_y + color_btn_h//2)
    black_btn.center = (WIN_W//2 + (color_btn_w//2 + color_gap//2), color_y + color_btn_h//2)

    grid_y = color_y + color_btn_h + gap_y
    grid_x0 = (WIN_W - grid_w)//2
    cells = []
    for r in range(2):
        for c in range(4):
            n = r*4 + c + 1
            rect = pygame.Rect(grid_x0 + c*(cell_w+gap_x), grid_y + r*(cell_h+gap_grid_y), cell_w, cell_h)
            cells.append((n, rect))

    start_btn = pygame.Rect((WIN_W - start_btn_w)//2, grid_y + grid_h + gap_y, start_btn_w, start_btn_h)

    while True:
        # draw
        canvas.fill((28,28,32))
        title = f_title.render(title_text, True, COL_TEXT)
        canvas.blit(title, (WIN_W//2 - title.get_width()//2, title_pos_y))

        # color buttons
        pygame.draw.rect(canvas, COL_BTN_H if color==chess.WHITE else COL_BTN, white_btn, border_radius=10)
        pygame.draw.rect(canvas, COL_BTN_H if color==chess.BLACK else COL_BTN, black_btn, border_radius=10)
        wlab = f_ui.render("White", True, COL_TEXT)
        blab = f_ui.render("Black", True, COL_TEXT)
        canvas.blit(wlab, (white_btn.centerx - wlab.get_width()//2, white_btn.centery - wlab.get_height()//2))
        canvas.blit(blab, (black_btn.centerx - blab.get_width()//2, black_btn.centery - blab.get_height()//2))

        # difficulty cells
        for n, rect in cells:
            pygame.draw.rect(canvas, COL_BTN_H if diff==n else COL_BTN, rect, border_radius=8)
            lab = f_ui.render(str(n), True, COL_TEXT)
            canvas.blit(lab, (rect.centerx - lab.get_width()//2, rect.centery - lab.get_height()//2))

        # start
        ready = color in (chess.WHITE, chess.BLACK) and (1 <= diff <= 8)
        pygame.draw.rect(canvas, (0,140,80) if ready else (60,60,60), start_btn, border_radius=10)
        slab = f_ui.render("Start", True, (255,255,255) if ready else (200,200,200))
        canvas.blit(slab, (start_btn.centerx - slab.get_width()//2, start_btn.centery - slab.get_height()//2))

        mapper.blit_rotated_scaled(screen, canvas)
        pygame.display.flip()
        clock.tick(60)

        # input
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                raise SystemExit
            pos = None
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                out = mapper.phys_to_logical(*ev.pos); pos = (int(out[0]), int(out[1])) if out else None
            elif ev.type == pygame.FINGERDOWN:
                px, py = mapper.finger_norm_to_phys(ev.x, ev.y)
                out = mapper.phys_to_logical(px, py); pos = (int(out[0]), int(out[1])) if out else None
            if not pos: continue
            mx, my = pos
            if white_btn.collidepoint(mx,my): color = chess.WHITE
            elif black_btn.collidepoint(mx,my): color = chess.BLACK
            else:
                for n, rect in cells:
                    if rect.collidepoint(mx,my): diff = n; break
                if start_btn.collidepoint(mx,my) and ready:
                    return color, diff

# -------------------- Engine worker --------------------
class EngineWorker(threading.Thread):
    def __init__(self, engine_path):
        super().__init__(daemon=True)
        self.engine_path = engine_path
        self.to_engine   = queue.Queue()
        self.to_ui       = queue.Queue()
        self._stopflag   = threading.Event()
        self._eng        = None

    def run(self):
        if not self.engine_path:
            self.to_ui.put(("error", "Engine path not found. Install Stockfish or set $STOCKFISH."))
            return
        try:
            self._eng = chess.engine.SimpleEngine.popen_uci(self.engine_path)
        except Exception as e:
            self.to_ui.put(("error", f"Engine start failed: {e}"))
            return

        while not self._stopflag.is_set():
            try:
                msg = self.to_engine.get(timeout=0.1)
            except queue.Empty:
                continue
            if not msg:
                continue
            if msg[0] == "play":
                _, req_id, fen, skill, think_time = msg
                try:
                    try:
                        self._eng.configure({"Skill Level": int(skill)})
                    except Exception:
                        pass
                    board = chess.Board(fen)
                    limit = chess.engine.Limit(time=think_time)
                    result = self._eng.play(board, limit)
                    mv = result.move
                    self.to_ui.put(("bestmove", req_id, mv.uci() if mv else None))
                except Exception as e:
                    self.to_ui.put(("error", f"Engine play failed: {e}"))
            elif msg[0] == "quit":
                break

        try:
            if self._eng is not None:
                self._eng.quit()
        except Exception:
            pass

    def stop(self):
        self._stopflag.set()
        self.to_engine.put(("quit",))

# -------------------- Difficulty table --------------------
DIFF_TABLE = {
    1: (1,  0.12), 2: (2,  0.18), 3: (3,  0.25), 4: (4,  0.35),
    5: (5,  0.45), 6: (6,  0.55), 7: (12, 1.00), 8: (14, 1.80),
}

# -------------------- Helpers: safe bottom status drawing --------------------
BOTTOM_PAD_Y = 10
BOTTOM_LINE_GAP = 6
SAFE_GAP = 12

def truncate_to_width(font, text, max_w):
    """Truncate with ellipsis if needed to fit max_w."""
    if font.size(text)[0] <= max_w:
        return text
    ell = "…"
    # crude but effective: binary shorten
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi) // 2
        candidate = text[:mid] + ell
        if font.size(candidate)[0] <= max_w:
            lo = mid + 1
        else:
            hi = mid
    return text[:max(0, lo - 1)] + ell

def draw_bottom_status(canvas, font_ui, left_text, right_text):
    """Draws left & right status; moves right_text to second line if overlap."""
    y1 = BOARD_PIXELS + UI_PAD + UI_HEIGHT - font_ui.get_height() - BOTTOM_PAD_Y
    y2 = y1 - font_ui.get_height() - BOTTOM_LINE_GAP

    # Render surfaces (we may re-render after truncation)
    left_srf = font_ui.render(left_text, True, COL_ACC)
    right_srf = font_ui.render(right_text, True, COL_TEXT)

    # Compute positions
    left_x = MARGIN
    left_right = left_x + left_srf.get_width()

    right_x = WIN_W - MARGIN - right_srf.get_width()

    # If they'd collide, try to move right_text to the second line.
    if right_x <= left_right + SAFE_GAP:
        # keep right aligned on second line
        max_right_w = WIN_W - 2*MARGIN
        # Truncate right line if somehow wider than full width minus margins
        if right_srf.get_width() > max_right_w:
            right_text = truncate_to_width(font_ui, right_text, max_right_w)
            right_srf = font_ui.render(right_text, True, COL_TEXT)
        canvas.blit(left_srf, (left_x, y1))
        canvas.blit(right_srf, (WIN_W - MARGIN - right_srf.get_width(), y2))
    else:
        # Fits on one line; also make sure left fits within leftover space (rare)
        max_left_w = right_x - left_x - SAFE_GAP
        if left_srf.get_width() > max_left_w:
            left_text = truncate_to_width(font_ui, left_text, max_left_w)
            left_srf = font_ui.render(left_text, True, COL_ACC)
        canvas.blit(left_srf, (left_x, y1))
        canvas.blit(right_srf, (right_x, y1))

# -------------------- Main --------------------
def main():
    pygame.init()
    pygame.mouse.set_visible(False)  # hide cursor for touch kiosk
    pygame.display.set_caption(f"Virtual Chessboard — {VERSION}")

    # Fullscreen
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    info = pygame.display.Info()
    screen_size = (info.current_w, info.current_h)
    print(f"[screen] {screen_size[0]}x{screen_size[1]}")

    # Rotation + touch envs
    app_rotate   = norm_angle(os.environ.get("APP_ROTATE", "90"))
    t_swap_xy    = os.environ.get("TOUCH_SWAP_XY", "0")
    t_invert_x   = os.environ.get("TOUCH_INVERT_X", "0")
    t_invert_y   = os.environ.get("TOUCH_INVERT_Y", "0")

    mapper = Mapper(screen_size, (WIN_W, WIN_H), app_rotate,
                    touch_swap_xy=t_swap_xy, touch_invert_x=t_invert_x, touch_invert_y=t_invert_y)
    canvas = pygame.Surface((WIN_W, WIN_H)).convert_alpha()

    # Fonts
    f_piece, f_small, f_ui, f_title, unicode_ok = get_fonts()

    # Engine
    worker = EngineWorker(ENGINE_PATH)
    worker.start()

    # Home the printer (best-effort)
    if chess_bridge is not None:
        try:
            print("[bridge] homing X/Y…")
            chess_bridge.home_xy()
        except Exception as e:
            print(f"[bridge] home_xy error: {e}")

    clock = pygame.time.Clock()

    # ---- Main menu first ----
    bottom_color, difficulty = show_menu_quick(mapper, screen, canvas, f_ui, f_title, chess.WHITE, 3)

    while True:
        # New game
        board = chess.Board()
        human_color  = bottom_color
        engine_color = not human_color
        skill, think_time = DIFF_TABLE.get(difficulty, (5, 0.45))

        # Track hardware moves in order to undo physically
        hw_moves = []  # list of (from_alg, to_alg) we sent to printer in this game

        selected_sq   = None
        legal_targets = set()
        dragging      = False
        drag_from_sq  = None
        drag_surface  = None
        drag_offset   = (0, 0)
        press_pos     = None
        last_move     = None

        # Buttons
        btn_w, btn_h = 120, 44
        gap = 16
        UI_Y = BOARD_PIXELS + UI_PAD
        btn_undo  = pygame.Rect(MARGIN, UI_Y + 8, btn_w, btn_h)
        btn_reset = pygame.Rect(MARGIN + btn_w + gap, UI_Y + 8, btn_w, btn_h)

        # Over state
        is_over = False
        over_reason = ""
        over_btn_rect = None
        result_str = "*"
        over_announced = False
        pending_game_over_until = None
        pending_over_reason = ""
        pending_result_str = "*"

        # Engine kickoff if human picked Black
        req_id = 0
        waiting_for_engine = False
        engine_error_text = ""
        if board.turn == engine_color and not is_over:
            req_id += 1
            waiting_for_engine = True
            worker.to_engine.put(("play", req_id, board.fen(), skill, think_time))

        running = True
        while running:
            clock.tick(60)

            # Engine results
            try:
                while True:
                    kind, *payload = worker.to_ui.get_nowait()
                    if kind == "bestmove":
                        resp_req_id, uci = payload
                        if resp_req_id == req_id and waiting_for_engine and not is_over and uci:
                            waiting_for_engine = False
                            move = chess.Move.from_uci(uci)
                            if move in board.legal_moves:
                                board.push(move)
                                last_move = move
                                print("engine_move:", uci)
                                if chess_bridge is not None:
                                    try:
                                        frm = chess.square_name(move.from_square)
                                        to  = chess.square_name(move.to_square)
                                        chess_bridge.move_piece(frm, to)
                                        hw_moves.append((frm, to))
                                    except Exception as e:
                                        print(f"[bridge] engine move error: {e}")
                    elif kind == "error":
                        engine_error_text = payload[0]
                        print("[engine]", engine_error_text)
                        waiting_for_engine = False
            except queue.Empty:
                pass

            # Game over?
            now_ms = pygame.time.get_ticks()
            if not is_over:
                end_now, reason_text, result_text = game_over_reason(board)
                if end_now:
                    if board.is_checkmate():
                        winner_color = chess.BLACK if board.turn == chess.WHITE else chess.WHITE
                        if winner_color != human_color:
                            if pending_game_over_until is None:
                                pending_game_over_until = now_ms + MATE_LOSS_DELAY_MS
                                pending_over_reason = reason_text
                                pending_result_str = result_text
                        else:
                            is_over = True; over_reason = reason_text; result_str = result_text
                    else:
                        is_over = True; over_reason = reason_text; result_str = result_text

            if not is_over and pending_game_over_until is not None and now_ms >= pending_game_over_until:
                is_over = True; over_reason = pending_over_reason; result_str = pending_result_str

            if is_over and not over_announced:
                print(f'end_game reason="{over_reason}" result={result_str}')
                over_announced = True

            # ---------- INPUT ----------
            def handle_press(mx, my):
                nonlocal press_pos, selected_sq, legal_targets, dragging, drag_from_sq, drag_surface, drag_offset, running, bottom_color, difficulty, hw_moves
                press_pos = (mx, my)

                # Undo
                if btn_undo.collidepoint(mx, my):
                    popped = undo_smart_pair(board, human_color)
                    for m in popped:
                        print("undo:", m.uci())
                        # Physically reverse the move if we had sent it
                        if chess_bridge is not None and hw_moves:
                            try:
                                last_hw_from, last_hw_to = hw_moves.pop()  # last physical move
                                chess_bridge.move_piece(last_hw_to, last_hw_from)  # reverse it
                            except Exception as e:
                                print(f"[bridge] undo reverse error: {e}")
                    # cancel any pending engine result
                    nonlocal req_id, waiting_for_engine
                    req_id += 1; waiting_for_engine = False
                    selected_sq = None; legal_targets.clear(); dragging = False
                    drag_from_sq = None; drag_surface = None
                    return

                # Reset -> back to menu (not just recenter)
                if btn_reset.collidepoint(mx, my):
                    print("reset -> menu")
                    # open menu, then re-seed new game params
                    bottom_color_new, difficulty_new = show_menu_quick(mapper, screen, canvas, f_ui, f_title, bottom_color, difficulty)
                    bottom_color = bottom_color_new
                    difficulty   = difficulty_new
                    running = False  # break inner loop -> start new game with new settings
                    return

                if is_over:
                    if over_btn_rect and over_btn_rect.collidepoint(mx, my):
                        print("new game -> menu")
                        bottom_color_new, difficulty_new = show_menu_quick(mapper, screen, canvas, f_ui, f_title, bottom_color, difficulty)
                        bottom_color = bottom_color_new
                        difficulty   = difficulty_new
                        running = False
                    return

                human_turn_and_ready = (board.turn == human_color and not waiting_for_engine)
                if not human_turn_and_ready: return

                sq = mouse_to_board_square(mx, my, human_color)
                if sq is None:
                    selected_sq = None; legal_targets.clear(); press_pos = None
                else:
                    piece = board.piece_at(sq)
                    if piece and piece.color == board.turn:
                        selected_sq = sq
                        legal_targets = {m.to_square for m in board.legal_moves if m.from_square == sq}
                        dragging = False; drag_from_sq = None; drag_surface = None
                    else:
                        if selected_sq is None:
                            legal_targets.clear(); press_pos = None

            def handle_drag(mx, my):
                nonlocal dragging, drag_from_sq, drag_surface, drag_offset
                human_turn_and_ready = (board.turn == human_color and not waiting_for_engine)
                if not human_turn_and_ready or not press_pos or selected_sq is None:
                    return
                dx = mx - press_pos[0]; dy = my - press_pos[1]
                if not dragging and (dx*dx + dy*dy) >= (DRAG_THRESH_PX*DRAG_THRESH_PX):
                    dragging = True; drag_from_sq = selected_sq
                    piece = board.piece_at(drag_from_sq)
                    if piece:
                        glyph = UNICODE[piece.piece_type][piece.color] if unicode_ok else LETTER[piece.piece_type][piece.color]
                        drag_surface = f_piece.render(glyph, True, (15,15,15))
                        fi = chess.square_file(drag_from_sq); ri = chess.square_rank(drag_from_sq)
                        sf, sr = board_to_screen_fr(fi, ri, human_color); bx, by = fr_to_xy(sf, sr)
                        gx = bx + (SQUARE - drag_surface.get_width()) // 2
                        gy = by + (SQUARE - drag_surface.get_height()) // 2
                        drag_offset = (press_pos[0] - gx, press_pos[1] - gy)

            def handle_release(mx, my):
                nonlocal dragging, drag_from_sq, drag_surface, selected_sq, legal_targets, last_move, req_id, waiting_for_engine
                made_move = False
                human_turn_and_ready = (board.turn == human_color and not waiting_for_engine)
                if not human_turn_and_ready:
                    return

                if dragging and drag_from_sq is not None:
                    drop_sq = mouse_to_board_square(mx, my, human_color)
                    try_sq = drop_sq if drop_sq is not None else drag_from_sq
                    if try_sq != drag_from_sq and try_make_move(board, drag_from_sq, try_sq):
                        last_move = board.move_stack[-1] if board.move_stack else None
                        made_move = True
                    dragging = False; drag_from_sq = None; drag_surface = None
                    selected_sq = None; legal_targets.clear()
                else:
                    sq = mouse_to_board_square(mx, my, human_color)
                    if sq is not None and selected_sq is not None and sq != selected_sq:
                        if try_make_move(board, selected_sq, sq):
                            last_move = board.move_stack[-1] if board.move_stack else None
                            made_move = True
                            selected_sq = None; legal_targets.clear()
                        else:
                            p2 = board.piece_at(sq)
                            if p2 and p2.color == board.turn:
                                selected_sq = sq
                                legal_targets = {m.to_square for m in board.legal_moves if m.from_square == sq}

                if made_move:
                    if chess_bridge is not None and last_move is not None:
                        try:
                            frm = chess.square_name(last_move.from_square)
                            to  = chess.square_name(last_move.to_square)
                            chess_bridge.move_piece(frm, to)
                            hw_moves.append((frm, to))
                        except Exception as e:
                            print(f"[bridge] human move error: {e}")

                    end_now, reason_text, result_text = game_over_reason(board)
                    if end_now:
                        if board.is_checkmate():
                            winner_color = chess.BLACK if board.turn == chess.WHITE else chess.WHITE
                            if winner_color != human_color:
                                if pending_game_over_until is None:
                                    pending_game_over_until = pygame.time.get_ticks() + MATE_LOSS_DELAY_MS
                                    pending_over_reason = reason_text
                                    pending_result_str = result_text
                            else:
                                nonlocal is_over, over_reason, result_str
                                is_over = True; over_reason = reason_text; result_str = result_text
                        else:
                            is_over = True; over_reason = reason_text; result_str = result_text
                    else:
                        req_id += 1; waiting_for_engine = True
                        worker.to_engine.put(("play", req_id, board.fen(), skill, think_time))

            # Read events (mouse + finger)
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    raise SystemExit

                if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    out = mapper.phys_to_logical(*ev.pos)
                    if out: handle_press(int(out[0]), int(out[1]))

                elif ev.type == pygame.MOUSEMOTION:
                    buttons = pygame.mouse.get_pressed(num_buttons=3)
                    if buttons[0]:
                        out = mapper.phys_to_logical(*ev.pos)
                        if out: handle_drag(int(out[0]), int(out[1]))

                elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
                    out = mapper.phys_to_logical(*ev.pos)
                    if out: handle_release(int(out[0]), int(out[1]))

                elif ev.type == pygame.FINGERDOWN:
                    px, py = mapper.finger_norm_to_phys(ev.x, ev.y)
                    out = mapper.phys_to_logical(px, py)
                    if out: handle_press(int(out[0]), int(out[1]))

                elif ev.type == pygame.FINGERMOTION:
                    px, py = mapper.finger_norm_to_phys(ev.x, ev.y)
                    out = mapper.phys_to_logical(px, py)
                    if out: handle_drag(int(out[0]), int(out[1]))

                elif ev.type == pygame.FINGERUP:
                    px, py = mapper.finger_norm_to_phys(ev.x, ev.y)
                    out = mapper.phys_to_logical(px, py)
                    if out: handle_release(int(out[0]), int(out[1]))

            # ---------- DRAW ----------
            canvas.fill(COL_BG)
            draw_board_squares(canvas)
            draw_last_move(canvas, last_move, human_color)
            draw_selection_outline(canvas, selected_sq, human_color)
            draw_legal_dots(canvas, legal_targets, human_color)
            draw_check_overlay(canvas, board, human_color)

            skip_sq = drag_from_sq if dragging else None
            draw_pieces(canvas, board, f_piece, unicode_ok, human_color, skip_sq=skip_sq)

            # Drag preview
            phys_mouse = pygame.mouse.get_pos()
            lpos = mapper.phys_to_logical(*phys_mouse)
            if dragging and drag_surface is not None and lpos:
                mx, my = int(lpos[0]), int(lpos[1])
                canvas.blit(drag_surface, (mx - drag_offset[0], my - drag_offset[1]))

            draw_file_labels(canvas, f_small, human_color)
            draw_rank_labels(canvas, f_small, human_color)

            pygame.draw.rect(canvas, (36,36,36), (0, BOARD_PIXELS + UI_PAD, WIN_W, UI_HEIGHT))

            # Hover states from logical cursor (okay if None on pure touch)
            hover_undo = hover_reset = False
            if lpos:
                mmx, mmy = int(lpos[0]), int(lpos[1])
                hover_undo  = btn_undo.collidepoint(mmx, mmy)
                hover_reset = btn_reset.collidepoint(mmx, mmy)

            draw_button(canvas, btn_undo,  "Undo",  f_ui, hover_undo)
            draw_button(canvas, btn_reset, "Reset", f_ui, hover_reset)

            # ------------ Non-overlapping bottom status ------------
            info_left  = f"Color: {'White' if human_color == chess.WHITE else 'Black'}  |  Difficulty: {difficulty}"
            if engine_error_text:
                turn_txt = "Engine error"
            elif board.turn == engine_color and not is_over and waiting_for_engine:
                # keep same string, just fix layout; you mentioned 'engien' typo — leaving proper spelling here
                turn_txt = "Engine thinking…"
            else:
                turn_txt = "White to move" if board.turn == chess.WHITE else "Black to move"

            draw_bottom_status(canvas, f_ui, info_left, turn_txt)
            # -------------------------------------------------------

            over_btn_rect = None
            if is_over:
                over_btn_rect = draw_game_over_overlay(canvas, (f_piece, f_small, f_ui, f_title, unicode_ok), over_reason)

            mapper.blit_rotated_scaled(screen, canvas)
            pygame.display.flip()

        # loop ended by Reset->Menu or GameOver->Menu
        bottom_color, difficulty = bottom_color, difficulty  # keep most recent values and show menu again
        bottom_color, difficulty = show_menu_quick(mapper, screen, canvas, f_ui, f_title, bottom_color, difficulty)

if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        pass
