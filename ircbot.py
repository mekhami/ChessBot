import sys
import urllib2
import json

from twisted.internet import defer, endpoints, protocol, reactor, task
from twisted.python import log
from twisted.words.protocols import irc


class ChessGame(object):
    fen_startpos = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    
    def __init__(self):
        self.board = [["#"]*12 for i in range(12)]
        self.turn = "-"
        self.castling = "-"
        self.ep = "-"
        self.fiftyMoves = 0
        self.fullMoves = 0
        self.fen = ""
        self.setFEN(ChessGame.fen_startpos)
        
        # Board setup
        #            x & y Coordinates       Absolute coordinates
        #            in 8x8   in 12x12       in 8x8     in 12x12
        # A1    -    (0, 0)   (2, 2)     -   0          26
        # E1    -    (4, 0)   (6, 2)     -   4          30
        # E4    -    (4, 3)   (6, 5)     -   28         66
        #
        # Converting x & y coordinates in 8x8 to 12x12
        # x_8 = x_12 - 2
        # y_8 = y_12 - 2
        #
        # Converting absolute coordinates in 8x8 to x & y coordinates in 8x8
        # x_8 = sq % 8
        # y_8 = sq / 8
        #
    
    def setFEN(self, fen):
        """
        Converts a FEN string into a board position
        
        Keyword arguments:
        fen -- the board position in FEN notation
        """
        
        parts = fen.split(" ")
        
        if parts[0].count("/") != 7:
            return False
        if parts[0].count("K") != 1:
            return False
        if parts[0].count("k") != 1:
            return False
        
        # Starting at A8, moving right, then coming down a row
        sq = 56
        for a in range(0, len(parts[0])):
            if parts[0][a].isalpha():
                if "pbnrqkPBNRQK".find(parts[0][a]) < 0:
                    return False
                self.boardSet(sq%8, sq/8, parts[0][a])
                sq += 1
            elif parts[0][a] == "/":
                # -8 to get to the row beneath in the same column
                # -7 to get from the 8th column to the 1st column
                # -1 to account for sq currently being in the 9th (i) column
                sq -= 16
            else:
                # We need to fill in empty spaces according to the number provided
                for b in range(0, int(parts[0][a])):
                    self.boardSet(sq%8+b, sq/8, "-")
                sq += int(parts[0][a])
        
        # Side to play
        if len(parts) >= 1:
            if parts[1] == "w":
                self.turn = "w"
            elif parts[1] == "b":
                self.turn = "b"
            else:
                return False;
        
        # Castling
        if len(parts) >= 2:
            self.castling = parts[2]
        
        # ep square
        if len(parts) >= 3:
            self.ep = parts[3]
            if self.ep != "-" and self.onBoard(self.ep) == False:
                return False
        
        # Halfmoves since last capture or pawn advance
        if len(parts) >= 4:
            self.fiftyMoves = int(parts[4])
            if self.fiftyMoves < 0:
                return False
        
        # Full moves
        if len(parts) >= 5:
            self.fullMoves = int(parts[5])
            if self.fullMoves < 0:
                return False
        
        return True
    
    def getFEN(self):
        """
        Converts the current game into an FEN string and stores it in self.fen
        
        Keyword arguments:
        """
        
        self.fen = ""
        
        # Iterate through the board
        spaces = 0
        for y in range(0, 8):
            for x in range(0, 8):
                piece = self.boardGet(x, 7-y)
                if piece == "-":
                    spaces += 1
                else:
                    if spaces > 0:
                        self.fen += str(spaces)
                        spaces = 0
                    self.fen += piece
            if spaces > 0:
                self.fen += str(spaces)
                spaces = 0
            if y < 7:
                self.fen += "/"
        
        self.fen += " " + self.turn
        self.fen += " " + self.castling
        self.fen += " " + self.ep
        self.fen += " " + str(self.fiftyMoves)
        self.fen += " " + str(self.fullMoves)
        
        return True
    
    def getLichessURL(self, moves):
        """
        Resets the board to the starting position, plays the moves given, and returns an URL to the position on Lichess.org
        
        Keyword arguments:
        moves -- the list of moves to be played
        """
        
        r = self.setFEN(ChessGame.fen_startpos)
        if r == False:
            return False
        
        r = self.moveParses(moves)
        if r == False:
            return False
        
        r = self.getFEN()
        if r == False:
            return False
        
        #if self.fen == ChessGame.fen_startpos):
        #    return False
        
        return "http://lichess.org/analysis/{}".format(self.fen.replace(" ", "_"))

    def printBoard(self):
        """
        prints the 8x8 board with current turn and castling permissions
        
        Keyword arguments:
        """
        
        for y in range(0, 8):
            for x in range(0, 8):
                sys.stdout.write(self.boardGet(x, 7-y))
            sys.stdout.write("\n")
        print("Turn: {}".format(self.turn))
        print("Castling: {}".format(self.castling))
    
    def charToCol(self, char):
        """
        Returns the numberical value of the column for the character given (a == 0, h == 7)
        
        Keyword arguments:
        char -- the character provided
        """
        
        return ord(char) - 97
    
    def charToRow(self, char):
        """
        Returns the numberical value of the row for the character given (1 == 0, 8 == 7)
        
        Keyword arguments:
        char -- the character provided
        """
        
        return int(char) - 1
    
    def posGetCol(self, str):
        """
        Returns the numberical value of the column for the move given (c5 == 3)
        
        Keyword arguments:
        str -- the move provided
        """
        
        if len(str) != 2:
            return -1
        return self.charToCol(str[0])
    
    def posGetRow(self, str):
        """
        Returns the numberical value of the row for the move given (c5 == 4)
        
        Keyword arguments:
        str -- the move provided
        """
        
        if len(str) != 2:
            return -1
        return self.charToRow(str[1])
    
    def boardGet(self, col, row):
        """
        Returns the piece currently at position (col, row)
        
        Keyword arguments:
        col -- the column requested
        row -- the row requested
        """
        
        return self.board[col+2][row+2]
    
    def boardSet(self, col, row, piece):
        """
        Sets the piece currently at position (col, row)
        
        Keyword arguments:
        col   -- the column requested
        row   -- the row requested
        piece -- the piece to place at position (col, row)
        """
        
        self.board[col+2][row+2] = piece
    
    def findMoveWP(self, col_to, row_to):
        """
        Returns a list of white pawn moves to position(col_to, row_to)
        
        Keyword arguments:
        col_to -- the column the piece is moving to
        row_to -- the row the piece is moving to
        """
        
        # If a white piece is already at the end position, nothing can move there
        if self.boardGet(col_to, row_to) != "-":
            if "PBNRQK".find(self.boardGet(col_to, row_to)) >= 0:
                return []
        
        results = []
        
        # ep
        if self.posGetCol(self.ep) == col_to and self.posGetRow(self.ep) == row_to:
            # Down 1 left 1
            if self.boardGet(col_to-1, row_to-1) == "P":
                results.append(["P", col_to-1, row_to-1])
            
            # Down 1 right 1
            if self.boardGet(col_to+1, row_to-1) == "P":
                results.append(["P", col_to+1, row_to-1])
        
        # Captures
        if "pnbrqk".find(self.boardGet(col_to, row_to)) >= 0:
            # Down 1 left 1
            if self.boardGet(col_to-1, row_to-1) == "P":
                results.append(["P", col_to-1, row_to-1])
            
            # Down 1 right 1
            if self.boardGet(col_to+1, row_to-1) == "P":
                results.append(["P", col_to+1, row_to-1])
        
        # Down 1
        if self.boardGet(col_to, row_to-1) == "P":
            results.append(["P", col_to, row_to-1])
        
        # Down 2
        if self.boardGet(col_to, row_to-2) == "P" and row_to == 3:
            # Down 1
            if self.boardGet(col_to, row_to-1) == "-":
                results.append(["P", col_to, row_to-2])
        
        return results
    
    def findMoveBP(self, col_to, row_to):
        """
        Returns a list of black pawn moves to position(col_to, row_to)
        
        Keyword arguments:
        col_to -- the column the piece is moving to
        row_to -- the row the piece is moving to
        """
        
        # If a black piece is already at the end position, nothing can move there
        if self.boardGet(col_to, row_to) != "-":
            if "pnbrqk".find(self.boardGet(col_to, row_to)) >= 0:
                return []
        
        results = []
        
        # ep
        if self.posGetCol(self.ep) == col_to and self.posGetRow(self.ep) == row_to:
            # Up 1 left 1
            if self.boardGet(col_to-1, row_to+1) == "p":
                results.append(["p", col_to-1, row_to+1])
            
            # Up 1 right 1
            if self.boardGet(col_to+1, row_to+1) == "p":
                results.append(["p", col_to+1, row_to+1])
        
        # Captures
        if "PNBRQK".find(self.boardGet(col_to, row_to)) >= 0:
          # Up 1 left 1
          if self.boardGet(col_to-1, row_to+1) == "p":
              results.append(["p", col_to-1, row_to+1])
          
          # Up 1 right 1
          if self.boardGet(col_to+1, row_to+1) == "p":
              results.append(["p", col_to+1, row_to+1])
        
        # Up 1
        if self.boardGet(col_to, row_to+1) == "p":
            results.append(["p", col_to, row_to+1])
        
        # Up 2
        if self.boardGet(col_to, row_to+2) == "p" and row_to == 4:
            # Up 1
            if self.boardGet(col_to, row_to+1) == "-":
                results.append(["p", col_to, row_to+2])
        
        return results
    
    def findMoveN(self, piece, col_to, row_to):
        """
        Returns a list of knight moves to position(col_to, row_to)
        
        Keyword arguments:
        piece  -- the type of piece: "N" for white, "n" for black
        col_to -- the column the piece is moving to
        row_to -- the row the piece is moving to
        """
        
        if self.boardGet(col_to, row_to) != "-":
            if piece == "N":
                # If a black piece is already at the end position, nothing can move there
                if "PBNRQK".find(self.boardGet(col_to, row_to)) >= 0:
                    return []
            elif piece == "n":
                # If a black piece is already at the end position, nothing can move there
                if "pbnrqk".find(self.boardGet(col_to, row_to)) >= 0:
                    return []
        
        results = []
        
        if self.boardGet(col_to-1, row_to+2) == piece: # Up 2 left 1
            results.append([piece, col_to-1, row_to+2])
        if self.boardGet(col_to+1, row_to+2) == piece: # Up 2 right 1
            results.append([piece, col_to+1, row_to+2])
        if self.boardGet(col_to-1, row_to-2) == piece: # Down 2 left 1
            results.append([piece, col_to-1, row_to-2])
        if self.boardGet(col_to+1, row_to-2) == piece: # Down 2 right 1
            results.append([piece, col_to+1, row_to-2])
        if self.boardGet(col_to+2, row_to+1) == piece: # Right 2 up 1
            results.append([piece, col_to+2, row_to+1])
        if self.boardGet(col_to+2, row_to-1) == piece: # Right 2 down 1
            results.append([piece, col_to+2, row_to-1])
        if self.boardGet(col_to-2, row_to+1) == piece: # Left 2 up 1
            results.append([piece, col_to-2, row_to+1])
        if self.boardGet(col_to-2, row_to-1) == piece: # Left 2 down 1
            results.append([piece, col_to-2, row_to-1])
        
        return results
    
    def findMoveDiagonal(self, piece, col_to, row_to):
        """
        Returns a list of diagonal moves to position(col_to, row_to)
        
        Keyword arguments:
        piece  -- the type of piece: "B" or "Q" for white, "b" or "q" for black
        col_to -- the column the piece is moving to
        row_to -- the row the piece is moving to
        """
        
        if self.boardGet(col_to, row_to) != "-":
            if piece == "B" or piece == "Q":
                # If a white piece is already at the end position, nothing can move there
                if "PBNRQK".find(self.boardGet(col_to, row_to)) >= 0:
                    return []
            elif piece == "b" or piece == "q":
                # If a black piece is already at the end position, nothing can move there
                if "pbnrqk".find(self.boardGet(col_to, row_to)) >= 0:
                    return []
        
        results = []
        
        # Up and right
        for a in range(1, 8):
            if self.boardGet(col_to+a, row_to+a) != "-":
                if self.boardGet(col_to+a, row_to+a) == piece:
                    results.append([piece, col_to+a, row_to+a])
                break
        
        # Up and left
        for a in range(1, 8):
            if self.boardGet(col_to-a, row_to+a) != "-":
                if self.boardGet(col_to-a, row_to+a) == piece:
                    results.append([piece, col_to-a, row_to+a])
                break
        
        # Down and right
        for a in range(1, 8):
            if self.boardGet(col_to+a, row_to-a) != "-":
                if self.boardGet(col_to+a, row_to-a) == piece:
                    results.append([piece, col_to+a, row_to-a])
                break
        
        # Down and left
        for a in range(1, 8):
            if self.boardGet(col_to-a, row_to-a) != "-":
                if self.boardGet(col_to-a, row_to-a) == piece:
                    results.append([piece, col_to-a, row_to-a])
                break
        
        return results
    
    def findMoveStraight(self, piece, col_to, row_to):
        """
        Returns a list of straight moves to position(col_to, row_to)
        
        Keyword arguments:
        piece  -- the type of piece: "R" or "Q" for white, "r" or "q" for black
        col_to -- the column the piece is moving to
        row_to -- the row the piece is moving to
        """
        
        if self.boardGet(col_to, row_to) != "-":
            if piece == "R" or piece == "Q":
                # If a white piece is already at the end position, nothing can move there
                if "PBNRQK".find(self.boardGet(col_to, row_to)) >= 0:
                    return []
            elif piece == "r" or piece == "q":
                # If a black piece is already at the end position, nothing can move there
                if "pbnrqk".find(self.boardGet(col_to, row_to)) >= 0:
                    return []
        
        results = []
        
        # Right
        for a in range(1, 8):
            if self.boardGet(col_to+a, row_to) != "-":
                if self.boardGet(col_to+a, row_to) == piece:
                    results.append([piece, col_to+a, row_to])
                break
        
        # Left
        for a in range(1, 8):
            if self.boardGet(col_to-a, row_to) != "-":
                if self.boardGet(col_to-a, row_to) == piece:
                    results.append([piece, col_to-a, row_to])
                break
        
        # Up
        for a in range(1, 8):
            if self.boardGet(col_to, row_to+a) != "-":
                if self.boardGet(col_to, row_to+a) == piece:
                    results.append([piece, col_to, row_to+a])
                break
        
        # Down
        for a in range(1, 8):
            if self.boardGet(col_to, row_to-a) != "-":
                if self.boardGet(col_to, row_to-a) == piece:
                    results.append([piece, col_to, row_to-a])
                break
        
        return results
    
    def findMoveKing(self, piece, col_to, row_to):
        """
        Returns a list of king moves to position(col_to, row_to)
        
        Keyword arguments:
        piece  -- the type of piece: "K" for white, "k" for black
        col_to -- the column the piece is moving to
        row_to -- the row the piece is moving to
        """
        
        if self.boardGet(col_to, row_to) != "-":
            if piece == "K":
                # If a white piece is already at the end position, nothing can move there
                if "PBNRQK".find(self.boardGet(col_to, row_to)) >= 0:
                    return []
            elif piece == "k":
                # If a black piece is already at the end position, nothing can move there
                if "pbnrqk".find(self.boardGet(col_to, row_to)) >= 0:
                    return []
        
        results = []
        
        if self.boardGet(col_to, row_to+1) == piece: # Up 1
            results.append([piece, col_to, row_to+1])
        if self.boardGet(col_to, row_to-1) == piece: # Down 1
            results.append([piece, col_to, row_to-1])
        if self.boardGet(col_to+1, row_to) == piece: # Right 1
            results.append([piece, col_to+1, row_to])
        if self.boardGet(col_to-1, row_to) == piece: # Left 1
            results.append([piece, col_to-1, row_to])
        if self.boardGet(col_to+1, row_to+1) == piece: # Up 1 right 1
            results.append([piece, col_to+1, row_to+1])
        if self.boardGet(col_to-1, row_to+1) == piece: # Up 1 left 1
            results.append([piece, col_to-1, row_to+1])
        if self.boardGet(col_to+1, row_to-1) == piece: # Down 1 right 1
            results.append([piece, col_to+1, row_to-1])
        if self.boardGet(col_to-1, row_to-1) == piece: # Down 1 left 1
            results.append([piece, col_to-1, row_to-1])
        
        return results
    
    def isWhiteAttacking(self, col, row):
        """
        Returns True or False depending on if a white piece is attacking the position given
        
        Keyword arguments:
        col -- the column of the position being checked
        row -- the row of the position being checked
        """
        
        if self.boardGet(col-1, row-1) == "P":
            return True
        elif self.boardGet(col+1, row-1) == "P":
            return True
        elif self.findMoveN("N", col, row) != []:
            return True;
        elif self.findMoveDiagonal("B", col, row) != []:
            return True;
        elif self.findMoveStraight("R", col, row) != []:
            return True;
        elif self.findMoveDiagonal("Q", col, row) != []:
            return True;
        elif self.findMoveStraight("Q", col, row) != []:
            return True;
        elif self.findMoveKing("K", col, row) != []:
            return True;
        else:
            return False
    
    def isBlackAttacking(self, col, row):
        """
        Returns True or False depending on if a black piece is attacking the position given
        
        Keyword arguments:
        col -- the column of the position being checked
        row -- the row of the position being checked
        """
        
        if self.boardGet(col-1, row+1) == "p":
            return True
        elif self.boardGet(col+1, row+1) == "p":
            return True
        elif self.findMoveN("n", col, row) != []:
            return True;
        elif self.findMoveDiagonal("b", col, row) != []:
            return True;
        elif self.findMoveStraight("r", col, row) != []:
            return True;
        elif self.findMoveDiagonal("q", col, row) != []:
            return True;
        elif self.findMoveStraight("q", col, row) != []:
            return True;
        elif self.findMoveKing("k", col, row) != []:
            return True;
        else:
            return False
    
    def colRowToStr(self, col, row):
        return chr(col + 97) + chr(row + 49)
    
    def onBoard(self, str):
        """
        Returns True or False depending on if the algebraic position given is on the board
        
        Keyword arguments:
        str -- the position given
        """
        
        if len(str) != 2:
            return False
        
        col = self.posGetCol(str)
        if col < 0 or col > 7:
            return False
        
        row = self.posGetRow(str)
        if row < 0 or row > 7:
            return False
        
        return True
    
    def moveMake(self, from_col, from_row, to_col, to_row, promotion="-"):
        """
        Plays the move given on the board
        
        Keyword arguments:
        from_col  -- the column the piece is moving from
        from_row  -- the row the piece is moving from
        to_col    -- the column the piece is moving to
        to_row    -- the row the piece is moving to
        promotion -- the piece we're promoting to, default is to not promote: "-"
        """
        
        # 50 move rule
        if self.boardGet(to_col, to_row) != "-" or self.boardGet(from_col, from_row) == "P" or self.boardGet(from_col, from_row) == "p":
            self.fiftyMoves = 0
        else:
            self.fiftyMoves += 1
        
        # Castling permissions
        if (from_col == 4 and from_row == 0) or (to_col == 4 and to_row == 0): # White king position
            self.castling = self.castling.replace("K", "")
            self.castling = self.castling.replace("Q", "")
        if (from_col == 0 and from_row == 0) or (to_col == 0 and to_row == 0): # White a1 rook position
            self.castling = self.castling.replace("Q", "")
        if (from_col == 7 and from_row == 0) or (to_col == 7 and to_row == 0): # White h1 rook position
            self.castling = self.castling.replace("K", "")
        
        if (from_col == 4 and from_row == 7) or (to_col == 4 and to_row == 7): # Black king position
            self.castling = self.castling.replace("k", "")
            self.castling = self.castling.replace("q", "")
        if (from_col == 0 and from_row == 7) or (to_col == 0 and to_row == 7): # Black a1 rook position
            self.castling = self.castling.replace("q", "")
        if (from_col == 7 and from_row == 7) or (to_col == 7 and to_row == 7): # Black h1 rook position
            self.castling = self.castling.replace("k", "")
        
        if self.castling == "":
            self.castling = "-"
        
        # Capture ep white
        if self.ep != "-" and self.boardGet(from_col, from_row) == "P":
            if self.posGetCol(self.ep) == to_col and self.posGetRow(self.ep) == to_row:
                self.boardSet(self.posGetCol(self.ep), self.posGetRow(self.ep)-1, "-")
        # Capture ep black
        if self.ep != "-" and self.boardGet(from_col, from_row) == "p":
            if self.posGetCol(self.ep) == to_col and self.posGetRow(self.ep) == to_row:
                self.boardSet(self.posGetCol(self.ep), self.posGetRow(self.ep)+1, "-")
        
        # Play the move
        if promotion == "-":
            self.boardSet(to_col, to_row, self.boardGet(from_col, from_row))
        else:
            self.boardSet(to_col, to_row, promotion)
        self.boardSet(from_col, from_row, "-")
        
        # Set the ep square
        if self.boardGet(to_col, to_row) == "P" and to_row - from_row == 2:
            self.ep = self.colRowToStr(to_col, to_row-1)
        elif self.boardGet(to_col, to_row) == "p" and to_row - from_row == -2:
            self.ep = self.colRowToStr(to_col, to_row+1)
        else:
            self.ep = "-"
        
        return True
    
    def moveMakeWKSC(self):
        self.moveMake(4,0, 6,0) # King
        self.moveMake(7,0, 5,0) # Rook
        self.fiftyMoves -= 1
    
    def moveMakeBKSC(self):
        self.moveMake(4,7, 6,7) # King
        self.moveMake(7,7, 5,7) # Rook
        self.fiftyMoves -= 1
    
    def moveMakeWQSC(self):
        self.moveMake(4,0, 2,0) # King
        self.moveMake(0,0, 3,0) # Rook
        self.fiftyMoves -= 1
    
    def moveMakeBQSC(self):
        self.moveMake(4,7, 2,7) # King
        self.moveMake(0,7, 3,7) # Rook
        self.fiftyMoves -= 1
    
    def moveParse(self, move):
        """
        Returns True or False depending on if the algebraic notation move provided can be parsed and found in the list of available moves
        
        Keyword arguments:
        move -- the move provided
        """
        
        if len(move) < 2:
            return False
    
        # Remove irrelevant characters
        strip = "!?+#x-:="
        for a in strip:
            move = move.replace(a, "")
        
        # Special case of castling
        if move == "OO" or move == "00":
            if self.turn == "w":
                # Check castling permissions
                if self.castling.find("K") < 0:
                    return False
                # Check squares not empty or attacked
                if self.isBlackAttacking(4, 0) == True: # e1
                    return False
                if self.isBlackAttacking(5, 0) == True or self.boardGet(5, 0) != "-": # f1
                    return False
                if self.isBlackAttacking(6, 0) == True or self.boardGet(6, 0) != "-": # g1
                    return False
                self.moveMakeWKSC()
                return True
            elif self.turn == "b":
                # Check squares not empty or attacked
                if self.isWhiteAttacking(4, 7) == True: # e8
                    return False
                if self.isWhiteAttacking(5, 7) == True or self.boardGet(5, 7) != "-": # f8
                    return False
                if self.isWhiteAttacking(6, 7) == True or self.boardGet(6, 7) != "-": # g8
                    return False
                self.moveMakeBKSC()
                return True
        elif move == "OOO" or move == "000":
            if self.turn == "w":
                # Check castling permissions
                if self.castling.find("Q") < 0:
                    return False
                # Check castling permissions
                if self.castling.find("k") < 0:
                    return False
                # Check squares not empty or attacked
                if self.isBlackAttacking(4, 0) == True: # e1
                    return False
                if self.isBlackAttacking(3, 0) == True or self.boardGet(3, 0) != "-": # d1
                    return False
                if self.isBlackAttacking(2, 0) == True or self.boardGet(2, 0) != "-": # c1
                    return False
                if self.boardGet(1, 0) != "-": # b1
                    return False
                self.moveMakeWQSC()
                return True
            elif self.turn == "b":
                # Check castling permissions
                if self.castling.find("q") < 0:
                    return False
                # Check squares not empty or attacked
                if self.isWhiteAttacking(4, 7) == True: # e8
                    return False
                if self.isWhiteAttacking(3, 7) == True or self.boardGet(3, 7) != "-": # d8
                    return False
                if self.isWhiteAttacking(2, 7) == True or self.boardGet(2, 7) != "-": # c8
                    return False
                if self.boardGet(1, 7) != "-": # b8
                    return False
                self.moveMakeBQSC()
                return True
        
        # If we're supplied with a piece type - Store and remove it e.g. (Nf3 ---> f3)
        piece_type = "P"
        if move[0].isupper():
            piece_type = move[0]
            if "BNRQK".find(piece_type) < 0:
                return False
            move = move[1:]
        
        # If the move is a promotion - store and remove it e.g. (a8Q ---> a8)
        promotion = "-"
        if move[-1:].isalpha():
            promotion = move[-1:]
            if "BNRQ".find(promotion) < 0:
                return False
            move = move[:-1]
        
        # Can't promote pieces other than pawns
        if promotion != "-" and piece_type != "P":
            return False
        
        # By this point we should be left with either 2, 3, or 4 characters
        
        # If it's 2 or 3
        # Comparing the first and the last two characters will highlight extra information about row & col
        # Move         Stripped       First         Second   Additional information
        # Nf3     ---> f3        ---> f3      ==    f3       None
        # Ngf3    ---> fg3       ---> fg      !=    g3       Piece originates from the f column
        # e4      ---> e4        ---> e4      ==    e4       None
        # N5xd4   ---> 5d4       ---> 5d      !=    d4       Piece originates from the 5th row
        # exd8=Q+ ---> ed8       ---> ed      !=    d8       Piece originates from the e column
        #
        # If it's 4
        # The user might be using longhand notation
        # e2e4
        # a7a8Q
        #
        
        hint_col = -1
        hint_row = -1
        firstChunk = move[:2]
        secondChunk = move[-2:]
        
        if self.onBoard(secondChunk) == False:
            return False;
        
        if len(move) == 4:
            if self.onBoard(firstChunk) == False:
                return False;
            hint_col = self.posGetCol(firstChunk)
            hint_row = self.posGetRow(firstChunk)
            move = move[2:]
            piece_type = self.boardGet(hint_col, hint_row)
        elif len(move) == 3:
            if firstChunk != secondChunk:
                if firstChunk[0].isalpha() == True:
                    hint_col = self.charToCol(firstChunk[0])
                else:
                    hint_row = self.charToRow(firstChunk[0])
                move = move[1:]
        elif len(move) == 2:
            pass
        else:
            return False
            
        # Convert the move to col & row
        col_to = self.posGetCol(move)
        row_to = self.posGetRow(move)
        
        # Can't promote pieces other than pawns
        if self.turn == "w":
            if promotion != "-" and row_to != 7:
                return False
        elif self.turn == "n":
            if promotion != "-" and row_to != 0:
                return False
        
        # Create a list of candidate moves
        moves_found = []
        if self.turn == "w":
            moves_found += self.findMoveWP(col_to, row_to)
            moves_found += self.findMoveN("N", col_to, row_to)
            moves_found += self.findMoveDiagonal("B", col_to, row_to)
            moves_found += self.findMoveStraight("R", col_to, row_to)
            moves_found += self.findMoveDiagonal("Q", col_to, row_to)
            moves_found += self.findMoveStraight("Q", col_to, row_to)
            moves_found += self.findMoveKing("K", col_to, row_to)
        elif self.turn == "b":
            moves_found += self.findMoveBP(col_to, row_to)
            moves_found += self.findMoveN("n", col_to, row_to)
            moves_found += self.findMoveDiagonal("b", col_to, row_to)
            moves_found += self.findMoveStraight("r", col_to, row_to)
            moves_found += self.findMoveDiagonal("q", col_to, row_to)
            moves_found += self.findMoveStraight("q", col_to, row_to)
            moves_found += self.findMoveKing("k", col_to, row_to)
        
        # Move must've been illegal
        if moves_found == []:
            return False
        
        # Compare the moves to the piece type and the hint (if any)
        for a in moves_found:
            if a[0].upper() != piece_type.upper():
                continue
            
            if hint_col != -1 and a[1] != hint_col:
                continue;
            if hint_row != -1 and a[2] != hint_row:
                continue;
            
            self.moveMake(a[1], a[2], col_to, row_to, promotion)
            return True
        
        # Didn't find any matches
        return False
    
    def moveParses(self, moves):
        """
        Parses the list of moves given and plays them
        
        Keyword arguments:
        moves -- the list of moves to be played
        """
        
        split = moves.split(" ")
        
        for a in split:
            if a == '':
                continue
            if a[0].isdigit() == True:
                continue
            
            if self.moveParse(a) == False:
                return False
            
            # Find king positions
            wK_col = 0
            wK_row = 0
            bK_col = 0
            bK_row = 0
            for x in range(0, 8):
                for y in range(0, 8):
                    if self.boardGet(x, y) == "K":
                        wK_col = x
                        wK_row = y
                    if self.boardGet(x, y) == "k":
                        bK_col = x
                        bK_row = y
            
            if self.turn == "w":
                self.turn = "b"
                # See if the move put us in check
                if self.isBlackAttacking(wK_col, wK_row) == True:
                    return False
            elif self.turn == "b":
                self.turn = "w"
                self.fullMoves += 1
                # See if the move put us in check
                if self.isWhiteAttacking(bK_col, bK_row) == True:
                    return False
            
        return True
        
    def test(self, fen, moves):
        """
        Compares the FEN provided with the FEN calculated from parsing and playing the moves given
        
        Keyword arguments:
        fen   -- the expected board position in FEN notation
        moves -- the list of moves to be played
        """
        
        # Check the FEN provided is accurate before trying to test the moves against it
        r = self.setFEN(fen)
        if r == False:
            print("Invalid FEN:   {}".format(fen))
            return
        
        # Reset to startpos FEN
        r = self.setFEN(ChessGame.fen_startpos)
        if r == False:
            print("Invalid start FEN: {}".format(ChessGame.fen_startpos))
            return
        
        # Play the moves provided
        r = self.moveParses(moves)
        if r == False:
            print("Invalid moves: {}".format(moves))
            return
        
        # Get the FEN from the board now the moves have been played
        r = self.getFEN()
        if r == False:
            print("Invalid FEN:   {}".format(fen))
            return
        
        if self.fen == fen:
            print("Passed: {}".format(moves))
        else:
            print("Failed: {}".format(moves))
        
        #print("Fen:   {}".format(fen))
        #print("Moves: {}".format(moves))

class ChessBotIRCProtocol(irc.IRCClient):
    nickname = 'ChessBot'

    def __init__(self):
        self.deferred = defer.Deferred()

    def connectionLost(self, reason):
        self.deferred.errback(reason)

    def signedOn(self):
        # This is called once the server has acknowledged that we sent
        # both NICK and USER.
        for channel in self.factory.channels:
            self.join(channel)

    # Obviously, called when a PRIVMSG is received.
    def privmsg(self, user, channel, message):
        nick, _, host = user.partition('!')
        message = message.strip()
        if not message.startswith('!'):  # not a trigger command
            return  # so do nothing
        command, sep, rest = message.lstrip('!').partition(' ')
        # Get the function corresponding to the command given.
        func = getattr(self, 'command_' + command, None)
        # Or, if there was no function, ignore the message.
        if func is None:
            return
        
        command = command.lower()
        
        # maybeDeferred will always return a Deferred. It calls func(rest), and
        # if that returned a Deferred, return that. Otherwise, return the
        # return value of the function wrapped in
        # twisted.internet.defer.succeed. If an exception was raised, wrap the
        # traceback in twisted.internet.defer.fail and return that.
        
        # Add callbacks to deal with whatever the command results are.
        # If the command gives error, the _show_error callback will turn the
        # error into a terse message first
        
        if channel == self.nickname:
            # When channel == self.nickname, the message was sent to the bot
            # directly and not to a channel. So we will answer directly too:
            d = defer.maybeDeferred(func, rest)
            d.addErrback(self._showError)
            d.addCallback(self._sendMessage, nick)
        else:
            if command == "board" or command == "help" or command == "quit":
                # Otherwise, send the answer to the channel, and use the nick
                # as addressing in the message itself:
                d = defer.maybeDeferred(func, rest)
                d.addErrback(self._showError)
                d.addCallback(self._sendMessage, channel)
            else:
                # Send them a message saying to use /msg
                pass

    def _sendMessage(self, msg, target):
        self.msg(target, msg)

    def _showError(self, failure):
        return failure.getErrorMessage()
    
    def command_quit(self, rest):
        self.quit()
    
    def command_help(self, rest):
        return "IRC bot for ##chess on irc.freenode.org - https://github.com/mekhami/ChessBot#readme"
    
    def command_board(self, rest):
        game = ChessGame()
        
        if rest == "":
            return "Usage: !board <moves>"
        
        r = game.getLichessURL(rest)
        
        if r == False:
            return "Invalid moves"
        return r
    
    def command_team(self, team):
        response = urllib2.urlopen("http://en.lichess.org/api/user?team={}&nb=100".format(team))
        data = json.load(response)

        online_users = ""
        
        for a in data['list']:
            if a['online']:
                online_users += " {}".format(a['username'])

        return "{} players online:{}".format(team, online_users)

    def command_live(self, player):
        if player and len(player) <= 16:
            try:
                response = urllib2.urlopen("http://en.lichess.org/api/user/" + player)
                data = json.load(response)
                
                if data['online'] == False:
                    return "{} is currently offline on Lichess.org".format(player)
                
                url = data['playing']
                
                return "{} is playing at {}".format(player, data['playing'])
            except urllib2.HTTPError as err:
                if err.code == 404:
                    return "{} was not found on Lichess.org".format(player)
                log.err()
            except urllib2.URLError as err:
                log.err()
            except KeyError:
                return "{} is not currently playing".format(player)
        else:
            # show all channel members on lichess
            pass


class ChessIRCFactory(protocol.ReconnectingClientFactory):
    protocol = ChessBotIRCProtocol
    channels = ['##chess']

def main(reactor, description):
    endpoint = endpoints.clientFromString(reactor, description)
    factory = ChessIRCFactory()
    d = endpoint.connect(factory)
    d.addCallback(lambda protocol: protocol.deferred)
    return d

if __name__ == '__main__':
    game = ChessGame()
    
    print("##### Legal #####")
    game.test("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",         "")
    game.test("rnbqkb1r/1p2pppp/p2p1n2/8/3NP3/2N5/PPP2PPP/R1BQKB1R w KQkq - 0 6", "1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 a6")
    game.test("rnbqkb1Q/pppppp2/5n2/8/8/8/PPPPPP1P/RNBQKBNR b KQq - 0 5",         "1. g4 Nf6 2. g5 h5 3. gxh6 Ng8 4. hxg7 Nf6 5. gxh8=Q")
    game.test("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1",      "1. e4")
    game.test("rnbqkbnr/pp1ppppp/8/2p5/4P3/8/PPPP1PPP/RNBQKBNR w KQkq c6 0 2",    "1. e4 c5")
    game.test("rnbqkb1r/pppppppp/5n2/6N1/8/8/PPPPPPPP/RNBQKB1R b KQkq - 3 2",     "1. Nf3 Nf6 2. Ng5")
    game.test("rnbqkb1r/ppp1pppp/7n/8/3N4/5N2/PPPPPPPP/R1BQKB1R b KQkq - 0 6",    "1. Nf3 Nh6 2. Nc3 Ng8 3. Nd5 Nh6 4. Ne3 d5 5. Nf5 d4 6. N5xd4")
    game.test("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq e6 0 2",    "1. e4 e5")
    game.test("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq e6 0 2",    "1. e2e4 e7e5")
    game.test("rnbqkb1r/ppppn1pp/4pp2/8/8/3BPN2/PPPP1PPP/RNBQ1RK1 b kq - 3 4",    "1. Nf3 f6 2. e3 e6 3. Bd3 Ne7 4. O-O")
    game.test("r1b2k1N/ppppq1pp/1bn2n2/4p3/2B1P3/3P4/PPP3PP/RNBQ1K1R w - - 1 9",  "1. e4 e5 2. Nf3 Nc6 3. Bc4 Nf6 4. Ng5 Bc5 5. Nxf7 Bxf2+ 6. Kf1 Qe7 7. Nxh8 Bb6 8. d3 Kf8")
    game.test("rnbq1rk1/pppp1ppp/3bpn2/8/8/3BPN2/PPPP1PPP/RNBQ1RK1 w - - 4 5",    "1. Nf3 Nf6 2. e3 e6 3. Bd3 Bd6 4. O-O O-O")
    game.test("2kr1bnr/pppbqppp/2npp3/8/8/2NPP3/PPPBQPPP/2KR1BNR w - - 6 7",      "1. Nc3 Nc6 2. d3 d6 3. e3 e6 4. Bd2 Bd7 5. Qe2 Qe7 6. O-O-O O-O-O")
    print("")
    
    print("##### Illegal #####")
    game.test("rnbqkbnr/pp1ppppp/8/2p5/4P3/8/PPPP1PPP/RNBQKBNR w KQkq c6 0 2",    "1. e4 Qxh1")
    game.test("rnbqk1nr/pppp1ppp/8/4p3/1b1PN3/8/PPP1PPPP/R1BQKBNR w KQkq - 3 3",  "1. d4 e5 2. Nc3 Bb4 3. Ne4")
    game.test("rnbqkb1r/pppppppp/5n2/6N1/8/8/PPPPPPPP/RNBQKB1R b KQkq - 3 2",     "1. e3 d5 2. Bb5+ Nc6 3. d3 Ne5")
    game.test("rnbqkb1r/ppp1pppp/7n/8/3N4/5N2/PPPPPPPP/R1BQKB1R b KQkq - 0 6",    "1. e3 e6 2. Ke2 Ke7 3. Kf3 Kf6 4. Kf4 Kf5")
    game.test("rnbqkb1r/ppp1pppp/7n/8/3N4/5N2/PPPPPPPP/R1BQKB1R b KQkq - 0 6",    "1. f4 Nf6 2. Kf2 Nd5 3. Ke3")
    game.test("rn1qkbnr/p1pppppp/bp6/8/4B3/4PN2/PPPP1PPP/RNBQ1RK1 b kq - 7 5",    "1. Nf3 b6 2. e3 Ba6 3. Bd3 Nf6 4. Be4 Ng8 5. O-O")
    game.test("rnbq1rk1/pppp1ppp/4pn2/8/5b2/BPN5/P1PPPPPP/R2QKBNR w KQ - 6 6",    "1. b3 Nf6 2. Nc3 e6 3. Nb1 Bd6 4. Nc3 Bf4 5. Ba3 O-O")
    game.test("rnbq1rk1/pppp1ppp/4pn2/8/5b2/BPN5/P1PPPPPP/R2QKBNR w KQ - 6 6",    "1. f3 c5 2. Nf3")
    game.test("rnbq1rk1/pppp1ppp/4pn2/8/5b2/BPN5/P1PPPPPP/R2QKBNR w KQ - 6 6",    "1. d1e1 c5 2. Nf3")
    game.test("rnbq1rk1/pppp1ppp/4pn2/8/5b2/BPN5/P1PPPPPP/R2QKBNR w KQ - 6 6",    "1. Nf3 e5 2. f3")
    game.test("rnbq1rk1/pppp1ppp/4pn2/8/5b2/BPN5/P1PPPPPP/R2QKBNR w KQ - 6 6",    "1. Be2")
    game.test("rnbq1rk1/pppp1ppp/4pn2/8/5b2/BPN5/P1PPPPPP/R2QKBNR w KQ - 6 6",    "1. O-O")
    game.test("rnbq1rk1/pppp1ppp/4pn2/8/5b2/BPN5/P1PPPPPP/R2QKBNR w KQ - 6 6",    "1. e4 O-O")
    game.test("rnbq1rk1/pppp1ppp/4pn2/8/5b2/BPN5/P1PPPPPP/R2QKBNR w KQ - 6 6",    "1. O-O-O")
    game.test("rnbq1rk1/pppp1ppp/4pn2/8/5b2/BPN5/P1PPPPPP/R2QKBNR w KQ - 6 6",    "1. e4 O-O-O")
    game.test("rnbq1rk1/pppp1ppp/4pn2/5b2/BPN5/P1PPPPPP/R2QKBNR w KQ - 6 6",      "1. e4 c5")
    game.test("rnbq1rk1/ppZp1ppp/4pn2/8/5b2/BPN5/P1PPPPPP/R2QKBNR w KQ - 6 6",    "1. e4 e5")
    game.test("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq f9 0 2",    "1. e4 e5")
    print("")
    
    log.startLogging(sys.stderr)
    task.react(main, ['tcp:irc.freenode.net:6667'])
