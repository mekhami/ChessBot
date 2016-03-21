import sys
import urllib.request

from twisted.internet import defer, endpoints, protocol, reactor, task
from twisted.python import log
from twisted.words.protocols import irc

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

    def command_live(self, rest):
        player = rest.partition(' ')
        if player:
            # find the player on lichess
            try:
                f = urllib.request.urlopen("http://en.lichess.org/api/user/" + player).read().decode("utf-8")
            except urllib.error.HTTPError as err:
                if(err.code == 404):
                    return player + " was not found on Lichess.org"
                return "HTTPError (" + str(err.code) + ") - " + err.reason
            except urllib.error.URLError as err:
                return "URLError - " + err.reason
            
            for a in f.split(','):
                if(a.find("\"playing\":\"") == 0):
                    return player + " is playing at " + a[11:-1]
            
            return player + " is not currently playing"
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
