import moonrakerpy as moonpy
import chess
import chess.pgn
import io

printer = moonpy.MoonrakerPrinter("http://192.168.1.217:7125")


# class printer:
#     def send_gcode(x):
#         ''


class Move:
    def __init__(self, from_square, to_square, is_knight=False, is_capture=False):
        self.from_square = from_square
        self.to_square = to_square
        self.is_knight = is_knight
        self.is_capture = is_capture

    def __str__(self):
        return f"{self.from_square}{self.to_square}{'_' if self.is_knight else ''}{'X' if self.is_capture else ''}"


class MoveList:
    def __init__(self):
        self.moves = []

    def add_move(self, from_square, to_square, is_knight=False, is_capture=False):
        move = Move(from_square, to_square, is_knight, is_capture)
        self.moves.append(move)

    def __iter__(self):
        return iter(self.moves)

    def __len__(self):
        return len(self.moves)

    def __getitem__(self, index):
        return self.moves[index]


board_size = 350
square_size = board_size / 8


def pgn_to_movelist(pgn_text):
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    board = game.board()
    move_list = MoveList()

    for move in game.mainline_moves():
        from_square = chess.square_name(move.from_square)
        to_square = chess.square_name(move.to_square)
        is_knight = str(board.piece_at(move.from_square)).lower() == "n"
        is_capture = board.is_capture(move)
        move_list.add_move(from_square, to_square, is_knight, is_capture)
        board.push(move)

    return move_list


def chess_notation_to_coordinates(notation):
    column = notation[0].upper()
    row = notation[1]

    x_index = ord(column) - ord('A')
    y_index = 8 - int(row)

    x_mm = (7 - x_index) * (board_size / 7)
    y_mm = y_index * (board_size / 7)

    return x_mm, y_mm


def move_to_square(notation):
    x_mm, y_mm = chess_notation_to_coordinates(notation)
    printer.send_gcode(f"G0 X{x_mm} Y{y_mm}")


def capturePiece(fromS, toS):
    move_to_square(fromS)
    printerHeat(100)
    printerWait(500)
    move_to_square(toS)
    print(fromS, toS)


def printerWait(time):
    printer.send_gcode(f'G4 P{time}')


def printerHeat(value):
    printer.send_gcode(
        f'SET_HEATER_TEMPERATURE HEATER=extruder TARGET={value}')


def printerPrep():
    printerHeat(0)
    printer.send_gcode('G28 X Y')


def play_game(pgn_text):
    printerPrep()
    moves = pgn_to_movelist(pgn_text)
    for move in moves:
        printerHeat(0)
        # if (move.is_capture):
        #     capturePiece(move.to_square,)
        move_to_square(move.from_square)
        printerHeat(100)
        printerWait(2000)
        if move.is_knight:
            intermediate_square = move.from_square[0] + move.to_square[1]
            move_to_square(intermediate_square)
            printerWait(750)
        move_to_square(move.to_square)
        printerWait(2000)


pgn_sample = """
1. d4 d5 2. c4 dxc4 3. e4 b5 4. a4 a6 5. axb5 axb5 6. Rxa8 Nf6 7. Be2 e6 8. Nf3 Bd6 9. O-O O-O"""
play_game(pgn_sample)
