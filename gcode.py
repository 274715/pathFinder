 import moonrakerpy as moonpy
import chess
import chess.pgn
import io
import time

# Initialize the printer (we won't actually send G-code in this version)
# printer = moonpy.MoonrakerPrinter("http://192.168.1.217:7125")

# Define board size and square size in mm
board_size = 350  # 350mm for the board size
square_size = board_size / 8  # Each square will be 350/8 mm

# Function to convert PGN text into move coordinates


def pgn_to_coordinate_notation(pgn_text):
    # Read the game from PGN text
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    board = game.board()  # Get the initial board position
    coordinate_moves = []  # List to store move notations

    # Loop through all the moves in the PGN game
    for move in game.mainline_moves():
        # Convert from square to notation (e.g., e2)
        from_square = chess.square_name(move.from_square)
        # Convert to square to notation (e.g., e4)
        to_square = chess.square_name(move.to_square)
        # Combine to form a move like 'e2e4'
        coordinate_moves.append(from_square + to_square)
        board.push(move)  # Update the board with the move

    return coordinate_moves

# Function to convert chess notation (e.g., 'e2') to coordinates (mm)


def chess_notation_to_coordinates(notation):
    column = notation[0].upper()  # Get the column letter (e.g., 'e')
    row = notation[1]  # Get the row number (e.g., '2')

    # Calculate the x and y indexes based on the board
    # Convert column letter to index (A-H -> 0-7)
    x_index = ord(column) - ord('A')

    # Reverse the row so that row 1 is at the bottom and row 8 is at the top
    y_index = 8 - int(row)  # Flip the row so that row 1 is at the bottom

    # Calculate x and y in millimeters, reversing the x-axis (A=350, H=0)
    x_mm = (7 - x_index) * (board_size / 7)  # Reverse the x-axis mapping
    y_mm = y_index * (board_size / 7)  # Reverse the y-axis mapping

    return x_mm, y_mm

# Function to generate G-code for moving to a specific square based on chess notation


def move_to_square(notation):
    x_mm, y_mm = chess_notation_to_coordinates(notation)
    # Generate the G-code command for moving to the calculated x and y coordinates
    return f"G0 X{x_mm} Y{y_mm}"

# Main function to generate G-code for a PGN game


def generate_gcode(pgn_text, output_file="chess_moves.gcode"):
    moves = pgn_to_coordinate_notation(pgn_text)  # Get all the moves from PGN
    gcode_commands = []  # List to store G-code commands

    # Add an initial setup to start the G-code file (optional, depending on your printer)
    gcode_commands.append("G21 ; Set units to mm")
    gcode_commands.append("G90 ; Use absolute positioning")
    gcode_commands.append("G28 ; Home all axes")

    for move in moves:
        from_square = move[:2]  # Extract the 'from' square (e.g., 'e2')
        to_square = move[2:]  # Extract the 'to' square (e.g., 'e4')

        # Add G-code to move to the 'from' square
        gcode_commands.append(move_to_square(from_square))
        gcode_commands.append(f"; Move from {from_square}")

        # Add a small delay between moves (if needed for visual effect)
        time.sleep(0.5)

        # Add G-code to move to the 'to' square
        gcode_commands.append(move_to_square(to_square))
        gcode_commands.append(f" ; Move to {to_square}")

        # Add a small delay after each move (if needed for visual effect)
        time.sleep(0.5)

    # Add a final command to stop the printer (optional, depending on your printer)
    gcode_commands.append("M104 S0 ; Turn off extruder")
    gcode_commands.append("M140 S0 ; Turn off heated bed")
    gcode_commands.append("M107 ; Turn off fan")
    gcode_commands.append("M84 ; Disable motors")

    # Write the G-code commands to the output file
    with open(output_file, "w") as file:
        file.write("\n".join(gcode_commands))

    print(f"G-code file generated: {output_file}")


# Sample PGN game (you can replace this with your actual PGN)
pgn_sample = """
[Event "Casual Game"]
[Site "Local"]
[Date "2024.11.28"]
[Round "?"]
[White "Player 1"]
[Black "Player 2"]
[Result "1-0"]

1. e4 e5 2. Nf3 Nc6
"""

# Call the function to generate G-code for the sample PGN
generate_gcode(pgn_sample)
