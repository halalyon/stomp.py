import base64
import os
import sys
import time

import internal
from internal.connect import Connection
from internal.listener import ConnectionListener, StatsListener

def get_commands():
    commands = [ ]
    for f in dir(StompCLI):
        if f.startswith('_') or f.startswith('on_') or f == 'c':
            continue
        else:
            commands.append(f)
    return commands


class StompCLI(ConnectionListener):
    def __init__(self, host='localhost', port=61613, user='', passcode=''):
        self.c = Connection([(host, port)], user, passcode)
        self.c.set_listener('', self)
        self.c.start()
        self.__commands = get_commands()
        self.transaction_id = None

    def __print_async(self, frame_type, headers, body):
        print("\r  \r", end='')
        print(frame_type)
        for header_key in headers.keys():
            print('%s: %s' % (header_key, headers[header_key]))
        print('')
        print(body)
        print('> ', end='')
        sys.stdout.flush()

    def on_connecting(self, host_and_port):
        self.c.connect(wait=True)

    def on_disconnected(self):
        print("lost connection")

    def on_message(self, headers, body):
        if 'filename' in headers:
            content = base64.b64decode(body.encode())
            if os.path.exists(headers['filename']):
                fname = '%s.%s' % (headers['filename'], int(time.time()))
            else:
                fname = headers['filename']
            f = open(fname, 'wb')
            f.write(content)
            f.close()
            self.__print_async("MESSAGE", headers, "Saved file: %s" % fname)
        else:
            self.__print_async("MESSAGE", headers, body)

    def on_error(self, headers, body):
        self.__print_async("ERROR", headers, body)

    def on_receipt(self, headers, body):
        self.__print_async("RECEIPT", headers, body)

    def on_connected(self, headers, body):
        self.__print_async("CONNECTED", headers, body)

    def ack(self, args):
        '''
        Usage:
            ack <message-id>

        Required Parameters:
            message-id - the id of the message being acknowledged

        Description:
            The command 'ack' is used to acknowledge consumption of a message from a subscription using client
            acknowledgment. When a client has issued a 'subscribe' with the ack flag set to client, any messages
            received from that destination will not be considered to have been consumed (by the server) until
            the message has been acknowledged.
        '''
        if not self.transaction_id:
            self.c.ack(headers = { 'message-id' : args[1] })
        else:
            self.c.ack(headers = { 'message-id' : args[1] }, transaction=self.transaction_id)

    def abort(self, args):
        '''
        Usage:
            abort

        Description:
            Roll back a transaction in progress.
        '''
        if not self.transaction_id:
            print("Not currently in a transaction")
        else:
            self.c.abort(transaction = self.transaction_id)
            self.transaction_id = None

    def begin(self, args):
        '''
        Usage:
            begin

        Description:
            Start a transaction. Transactions in this case apply to sending and acknowledging -
            any messages sent or acknowledged during a transaction will be handled atomically based on the
            transaction.
        '''
        if self.transaction_id:
            print("Currently in a transaction (%s)" % self.transaction_id)
        else:
            self.transaction_id = self.c.begin()
            print('Transaction id: %s' % self.transaction_id)

    def commit(self, args):
        '''
        Usage:
            commit

        Description:
            Commit a transaction in progress.
        '''
        if not self.transaction_id:
            print("Not currently in a transaction")
        else:
            print('Committing %s' % self.transaction_id)
            self.c.commit(transaction=self.transaction_id)
            self.transaction_id = None

    def disconnect(self, args):
        '''
        Usage:
            disconnect

        Description:
            Gracefully disconnect from the server.
        '''
        try:
            self.c.disconnect()
        except NotConnectedException:
            pass # ignore if no longer connected

    def send(self, args):
        '''
        Usage:
            send <destination> <message>

        Required Parameters:
            destination - where to send the message
            message - the content to send

        Description:
            Sends a message to a destination in the messaging system.
        '''
        if len(args) < 3:
            print('Expecting: send <destination> <message>')
        elif not self.transaction_id:
            self.c.send(destination=args[1], message=' '.join(args[2:]))
        else:
            self.c.send(destination=args[1], message=' '.join(args[2:]), transaction=self.transaction_id)

    def sendfile(self, args):
        '''
        Usage:
            sendfile <destination> <filename>

        Required Parameters:
            destination - where to send the message
            filename - the file to send

        Description:
            Sends a file to a destination in the messaging system.
        '''
        if len(args) < 3:
            print('Expecting: sendfile <destination> <filename>')
        elif not os.path.exists(args[2]):
            print('File %s does not exist' % args[2])
        else:
            s = open(args[2], mode='rb').read()
            msg = base64.b64encode(s).decode()
            if not self.transaction_id:
                self.c.send(destination=args[1], message=msg, filename=args[2])
            else:
                self.c.send(destination=args[1], message=msg, filename=args[2], transaction=self.transaction_id)
            
    def subscribe(self, args):
        '''
        Usage:
            subscribe <destination> [ack]

        Required Parameters:
            destination - the name to subscribe to

        Optional Parameters:
            ack - how to handle acknowledgements for a message; either automatically (auto) or manually (client)

        Description:
            Register to listen to a given destination. Like send, the subscribe command requires a destination
            header indicating which destination to subscribe to. The ack parameter is optional, and defaults to
            auto.
        '''
        if len(args) < 2:
            print('Expecting: subscribe <destination> [ack]')
        elif len(args) > 2:
            print('Subscribing to "%s" with acknowledge set to "%s"' % (args[1], args[2]))
            self.c.subscribe(destination=args[1], ack=args[2])
        else:
            print('Subscribing to "%s" with auto acknowledge' % args[1])
            self.c.subscribe(destination=args[1], ack='auto')

    def unsubscribe(self, args):
        '''
        Usage:
            unsubscribe <destination>

        Required Parameters:
            destination - the name to unsubscribe from

        Description:
            Remove an existing subscription - so that the client no longer receive messages from that destination.
        '''
        if len(args) < 2:
            print('Expecting: unsubscribe <destination>')
        else:
            print('Unsubscribing from "%s"' % args[1])
            self.c.unsubscribe(destination=args[1])

    def stats(self, args):
        '''
        Usage:
            stats [on|off]
            
        Description:
            Record statistics on messages sent, received, errors, etc. If no argument (on|off) is specified,
            dump the current statistics.
        '''
        if len(args) < 2:
            stats = self.c.get_listener('stats')
            if stats:
                print(stats)
            else:
                print('No stats available')
        elif args[1] == 'on':
            self.c.set_listener('stats', StatsListener())
        elif args[1] == 'off':
            self.c.remove_listener('stats')
        else:
            print('Expecting: stats [on|off]')

    def help(self, args):
        '''
        Usage:
            help [command]

        Description:
            Display info on a specified command, or a list of available commands
        '''
        if len(args) == 1:
            print('Usage: help <command>, where command is one of the following:')
            print('    ')
            for f in self.__commands:
                print('%s ' % f, end='')
            print('')
            return
        elif not hasattr(self, args[1]):
            print('There is no command "%s"' % args[1])
            return

        func = getattr(self, args[1])
        if hasattr(func, '__doc__') and getattr(func, '__doc__') is not None:
            print(func.__doc__)
        else:
            print('There is no help for command "%s"' % args[1])

    def version(self, args):
        print('Stomp.py Version %s.%s' % internal.__version__)
    ver = version


def main():
    # If the readline module is available, make command input easier
    try:
        import readline
        def stomp_completer(text, state):
            commands = get_commands()
            for command in commands[state:]:
                if command.startswith(text):
                    return "%s " % command
            return None

        readline.parse_and_bind("tab: complete")
        readline.set_completer(stomp_completer)
        readline.set_completer_delims("")
    except ImportError:
        pass # ignore unavailable readline module

    if len(sys.argv) > 5:
        print('USAGE: stomp.py [host] [port] [user] [passcode]')
        sys.exit(1)

    if len(sys.argv) >= 2:
        host = sys.argv[1]
    else:
        host = "localhost"

    if len(sys.argv) >= 3:
        port = int(sys.argv[2])
    else:
        port = 61613

    if len(sys.argv) >= 5:
        user = sys.argv[3]
        passcode = sys.argv[4]
    else:
        user = None
        passcode = None

    st = StompCLI(host, port, user, passcode)
    try:
        while True:
            line = input("\r> ")
            if not line or line.lstrip().rstrip() == '':
                continue
            line = line.lstrip().rstrip()
            if line.startswith('quit') or line.startswith('disconnect'):
                break
            split = line.split()
            command = split[0]
            if not command.startswith("on_") and hasattr(st, command):
                getattr(st, command)(split)
            else:
                print('unrecognized command')
    except EOFError:
        pass
    except KeyboardInterrupt:
        pass
    finally:
        st.disconnect(None)



#
# command line testing
#
if __name__ == '__main__':
    main()