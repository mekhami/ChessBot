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
        parts = fen.split(" ")
        
        # Starting at A8, moving right, then coming down a row
        sq = 56
        for a in range(0, len(parts[0])):
            if(parts[0][a].isalpha()):
                self.boardSet(sq%8, sq/8, parts[0][a])
                sq += 1
            elif(parts[0][a] == "/"):
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
        if(len(parts) >= 1):
            if(parts[1] == "w"):
                self.turn = "w"
            elif(parts[1] == "b"):
                self.turn = "b"
        else:
            self.turn = "w"
        
        # Castling
        if(len(parts) >= 2):
            self.castling = parts[2]
        
        # ep square
        if(len(parts) >= 3):
            self.ep = parts[3]
        
        # Halfmoves since last capture or pawn advance
        if(len(parts) >= 4):
            self.fiftyMoves = int(parts[4])
        
        # Full moves since last capture or pawn advance
        if(len(parts) >= 5):
            self.fullMoves = int(parts[5])
    
    def getFEN(self):
        fen = ""
        
        # Iterate through the board
        spaces = 0
        for y in range(0, 8):
            for x in range(0, 8):
                piece = self.boardGet(x, 7-y)
                if(piece == "-"):
                    spaces += 1
                else:
                    if(spaces > 0):
                        fen += str(spaces)
                        spaces = 0
                    fen += piece
            if(spaces > 0):
                fen += str(spaces)
                spaces = 0
            if(y < 7):
                fen += "/"
        
        fen += " "
        fen += self.turn
        
        fen += " "
        fen += self.castling
        
        fen += " "
        fen += self.ep
        
        fen += " "
        fen += str(self.fiftyMoves)
        
        fen += " "
        fen += str(self.fullMoves)
        
        return fen
    
    def getLichessURL(self, moves):
        self.setFEN(ChessGame.fen_startpos)
        r = self.moveParses(moves)
        
        if(r == False):
            return "Invalid moves"
        
        fen = self.getFEN()
        fen = fen.replace(" ", "_")
        
        return "http://lichess.org/editor/{}".format(fen)

    def printBoard(self):
        for y in range(0, 8):
            for x in range(0, 8):
                sys.stdout.write(self.boardGet(x, 7-y))
            sys.stdout.write("\n")
        print("Turn: {}".format(self.turn))
        print("Castling: {}".format(self.castling))
    
    def posGetCol(self, str):
        return ord(str[0]) - 97
    
    def posGetRow(self, str):
        return int(str[1]) - 1
    
    def boardGet(self, col, row):
        return self.board[col+2][row+2]
    
    def boardSet(self, col, row, piece):
        self.board[col+2][row+2] = piece
    
    def findMoveWP(self, col_to, row_to, hint="-"):
        if(hint != "-"):
            return [self.posGetCol(hint), row_to-1]
        else:
            if(self.boardGet(col_to, row_to-1) == "P"):
                return [col_to, row_to-1]
            elif(self.boardGet(col_to, row_to-2) == "P"):
                return [col_to, row_to-2]
            else:
                return None
    
    def findMoveBP(self, col_to, row_to, hint="-"):
        if(hint != "-"):
            return [self.posGetCol(hint), row_to+1]
        else:
            if(self.boardGet(col_to, row_to+1) == "p"):
                return [col_to, row_to+1]
            elif(self.boardGet(col_to, row_to+2) == "p"):
                return [col_to, row_to+2]
            else:
                return None
    
    def findMoveN(self, piece, col_to, row_to, hint="-"):
        results = []
    
        if(self.boardGet(col_to-1, row_to+2) == piece): # Up 2 left 1
            results.append([col_to-1, row_to+2])
        if(self.boardGet(col_to+1, row_to+2) == piece): # Up 2 right 1
            results.append([col_to+1, row_to+2])
        if(self.boardGet(col_to-1, row_to-2) == piece): # Down 2 left 1
            results.append([col_to-1, row_to-2])
        if(self.boardGet(col_to+1, row_to-2) == piece): # Down 2 right 1
            results.append([col_to+1, row_to-2])
        if(self.boardGet(col_to+2, row_to+1) == piece): # Right 2 up 1
            results.append([col_to+2, row_to+1])
        if(self.boardGet(col_to+2, row_to-1) == piece): # Right 2 down 1
            results.append([col_to+2, row_to-1])
        if(self.boardGet(col_to-2, row_to+1) == piece): # Left 2 up 1
            results.append([col_to-2, row_to+1])
        if(self.boardGet(col_to-2, row_to-1) == piece): # Left 2 down 1
            results.append([col_to-2, row_to-1])
        
        if not results:
            return None
        
        if(hint == "-"):
            return results[0]
        
        # Find the result that matches the hint
        for a in results:
            if(hint.isalpha() == True):
                if(a[0] == ord(hint) - 97):
                    return a
            else:
                if(a[1] == int(hint)-1):
                    return a
        
        return None
    
    def findMoveDiagonal(self, piece, col_to, row_to, hint="-"):
        results = []
        
        # Up and right
        for a in range(1, 8):
            if(self.boardGet(col_to+a, row_to+a) != "-"):
                if(self.boardGet(col_to+a, row_to+a) == piece):
                    results.append([col_to+a, row_to+a])
                break
        
        # Up and left
        for a in range(1, 8):
            if(self.boardGet(col_to-a, row_to+a) != "-"):
                if(self.boardGet(col_to-a, row_to+a) == piece):
                    results.append([col_to-a, row_to+a])
                break
        
        # Down and right
        for a in range(1, 8):
            if(self.boardGet(col_to+a, row_to-a) != "-"):
                if(self.boardGet(col_to+a, row_to-a) == piece):
                    results.append([col_to+a, row_to-a])
                break
        
        # Down and left
        for a in range(1, 8):
            if(self.boardGet(col_to-a, row_to-a) != "-"):
                if(self.boardGet(col_to-a, row_to-a) == piece):
                    results.append([col_to-a, row_to-a])
                break
        
        if not results:
            return None
        
        if(hint == "-"):
            return results[0]
        
        # Find the result that matches the hint
        for a in results:
            if(hint.isalpha() == True):
                if(a[0] == ord(hint) - 97):
                    return a
            else:
                if(a[1] == int(hint)):
                    return a
    
    def findMoveStraight(self, piece, col_to, row_to, hint="-"):
        results = []
        
        # Right
        for a in range(1, 8):
            if(self.boardGet(col_to+a, row_to) != "-"):
                if(self.boardGet(col_to+a, row_to) == piece):
                    results.append([col_to+a, row_to])
                break
        
        # Left
        for a in range(1, 8):
            if(self.boardGet(col_to-a, row_to) != "-"):
                if(self.boardGet(col_to-a, row_to) == piece):
                    results.append([col_to-a, row_to])
                break
        
        # Up
        for a in range(1, 8):
            if(self.boardGet(col_to, row_to+a) != "-"):
                if(self.boardGet(col_to, row_to+a) == piece):
                    results.append([col_to, row_to+a])
                break
        
        # Down
        for a in range(1, 8):
            if(self.boardGet(col_to, row_to-a) != "-"):
                if(self.boardGet(col_to, row_to-a) == piece):
                    results.append([col_to, row_to-a])
                break
        
        if not results:
            return None
        
        if(hint == "-"):
            return results[0]
        
        # Find the result that matches the hint
        for a in results:
            if(hint.isalpha() == True):
                if(a[0] == ord(hint) - 97):
                    return a
            else:
                if(a[1] == int(hint)):
                    return a
        
        return None
    
    def findMoveKing(self, piece, col_to, row_to, hint="-"):
        results = []
        
        if(self.boardGet(col_to, row_to+1) == piece): # Up 1
            results.append([col_to, row_to+1])
        if(self.boardGet(col_to, row_to-1) == piece): # Down 1
            results.append([col_to, row_to-1])
        if(self.boardGet(col_to+1, row_to) == piece): # Right 1
            results.append([col_to+1, row_to])
        if(self.boardGet(col_to-1, row_to) == piece): # Left 1
            results.append([col_to-1, row_to])
        if(self.boardGet(col_to+1, row_to+1) == piece): # Up 1 right 1
            results.append([col_to+1, row_to+1])
        if(self.boardGet(col_to-1, row_to+1) == piece): # Up 1 left 1
            results.append([col_to-1, row_to+1])
        if(self.boardGet(col_to+1, row_to-1) == piece): # Down 1 right 1
            results.append([col_to+1, row_to-1])
        if(self.boardGet(col_to-1, row_to-1) == piece): # Down 1 left 1
            results.append([col_to-1, row_to-1])
        
        if not results:
            return None
        
        return results[0]
    
    def isWhiteAttacking(self, col, row):
        if(self.boardGet(col-1, row-1) == "P"):
            return True
        elif(self.boardGet(col+1, row-1) == "P"):
            return True
        elif(self.findMoveN("N", col, row) != None):
            return True;
        elif(self.findMoveDiagonal("B", col, row) != None):
            return True;
        elif(self.findMoveStraight("R", col, row) != None):
            return True;
        elif(self.findMoveDiagonal("Q", col, row) != None):
            return True;
        elif(self.findMoveStraight("Q", col, row) != None):
            return True;
        elif(self.findMoveKing("K", col, row) != None):
            return True;
        else:
            return False
    
    def isBlackAttacking(self, col, row):
        if(self.boardGet(col-1, row+1) == "p"):
            return True
        elif(self.boardGet(col+1, row+1) == "p"):
            return True
        elif(self.findMoveN("n", col, row) != None):
            return True;
        elif(self.findMoveDiagonal("b", col, row) != None):
            return True;
        elif(self.findMoveStraight("r", col, row) != None):
            return True;
        elif(self.findMoveDiagonal("q", col, row) != None):
            return True;
        elif(self.findMoveStraight("q", col, row) != None):
            return True;
        elif(self.findMoveKing("k", col, row) != None):
            return True;
        else:
            return False
    
    def colRowToStr(self, col, row):
        return chr(col + 97) + chr(row + 49)
    
    def moveMake(self, from_col, from_row, to_col, to_row, promotion="-"):
        # 50 move rule
        if(self.boardGet(to_col, to_row) != "-" or self.boardGet(from_col, from_row) == "P" or self.boardGet(from_col, from_row) == "p"):
            self.fiftyMoves = 0
        else:
            self.fiftyMoves += 1
        
        # White castle permissions
        if((from_col == 4 and from_row == 0) or (to_col == 4 and to_row == 0)): # White king position
            self.castling = self.castling.replace("K", "")
            self.castling = self.castling.replace("Q", "")
        if((from_col == 0 and from_row == 0) or (to_col == 0 and to_row == 0)): # White a1 rook position
            self.castling = self.castling.replace("Q", "")
        if((from_col == 7 and from_row == 0) or (to_col == 7 and to_row == 0)): # White h1 rook position
            self.castling = self.castling.replace("K", "")
        # Black castle permissions
        if((from_col == 4 and from_row == 7) or (to_col == 4 and to_row == 7)): # Black king position
            self.castling = self.castling.replace("k", "")
            self.castling = self.castling.replace("q", "")
        if((from_col == 0 and from_row == 7) or (to_col == 0 and to_row == 7)): # Black a1 rook position
            self.castling = self.castling.replace("q", "")
        if((from_col == 7 and from_row == 7) or (to_col == 7 and to_row == 7)): # Black h1 rook position
            self.castling = self.castling.replace("k", "")
        
        if(self.castling == ""):
            self.castling = "-"
        
        # Capture ep white
        if(self.ep != "-" and self.boardGet(from_col, from_row) == "P"):
            if(self.posGetCol(self.ep) == to_col and self.posGetCol(self.ep) == to_col):
                self.boardSet(self.posGetCol(self.ep), self.posGetRow(self.ep)-1, "-")
        # Capture ep black
        if(self.ep != "-" and self.boardGet(from_col, from_row) == "p"):
            if(self.posGetCol(self.ep) == to_col and self.posGetCol(self.ep) == to_col):
                self.boardSet(self.posGetCol(self.ep), self.posGetRow(self.ep)+1, "-")
        
        # Play the move
        if(promotion == "-"):
            self.boardSet(to_col, to_row, self.boardGet(from_col, from_row))
        else:
            self.boardSet(to_col, to_row, promotion)
        self.boardSet(from_col, from_row, "-")
        
        # Set the ep square
        if(self.boardGet(to_col, to_row) == "P" and to_row - from_row == 2):
            self.ep = self.colRowToStr(to_col, to_row-1)
        elif(self.boardGet(to_col, to_row) == "p" and to_row - from_row == -2):
            self.ep = self.colRowToStr(to_col, to_row+1)
        else:
            self.ep = "-"
        
        return
    
    def moveMakeWKSC(self):
        self.moveMake(4,0, 6,0) # King
        self.moveMake(7,0, 5,0) # Rook
    
    def moveMakeBKSC(self):
        self.moveMake(4,7, 6,7) # King
        self.moveMake(7,7, 5,7) # Rook
    
    def moveMakeWQSC(self):
        self.moveMake(4,0, 2,0) # King
        self.moveMake(0,0, 3,0) # Rook
    
    def moveMakeBQSC(self):
        self.moveMake(4,7, 2,7) # King
        self.moveMake(0,7, 3,7) # Rook
    
    def moveParse(self, move):
        # Remove irrelevant characters
        strip = "!?+#x-:="
        for a in strip:
            move = move.replace(a, "")
        
        # Special case of castling
        if(move == "OO" or move == "00"):
            if(self.turn == "w"):
                self.moveMakeWKSC()
                return
            elif(self.turn == "b"):
                self.moveMakeBKSC()
                return
        elif(move == "OOO" or move == "000"):
            if(self.turn == "w"):
                self.moveMakeWQSC()
                return
            elif(self.turn == "b"):
                self.moveMakeBQSC()
                return
        
        # If we're supplied with a piece type - Store and remove it e.g. (Nf3 ---> f3)
        piece_type = "P"
        if(move[0].isupper()):
            piece_type = move[0]
            move = move[1:]
        
        # If the move is a promotion - store and remove it e.g. (a8Q ---> a8)
        promotion = "-"
        if(move[-1:].isalpha()):
            promotion = move[-1:]
            move = move[:-1]
        
        # By this point we should be left with either 2 or 3 characters
        # Comparing the first and the last two characters will highlight extra information about row & col
        # Move        Stripped       First         Second   Additional information
        # Nf3    ---> f3        ---> f3      ==    f3       None
        # Ngf3   ---> fg3       ---> fg      !=    g3       Piece originates from the f column
        # e4     ---> e4        ---> e4      ==    e4       None
        # N5xd4  ---> 5d4       ---> 5d      !=    d4       Piece originates from the 5th row
        
        if(len(move) != 2 and len(move) != 3):
            return False
        
        first_chunk = move[:2]
        second_chunk = move[-2:]
        
        hint = "-"
        if(first_chunk == second_chunk):
            pass
        else:
            hint = first_chunk[0]
            move = move[1:]
        
        # Convert the move to col & row
        col_to = self.posGetCol(move)
        row_to = self.posGetRow(move)
        
        move_found = None
        if(self.turn == "w"):
            if(piece_type == "P"):
                move_found = self.findMoveWP(col_to, row_to, hint)
            elif(piece_type == "N"):
                move_found = self.findMoveN("N", col_to, row_to, hint)
            elif(piece_type == "B"):
                move_found = self.findMoveDiagonal("B", col_to, row_to, hint)
            elif(piece_type == "R"):
                move_found = self.findMoveStraight("R", col_to, row_to, hint)
            elif(piece_type == "Q"):
                move_found = self.findMoveDiagonal("Q", col_to, row_to, hint)
                if(move_found == None):
                    move_found = self.findMoveStraight("Q", col_to, row_to, hint)
            elif(piece_type == "K"):
                move_found = self.findMoveKing("K", col_to, row_to)
        elif(self.turn == "b"):
            if(piece_type == "P"):
                move_found = self.findMoveBP(col_to, row_to, hint)
            elif(piece_type == "N"):
                move_found = self.findMoveN("n", col_to, row_to, hint)
            elif(piece_type == "B"):
                move_found = self.findMoveDiagonal("b", col_to, row_to, hint)
            elif(piece_type == "R"):
                move_found = self.findMoveStraight("r", col_to, row_to, hint)
            elif(piece_type == "Q"):
                move_found = self.findMoveDiagonal("q", col_to, row_to, hint)
                if(move_found == None):
                    move_found = self.findMoveStraight("q", col_to, row_to, hint)
            elif(piece_type == "K"):
                move_found = self.findMoveKing("k", col_to, row_to)
        
        # If any moves fit the criteria, play the move
        if(move_found != None):
            self.moveMake(move_found[0], move_found[1], col_to, row_to, promotion)
            return True
        # If not, the move must've been illegal
        return False
    
    def moveParses(self, moves):
        split = moves.split(" ")
        
        for a in split:
            if(a == ''):
                continue
            if(a[0].isdigit() == True):
                continue
            
            if(self.moveParse(a) == False):
                return False
            
            # Find king positions
            wK_col = 0
            wK_row = 0
            bK_col = 0
            bK_row = 0
            for x in range(0, 8):
                for y in range(0, 8):
                    if(self.boardGet(x, y) == "K"):
                        wK_col = x
                        wK_row = y
                    if(self.boardGet(x, y) == "k"):
                        bK_col = x
                        bK_row = y
            
            if(self.turn == "w"):
                self.turn = "b"
                # See if the move put us in check
                if(self.isBlackAttacking(wK_col, wK_row) == True):
                    return False
            elif(self.turn == "b"):
                self.turn = "w"
                self.fullMoves += 1
                # See if the move put us in check
                if(self.isWhiteAttacking(bK_col, bK_row) == True):
                    return False
            
        return True
        
    def test(self, fen, moves):
        self.setFEN(ChessGame.fen_startpos)
        r = self.moveParses(moves)
        
        print("Moves:    " + moves)
        
        if(r == False):
            print("Invalid moves")
            print("")
            return
        
        self.fen = self.getFEN()
        
        print("Expected: " + fen)
        print("Result:   " + self.fen)
        
        if(fen == self.fen):
            print("Pass")
        else:
            print("Fail")
        print("")


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
        # maybeDeferred will always return a Deferred. It calls func(rest), and
        # if that returned a Deferred, return that. Otherwise, return the
        # return value of the function wrapped in
        # twisted.internet.defer.succeed. If an exception was raised, wrap the
        # traceback in twisted.internet.defer.fail and return that.
        d = defer.maybeDeferred(func, rest)
        # Add callbacks to deal with whatever the command results are.
        # If the command gives error, the _show_error callback will turn the
        # error into a terse message first:
        d.addErrback(self._showError)
        # Whatever is returned is sent back as a reply:
        if channel == self.nickname:
            # When channel == self.nickname, the message was sent to the bot
            # directly and not to a channel. So we will answer directly too:
            d.addCallback(self._sendMessage, nick)
        else:
            # Otherwise, send the answer to the channel, and use the nick
            # as addressing in the message itself:
            d.addCallback(self._sendMessage, channel, nick)

    def _sendMessage(self, msg, target, nick=None):
        if nick:
            msg = '%s, %s' % (nick, msg)
        self.msg(target, msg)

    def _showError(self, failure):
        return failure.getErrorMessage()

    def command_board(self, rest):
        game = ChessGame()
        return "Lichess url: {}".format(game.getLichessURL(rest))

    def command_team(self, rest):
        teamname = rest.partition(' ')
        if teamname[0]:
            try:
                response = urllib2.urlopen("http://en.lichess.org/api/user?team={}&nb=100".format(teamname[0]))
                data = json.load(response)
            except:
                return
            online_users = ""
            
            for a in data['list']:
                try:
                    if(a['online']):
                        online_users += " {}".format(a['username'])
                except:
                    pass
            return "{} players online:{}".format(teamname[0], online_users)

    def command_live(self, rest):
        player = rest.partition(' ')
        if player[0]:
            try:
                response = urllib2.urlopen("http://en.lichess.org/api/user/" + player[0])
                data = json.load(response)
                return "{} is playing at {}".format(player[0], data['playing'])
            except urllib2.HTTPError as err:
                if(err.code == 404):
                    return "{} was not found on Lichess.org".format(player[0])
                return "HTTPError ({}) - {}".format(err.code, err.reason)
            except urllib2.URLError as err:
                return "URLError - {}".format(err.reason)
            except KeyError:
                return "{} is not currently playing".format(player[0])
        else:
            # show all channel members on lichess
            pass


class ChessIRCFactory(protocol.ReconnectingClientFactory):
    protocol = ChessBotIRCProtocol
    channels = ['#chesstest']

def main(reactor, description):
    endpoint = endpoints.clientFromString(reactor, description)
    factory = ChessIRCFactory()
    d = endpoint.connect(factory)
    d.addCallback(lambda protocol: protocol.deferred)
    return d

if __name__ == '__main__':
    log.startLogging(sys.stderr)
    task.react(main, ['tcp:irc.freenode.net:6667'])
