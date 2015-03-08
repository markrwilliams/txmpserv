from os import environ, getpid
from sys import argv, executable
from socket import AF_INET
from twisted.web import server, resource
from twisted.internet import reactor
from twisted.web.wsgi import WSGIResource
from txmpserv.accept_thread import (prepareSignalHandler, listenTCP,
                                    adoptStreamPort)


def application(environ, start_response):
    start_response('200 OK', [('Content-type', 'text/plain')])
    return ['Hello, world from %d!' % getpid()]


def main(fd=None):
    wsgi = WSGIResource(reactor, reactor.getThreadPool(), application)
    factory = server.Site(wsgi)
    prepareSignalHandler()

    if fd is None:
        # Create a new listening port and several other processes to help out.
        port = listenTCP(reactor, 8080, factory, willBeShared=True)
        for i in range(1):
            reactor.spawnProcess(
                None, executable, [executable, __file__, str(port.fileno())],
                childFDs={0: 0, 1: 1, 2: 2, port.fileno(): port.fileno()},
                env=environ)
    else:
        # Another process created the port, just start listening on it.
        port = adoptStreamPort(reactor, fd, AF_INET, factory)

    reactor.run()


if __name__ == '__main__':
    if len(argv) == 1:
        main()
    else:
        main(int(argv[1]))
