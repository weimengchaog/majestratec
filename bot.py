#!/usr/bin/env python2.7
#
# irc xdcc serve bot
#


from irc.client import SimpleIRCClient as IRC
from irc.client import ip_quad_to_numstr
import irc.logging
import logging
import re
import struct
import sys
import os

class ServBot(IRC):
    
    
    def __init__(self, chan, root):
        self._log = logging.getLogger('ServBot-%s' % chan)
        IRC.__init__(self)
        self._chan = str(chan)
        if not os.path.exists(root):
            os.mkdir(root)
        self._root = root
        self._sendq = []
        self._dcc = None
        self._file = None
        self._filesize = -1
        self.ircobj.execute_every(1, self._pump)

    def _pump(self):
        if self.connection.is_connected():
            if len(self._sendq) > 0 and self._dcc is None:

                nick, file = self._sendq.pop()
                nick = nick.split('!')[0]
                self._log.info('sendfile: %s %s' % (nick, file))
                size = os.path.getsize(file)
                self._dcc = self.dcc_listen('raw')
                self._file = open(file,'rb')
                self._filesize = size
                self.connection.ctcp('DCC', nick, 'SEND %s %s %d %d' % (os.path.basename(file), 
                                                                        ip_quad_to_numstr(self._dcc.localaddress), 
                                                                        self._dcc.localport,
                                                                        size))
    def on_dcc_connect(self, conn, event):
        self._send_chunk()

    def on_dcc_disconnect(self, conn, event):
        self._file.close()
        self._dcc.disconnect()
        self._file = None
        self._filesize = -1
        self._dcc = None

    
    def _send_chunk(self):
        data = self._file.read(1024)
        self._dcc.send_bytes(data)
        sent = len(data)

    def on_dccmsg(self, connection, event):
        acked = struct.unpack('!I', event.arguments[0])
        if acked == self._filesize:
            self._dcc.disconnect()
            self._file.close()
            self._file = None
            self._filesize = -1
            self._dcc = None
        else:
            self._log.info('acked: %d' % acked)
            self._send_chunk()

    def on_welcome(self, conn, event):
        self._log.info('connected')
        self.connection.join(self._chan)


    def on_join(self, conn, event):
        if event.target == self._chan:
            self._log.info('joined channel')
        else:
            self._log.warning('joined unrequested channel: %s' % event.target)


    def on_disconnect(self, conn, event):
        conn.reconnect()

    def on_pubmsg(self, conn, event):
        msg = ''.join(event.arguments)
        if msg.startswith('\\'):
            args = msg.split()
            cmd = args[0][1:]
            args = args[1:]
            result = self._do_cmd(event.source, cmd, args)
            for line in result:
                conn.privmsg(event.target, line)

    def _do_cmd(self,nick, cmd, args):
        _cmd = 'cmd_' + cmd
        if hasattr(self, _cmd):
            try:
                self._log.info(_cmd)
                return getattr(self, _cmd)(nick, args)
            except Exception as e:
                return ['error: %s' % e]
        else:
            return ['no such command: ' + cmd]


    def cmd_ping(self,nick, args):
        return ['pong']

    def _walk_find(self, check):
        found = []
        for root, dirs, files in os.walk(self._root):
            for file in files:
                if check(file):
                    found.append(file)
        ret = [ '%d matches' % len(found) ]
        
        for match in found[:5]:
            size = os.path.getsize(os.path.join(self._root, match))
            ret.append(match + ' - size: %dB' % size)
        return ret

    def _do_dcc(self ,nick, file):
        self._sendq.append((nick, file))
        
    def cmd_help(self, nick, args):
        return ['use \\regex , \\find and \\get', 'make sure to /quote dccallow +xdccbot']

    def cmd_get(self, nick, args):
        file = ' '.join(args)
        if os.sep in file:
            return ['invalid filename']
        file = os.path.join(self._root, file)
        if os.path.exists(file):
            self._do_dcc(nick, file)
            return ['your request has been queued']
        else:
            return ['no such file']
    
    def cmd_find(self, nick, args):
        search = ' '.join(args)
        self._log.info('checking %s for %s' % ( self._root, search))
        def check(file):
            return search in file
        return self._walk_find(check)

    def cmd_regex(self, nick, args):
        self._log.info('checking %s for regexp %s' % (self._root, args[0]))
        r = re.compile(args[0])
        def check(file):
            return r.match(file) is not None
        return self._walk_find(check)

def main():
    log = logging.getLogger('main')
    
    def fatal(msg):
        log.error(msg)
        sys.exit(1)

    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--server', type=str, required=True)
    ap.add_argument('--chan', type=str, required=True)
    ap.add_argument('--debug', action='store_const', const=True, default=False)

    args = ap.parse_args()
    if args.debug:
        lvl = logging.DEBUG
    else:
        lvl = logging.INFO

    logging.basicConfig(level=lvl)
    
    host, port = None, None
    serv = args.server.split(':')
    if len(serv) == 2:
        try:
            host, port = serv[0], int(serv[1])
        except:
            fatal('bad port number: %s' % serv[1])
    elif len(serv) == 1:
        host, port = serv[0], 6667
    else:
        fatal('incorrect server format')

    bot = ServBot(args.chan, os.path.join(os.environ['HOME'], '.xdcc'))
    
    try:
        log.info('connecting to %s:%d' % (host, port))
        bot.connect(host, port, 'xdccbot')
    except Exception as e:
        fatal(str(e))

    log.info('starting')
    try:
        bot.start()
    except:
        bot.connection.disconnect('bai')


if __name__ == '__main__':
    main()