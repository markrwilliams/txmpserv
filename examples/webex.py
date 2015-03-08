from os import environ, getpid
from sys import argv, executable
from socket import AF_INET
from twisted.web import server, resource
from twisted.internet import reactor
from txmpserv.accept_thread import (prepareSignalHandler, listenTCP,
                                    adoptStreamPort)


class Counter(resource.Resource):
    isLeaf = True
    numberRequests = 0

    def render_GET(self, request):
        self.numberRequests += 1
        request.setHeader("content-type", "text/plain")
        return "I am %s and this is request #%s\n" % (getpid(),
                                                      str(self.numberRequests))


def main(fd=None):
    counter = Counter()
    factory = server.Site(counter)
    prepareSignalHandler()

    if fd is None:
        # Create a new listening port and several other processes to help out.
        port = listenTCP(reactor, 8080, factory, willBeShared=True)
        for i in range(8):
            reactor.spawnProcess(
                None, executable, [executable, __file__,
                                   str(port.realFileno())],
                childFDs={0: 0, 1: 1, 2: 2,
                          port.realFileno(): port.realFileno()},
                env=environ)
    else:
        # Another process created the port, just start listening on it.
        port = adoptStreamPort(reactor, fd, AF_INET, factory)

    reactor.run()
    print getpid(), counter.numberRequests


if __name__ == '__main__':
    if len(argv) == 1:
        main()
    else:
        main(int(argv[1]))
