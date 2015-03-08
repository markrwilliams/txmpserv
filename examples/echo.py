#!/usr/bin/env python

# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

from twisted.python import log
import sys
from twisted.internet.protocol import Protocol, Factory
from twisted.internet import reactor
from txmpserv.accept_thread import listenTCP, prepareSignalHandler

### Protocol Implementation

# This is just about the simplest possible protocol
class Echo(Protocol):
    def dataReceived(self, data):
        """
        As soon as any data is received, write it back.
        """
        self.transport.write(data)


def main():
    log.startLogging(sys.stdout)
    f = Factory()
    f.protocol = Echo
    prepareSignalHandler()
    listenTCP(reactor, 8000, f)
    reactor.run()

if __name__ == '__main__':
    main()
