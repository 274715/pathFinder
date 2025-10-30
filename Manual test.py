import sys
import pygame
import chess

VERSION = "v1.4-hardreset"
print(f"[virtual_board {VERSION}] loaded from {__file__}")

# ============================================================
#                       CONFIG / THEME
# ============================================================

BOARD_PIXELS = 640                 # board drawing area (square)
UI_HEIGHT    = 96                  # bottom bar height
UI_PAD       = 44                  # gap below board so labels aren't covered
WIN_W, WIN_H = BOARD_PIXELS, BOARD_PIXELS + UI_PAD + UI_HEIGHT
MARGIN       = 40                  # inner padding around board
SQUARE       = (BOARD_PIXELS - 2 * MARGIN) // 8

# Colors
COL_BG     = (24, 24, 24)
COL_LIGHT  = (240, 217, 181)
COL_DARK   = (181, 136, 99)
COL_TEXT   = (230, 230, 230)
COL_BTN    = (62, 62, 62)
COL_BTN_H  = (92, 92, 92)
COL_ACC    = (180, 255, 180)
COL_DOT    = (120, 120, 120)        # legal move dots
COL_SEL    = (112, 162, 255)        # selection outline
COL_HI     = (246, 246, 105, 110)   # last-move highlight (alpha)
COL_CHECK  = (255, 80, 80, 140)     # king-in-check overlay (alpha)
COL_DIM    = (160, 160, 160)
COL_OVER   = (16, 16, 16, 200)      # dark overlay for game over modal

# Drag behavior
DRAG_THRESH_PX = 6   # start dragging only if mouse moves this many pixels while held

# Unicode glyphs for pieces; will fall back to letters if needed
UNICODE = {
    chess.PAWN:   {chess.WHITE: "♙", chess.BLACK: "♟"},
    chess.KNIGHT: {chess.WHITE: "♘", chess.BLACK: "♞"},
    chess.BISHOP: {chess.WHITE: "♗", chess.BLACK: "♝"},
    chess.ROOK:   {chess.WHITE: "♖", chess.BLACK: "♜"},
    chess.QUEEN:  {chess.WHITE: "♕", chess.BLACK: "♛"},
    chess.KING:   {chess.WHITE: "♔", chess.BLACK: "♚"},
}
LETTER = {  # fallback letters if glyphs unavailable
    chess.PAWN:   {chess.WHITE: "P", chess.BLACK: "p"},
    chess.KNIGHT: {chess.WHITE: "N", chess.BLACK: "n"},
    chess.BISHOP: {chess.WHITE: "B", chess.BLACK: "b"},
    chess.ROOK:   {chess.WHITE: "R", chess.BLACK: "r"},
    chess.QUEEN:  {chess.WHITE: "Q", chess.BLACK: "q"},
    chess.KING:   {chess.WHITE: "K", chess.BLACK: "k"},
}

# ============================================================
#                        FONT HELPERS
# ============================================================

def get_fonts():
    """
    Return (piece_font, small_font, ui_font, title_font, has_unicode).
    Title font slightly larger, non-bold for sharper rendering.
    """
    candidates = ["Apple Symbols", "Arial Unicode MS", "DejaVu Sans", None]  # None = default
    for name in candidates:
        try:
            f_piece = pygame.font.SysFont(name, int(SQUARE * 0.82))
            if f_piece.render("♔♕♖♗♘♙", True, (0,0,0)).get_width() > 0:
                return (
                    f_piece,
                    pygame.font.SysFont(name, 18),
                    pygame.font.SysFont(name, 22),
                    pygame.font.SysFont(name, 42, bold=False),
                    True,
                )
        except Exception:
            pass
    base = pygame.font.SysFont(None, int(SQUARE * 0.82))
    return base, pygame.font.SysFont(None, 18), pygame.font.SysFont(None, 22), pygame.font.SysFont(None, 42, bold=False), False

# ============================================================
#                ORIENTATION / GEOMETRY HELPERS
# ============================================================

def board_to_screen_fr(file_i: int, rank_i: int, bottom_color: bool):
    if bottom_color == chess.WHITE:
        sf, sr = file_i, rank_i
    else:
        sf, sr = 7 - file_i, 7 - rank_i
    return sf, sr

def screen_to_board_fr(sf: int, sr: int, bottom_color: bool):
    if bottom_color == chess.WHITE:
        file_i, rank_i = sf, sr
    else:
        file_i, rank_i = 7 - sf, 7 - sr
    return file_i, rank_i

def fr_to_xy(sf: int, sr: int):
    x = MARGIN + sf * SQUARE
    y = MARGIN + (7 - sr) * SQUARE
    return x, y

def mouse_to_board_square(mx: int, my: int, bottom_color: bool):
    if not (MARGIN <= mx < MARGIN + 8 * SQUARE and MARGIN <= my < MARGIN + 8 * SQUARE):
        return None
    sf = (mx - MARGIN) // SQUARE
    sr_from_top = (my - MARGIN) // SQUARE
    sr = 7 - sr_from_top
    file_i, rank_i = screen_to_board_fr(sf, sr, bottom_color)
    return chess.square(file_i, rank_i)

# ============================================================
#                         UI HELPERS
# ============================================================

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

def draw_file_labels(screen, font_small, bottom_color):
    files = "abcdefgh" if bottom_color == chess.WHITE else "hgfedcba"
    for i, letter in enumerate(files):
        lx = MARGIN + i * SQUARE + SQUARE//2
        ly = BOARD_PIXELS - 14
        lab = font_small.render(letter, True, COL_TEXT)
        screen.blit(lab, (lx - lab.get_width()//2, ly))

def draw_rank_labels(screen, font_small, bottom_color):
    for sr in range(8):
        number = str(sr + 1) if bottom_color == chess.WHITE else str(8 - sr)
        lx = 12
        ly = MARGIN + (7 - sr) * SQUARE + SQUARE//2 - 8
        lab = font_small.render(number, True, COL_TEXT)
        screen.blit(lab, (lx, ly))

def draw_last_move(screen, move, bottom_color):
    if not move:
        return
    for sq in (move.from_square, move.to_square):
        fi = chess.square_file(sq); ri = chess.square_rank(sq)
        sf, sr = board_to_screen_fr(fi, ri, bottom_color)
        x, y = fr_to_xy(sf, sr)
        hi = pygame.Surface((SQUARE, SQUARE), pygame.SRCALPHA)
        hi.fill(COL_HI)
        screen.blit(hi, (x, y))

def draw_selection_outline(screen, sel_sq, bottom_color):
    if sel_sq is None:
        return
    fi = chess.square_file(sel_sq); ri = chess.square_rank(sel_sq)
    sf, sr = board_to_screen_fr(fi, ri, bottom_color)
    x, y = fr_to_xy(sf, sr)
    pygame.draw.rect(screen, COL_SEL, (x+2, y+2, SQUARE-4, SQUARE-4), width=3, border_radius=6)

def draw_legal_dots(screen, legal_targets, bottom_color):
    dot_r = max(6, SQUARE // 8)
    for tsq in list(legal_targets):
        try:
            fi = chess.square_file(tsq); ri = chess.square_rank(tsq)
            sf, sr = board_to_screen_fr(fi, ri, bottom_color)
            cx = MARGIN + sf * SQUARE + SQUARE // 2
            cy = MARGIN + (7 - sr) * SQUARE + SQUARE // 2
            pygame.draw.circle(screen, COL_DOT, (cx, cy), dot_r)
        except Exception:
            legal_targets.discard(tsq)

def draw_check_overlay(screen, board, bottom_color):
    if board.is_check():
        ksq = board.king(board.turn)
        if ksq is not None:
            kf = chess.square_file(ksq); kr = chess.square_rank(ksq)
            sf, sr = board_to_screen_fr(kf, kr, bottom_color)
            x, y = fr_to_xy(sf, sr)
            chk = pygame.Surface((SQUARE, SQUARE), pygame.SRCALPHA)
            chk.fill(COL_CHECK)
            screen.blit(chk, (x, y))

def draw_pieces(screen, board, font_piece, has_unicode, bottom_color, skip_sq=None):
    for sq in chess.SQUARES:
        if skip_sq is not None and sq == skip_sq:
            continue
        piece = board.piece_at(sq)
        if not piece:
            continue
        fi = chess.square_file(sq); ri = chess.square_rank(sq)
        sf, sr = board_to_screen_fr(fi, ri, bottom_color)
        x, y = fr_to_xy(sf, sr)
        glyph = UNICODE[piece.piece_type][piece.color] if has_unicode else LETTER[piece.piece_type][piece.color]
        surf  = font_piece.render(glyph, True, (15, 15, 15))
        screen.blit(surf, (x + (SQUARE - surf.get_width())//2,
                           y + (SQUARE - surf.get_height())//2))

def try_make_move(board, from_sq, to_sq):
    if from_sq == to_sq:
        return False
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

# ============================================================
#                 GAME OVER REASON / OVERLAY
# ============================================================

def game_over_reason(board: chess.Board):
    """
    Returns (is_over, reason_text, result_str)
    result_str is '1-0', '0-1', or '1/2-1/2'
    """
    if board.is_checkmate():
        winner = "White" if board.turn == chess.BLACK else "Black"
        result = "1-0" if winner == "White" else "0-1"
        return True, f"Checkmate — {winner} wins", result
    if board.is_stalemate():
        return True, "Stalemate — draw", "1/2-1/2"
    if hasattr(board, "is_seventyfive_moves") and board.is_seventyfive_moves():
        return True, "75-move rule — draw", "1/2-1/2"
    if hasattr(board, "is_fivefold_repetition") and board.is_fivefold_repetition():
        return True, "Fivefold repetition — draw", "1/2-1/2"
    if board.is_insufficient_material():
        return True, "Insufficient material — draw", "1/2-1/2"
    if board.is_repetition(3) or board.can_claim_threefold_repetition():
        return True, "Threefold repetition — draw", "1/2-1/2"
    return False, "", "*"

def draw_game_over_overlay(screen, fonts, reason_text):
    _, font_small, font_ui, font_title, _ = fonts
    overlay = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
    overlay.fill(COL_OVER)
    screen.blit(overlay, (0, 0))

    box_w, box_h = 520, 220
    rect = pygame.Rect((WIN_W - box_w)//2, (WIN_H - box_h)//2 - 20, box_w, box_h)
    pygame.draw.rect(screen, (40, 40, 44), rect, border_radius=12)
    pygame.draw.rect(screen, (70, 70, 74), rect, width=2, border_radius=12)

    title = font_title.render("Game Over", True, COL_TEXT)
    screen.blit(title, (rect.centerx - title.get_width()//2, rect.y + 18))

    reason = font_ui.render(reason_text, True, COL_ACC)
    screen.blit(reason, (rect.centerx - reason.get_width()//2, rect.y + 78))

    btn = pygame.Rect(rect.centerx - 100, rect.bottom - 70, 200, 48)
    pygame.draw.rect(screen, COL_BTN, btn, border_radius=10)
    label = font_ui.render("New Game", True, COL_TEXT)
    screen.blit(label, (btn.centerx - label.get_width()//2, btn.centery - label.get_height()//2))
    return btn

# ============================================================
#                      MENU (CENTERED)
# ============================================================

def show_menu(screen, fonts):
    _, _, font_ui, font_title, _ = fonts
    clock = pygame.time.Clock()

    w, h = WIN_W, WIN_H
    cx = w // 2

    title_text = "Choose Color & Difficulty"
    title_surf = font_title.render(title_text, True, COL_TEXT)
    title_h    = title_surf.get_height()

    btn_w, btn_h = 180, 56
    v_gap_small  = 12
    v_gap_med    = 24
    v_gap_big    = 28

    diff_bw, diff_bh, diff_col_gap, diff_row_gap = 60, 48, 14, 12
    diff_cols, diff_rows = 4, 2
    grid_w = diff_cols * diff_bw + (diff_cols - 1) * diff_col_gap
    grid_h = diff_rows * diff_bh + (diff_rows - 1) * diff_row_gap

    total_h = (title_h + v_gap_med + btn_h + v_gap_small + btn_h +
               v_gap_med + grid_h + v_gap_big + btn_h)
    top_y = max(20, (h - total_h) // 2)

    title_pos = (int(cx - title_surf.get_width() // 2), int(top_y))

    y = top_y + title_h + v_gap_med
    white_btn = pygame.Rect(cx - btn_w // 2, int(y), btn_w, btn_h)

    y += btn_h + v_gap_small
    black_btn = pygame.Rect(cx - btn_w // 2, int(y), btn_w, btn_h)

    y += btn_h + v_gap_med
    diff_btns = []
    grid_x0 = cx - grid_w // 2
    row1_y = int(y)
    for i in range(4):
        rx = grid_x0 + i * (diff_bw + diff_col_gap)
        diff_btns.append((i + 1, pygame.Rect(rx, row1_y, diff_bw, diff_bh)))
    row2_y = row1_y + diff_bh + diff_row_gap
    for i in range(4):
        rx = grid_x0 + i * (diff_bw + diff_col_gap)
        diff_btns.append((i + 5, pygame.Rect(rx, row2_y, diff_bw, diff_bh)))

    y = row2_y + diff_bh + v_gap_big
    start_btn = pygame.Rect(cx - btn_w // 2, int(y), btn_w, btn_h)

    chosen_color = None
    chosen_diff  = None

    while True:
        mx, my = pygame.mouse.get_pos()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit(0)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if white_btn.collidepoint(mx, my):
                    chosen_color = chess.WHITE
                elif black_btn.collidepoint(mx, my):
                    chosen_color = chess.BLACK
                else:
                    for lvl, rect in diff_btns:
                        if rect.collidepoint(mx, my):
                            chosen_diff = lvl
                            break
                    if start_btn.collidepoint(mx, my) and chosen_color is not None and chosen_diff is not None:
                        color_str = "white" if chosen_color == chess.WHITE else "black"
                        print(f"new_game color={color_str} difficulty={chosen_diff}")
                        return chosen_color, chosen_diff

        screen.fill((28, 28, 32))
        screen.blit(title_surf, title_pos)

        def draw_choice(rect, label, active):
            pygame.draw.rect(screen, COL_BTN_H if active else COL_BTN, rect, border_radius=10)
            lab = font_ui.render(label, True, COL_TEXT)
            screen.blit(lab, (rect.centerx - lab.get_width()//2, rect.centery - lab.get_height()//2))

        draw_choice(white_btn, "White", chosen_color == chess.WHITE)
        draw_choice(black_btn, "Black", chosen_color == chess.BLACK)

        for lvl, rect in diff_btns:
            active = (chosen_diff == lvl)
            pygame.draw.rect(screen, COL_BTN_H if active else COL_BTN, rect, border_radius=8)
            lab = font_ui.render(str(lvl), True, COL_TEXT)
            screen.blit(lab, (rect.centerx - lab.get_width()//2, rect.centery - lab.get_height()//2))

        ready = (chosen_color is not None and chosen_diff is not None)
        pygame.draw.rect(screen, (0, 140, 80) if ready else (60, 60, 60), start_btn, border_radius=10)
        start_txt = font_ui.render("Start Game", True, (255, 255, 255) if ready else (200, 200, 200))
        screen.blit(start_txt, (start_btn.centerx - start_txt.get_width()//2, start_btn.centery - start_txt.get_height()//2))

        pygame.display.flip()
        pygame.time.Clock().tick(60)

# ============================================================
#                           MAIN
# ============================================================

def main():
    pygame.init()
    pygame.display.set_caption(f"Virtual Chessboard — {VERSION}")
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    clock  = pygame.time.Clock()

    fonts = get_fonts()
    font_piece, font_small, font_ui, font_title, has_unicode = fonts

    while True:  # menu loop (Reset/New Game both return here)
        bottom_color, difficulty = show_menu(screen, fonts)
        board = chess.Board()

        # selection / dragging state
        selected_sq   = None
        legal_targets = set()
        dragging      = False
        drag_from_sq  = None
        drag_surface  = None
        drag_offset   = (0, 0)
        press_pos     = None

        # last move
        last_move = None

        # buttons (Undo + Reset)
        btn_w = 120
        btn_h = 44
        gap   = 16
        UI_Y  = BOARD_PIXELS + UI_PAD
        btn_undo  = pygame.Rect(MARGIN, UI_Y + 8, btn_w, btn_h)
        btn_reset = pygame.Rect(MARGIN + btn_w + gap, UI_Y + 8, btn_w, btn_h)

        # game-over overlay state
        is_over       = False
        over_reason   = ""
        over_btn_rect = None
        result_str    = "*"

        running_game = True
        while running_game:
            mx, my = pygame.mouse.get_pos()
            hover_undo  = btn_undo.collidepoint(mx, my)
            hover_reset = btn_reset.collidepoint(mx, my)

            # Check game-over status
            if not is_over:
                is_over, over_reason, result_str = game_over_reason(board)
                if is_over:
                    print(f'end_game reason="{over_reason}" result={result_str}')

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit(); sys.exit(0)

                if is_over:
                    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        if hover_reset:
                            print("reset")
                            running_game = False
                            break
                        if over_btn_rect and over_btn_rect.collidepoint(mx, my):
                            print("reset")
                            running_game = False
                            break
                    elif event.type == pygame.KEYDOWN and event.key == pygame.K_q:
                        pygame.quit(); sys.exit(0)
                    continue

                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    press_pos = (mx, my)

                    if hover_undo:
                        if board.move_stack:
                            popped = board.pop()
                            print("undo:", popped.uci())
                            last_move = board.move_stack[-1] if board.move_stack else None
                        selected_sq = None
                        legal_targets.clear()
                        dragging = False
                        drag_from_sq = None
                        drag_surface = None
                        continue

                    if hover_reset:
                        print("reset")
                        running_game = False
                        break

                    sq = mouse_to_board_square(mx, my, bottom_color)
                    if sq is None:
                        selected_sq = None
                        legal_targets.clear()
                        press_pos = None
                    else:
                        piece = board.piece_at(sq)
                        if piece and piece.color == board.turn:
                            selected_sq   = sq
                            legal_targets = {m.to_square for m in board.legal_moves if m.from_square == sq}
                            dragging      = False
                            drag_from_sq  = None
                            drag_surface  = None
                        else:
                            if selected_sq is None:
                                legal_targets.clear()
                                press_pos = None

                elif event.type == pygame.MOUSEMOTION:
                    if press_pos and selected_sq is not None and pygame.mouse.get_pressed(num_buttons=3)[0]:
                        dx = mx - press_pos[0]
                        dy = my - press_pos[1]
                        if not dragging and (dx*dx + dy*dy) >= (DRAG_THRESH_PX * DRAG_THRESH_PX):
                            dragging = True
                            drag_from_sq = selected_sq
                            piece = board.piece_at(drag_from_sq)
                            if piece:
                                glyph = UNICODE[piece.piece_type][piece.color] if has_unicode else LETTER[piece.piece_type][piece.color]
                                drag_surface = font_piece.render(glyph, True, (15, 15, 15))
                                fi = chess.square_file(drag_from_sq); ri = chess.square_rank(drag_from_sq)
                                sf, sr = board_to_screen_fr(fi, ri, bottom_color)
                                base_x, base_y = fr_to_xy(sf, sr)
                                gx = base_x + (SQUARE - drag_surface.get_width()) // 2
                                gy = base_y + (SQUARE - drag_surface.get_height()) // 2
                                drag_offset = (press_pos[0] - gx, press_pos[1] - gy)

                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    press_pos = None

                    if dragging and drag_from_sq is not None:
                        drop_sq = mouse_to_board_square(mx, my, bottom_color)
                        try_sq = drop_sq if drop_sq is not None else drag_from_sq

                        if try_sq == drag_from_sq:
                            dragging = False
                            drag_from_sq = None
                            drag_surface = None
                            selected_sq = None
                            legal_targets.clear()
                            continue

                        if try_make_move(board, drag_from_sq, try_sq):
                            last_move = board.move_stack[-1] if board.move_stack else None
                            selected_sq = None
                            legal_targets.clear()
                        else:
                            if drop_sq is not None:
                                p2 = board.piece_at(drop_sq)
                                if p2 and p2.color == board.turn:
                                    selected_sq = drop_sq
                                    legal_targets = {m.to_square for m in board.legal_moves if m.from_square == drop_sq}
                                else:
                                    selected_sq = None
                                    legal_targets.clear()
                            else:
                                selected_sq = None
                                legal_targets.clear()

                        dragging = False
                        drag_from_sq = None
                        drag_surface = None

                    else:
                        sq = mouse_to_board_square(mx, my, bottom_color)
                        if sq is None:
                            selected_sq = None
                            legal_targets.clear()
                        else:
                            if selected_sq is None:
                                pass
                            else:
                                if sq == selected_sq:
                                    pass
                                else:
                                    if try_make_move(board, selected_sq, sq):
                                        last_move = board.move_stack[-1] if board.move_stack else None
                                        selected_sq = None
                                        legal_targets.clear()
                                    else:
                                        p2 = board.piece_at(sq)
                                        if p2 and p2.color == board.turn:
                                            selected_sq = sq
                                            legal_targets = {m.to_square for m in board.legal_moves if m.from_square == sq}
                                        else:
                                            pass

                elif event.type == pygame.KEYDOWN and event.key == pygame.K_q:
                    pygame.quit(); sys.exit(0)

            # --------- RENDER ---------
            screen.fill(COL_BG)
            draw_board_squares(screen)
            draw_last_move(screen, last_move, bottom_color)
            draw_selection_outline(screen, selected_sq, bottom_color)
            draw_legal_dots(screen, legal_targets, bottom_color)
            draw_check_overlay(screen, board, bottom_color)

            skip_sq = drag_from_sq if dragging else None
            draw_pieces(screen, board, font_piece, has_unicode, bottom_color, skip_sq=skip_sq)

            if dragging and drag_surface is not None:
                mx, my = pygame.mouse.get_pos()
                screen.blit(drag_surface, (mx - drag_offset[0], my - drag_offset[1]))

            draw_file_labels(screen, font_small, bottom_color)
            draw_rank_labels(screen, font_small, bottom_color)

            pygame.draw.rect(screen, (36, 36, 36), (0, BOARD_PIXELS + UI_PAD, WIN_W, UI_HEIGHT))
            draw_button(screen, btn_undo,  "Undo",  font_ui, hover_undo)
            draw_button(screen, btn_reset, "Reset", font_ui, hover_reset)

            info = f"Color: {'White' if bottom_color == chess.WHITE else 'Black'}   |   Difficulty: {difficulty}"
            info_srf = font_ui.render(info, True, COL_ACC)
            screen.blit(info_srf, (MARGIN, BOARD_PIXELS + UI_PAD + UI_HEIGHT - info_srf.get_height() - 10))

            turn_txt = "White to move" if board.turn == chess.WHITE else "Black to move"
            turn_srf = font_ui.render(turn_txt, True, COL_TEXT)
            screen.blit(turn_srf, (WIN_W - MARGIN - turn_srf.get_width(), BOARD_PIXELS + UI_PAD + UI_HEIGHT - turn_srf.get_height() - 10))

            over_btn_rect = None
            is_over_now, over_reason, result_str = game_over_reason(board)
            if is_over_now:
                print(f'end_game reason="{over_reason}" result={result_str}')
                over_btn_rect = draw_game_over_overlay(screen, fonts, over_reason)
                # While overlay visible, inputs handled in event loop above

            pygame.display.flip()
            clock.tick(60)

if __name__ == "__main__":
    main()
