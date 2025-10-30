import pytest

chess = pytest.importorskip("chess")

from printer_sim import (
    init_grave_positions,
    plan_capture_sequence,
    captured_white,
    captured_black,
    sq_to_rc,
    rc_to_center_xy,
)


@pytest.fixture(autouse=True)
def reset_graveyard_state():
    captured_white.clear()
    captured_black.clear()
    init_grave_positions()


def _make_capture_board():
    board = chess.Board()
    if hasattr(board, "clear_board"):
        board.clear_board()
    else:
        for square in chess.SQUARES:
            board.remove_piece_at(square)
    board.set_piece_at(chess.E1, chess.Piece(chess.KING, chess.WHITE))
    board.set_piece_at(chess.E8, chess.Piece(chess.KING, chess.BLACK))
    board.set_piece_at(chess.E4, chess.Piece(chess.PAWN, chess.WHITE))
    board.set_piece_at(chess.D5, chess.Piece(chess.PAWN, chess.BLACK))
    board.turn = chess.WHITE
    if hasattr(board, "clear_stack"):
        board.clear_stack()
    else:
        board.stack = []
    return board


def test_capture_return_path_can_enter_occupied_origin():
    board = _make_capture_board()
    move = chess.Move.from_uci("e4d5")
    assert board.is_capture(move)

    segments, captured_color, grave_xy = plan_capture_sequence(board, move)

    assert captured_color == chess.BLACK
    assert grave_xy is not None

    path_back = segments[4]["waypoints"]
    src_center = rc_to_center_xy(*sq_to_rc(move.from_square))
    assert path_back[-1] == pytest.approx(src_center)
    # The path should include at least two distinct waypoints (graveyard -> board).
    assert len(path_back) >= 2
