import signal
import errno
import socket
import os

from twisted.internet.tcp import Port
from twisted.internet import fdesc, error
from twisted.python import log
from threading import RLock
from txmpserv.interruptable_thread import InterruptableThread, noop


def prepareSignalHandler(sig=InterruptableThread.interruptSignal):
    signal.signal(sig, noop)


class ThreadedAcceptPort(Port):
    socketIsShared = False

    def __init__(self, *args, **kwargs):
        Port.__init__(self, *args, **kwargs)
        self.acceptThread = None

    def createInternetSocket(self):
        s = socket.socket(self.addressFamily, self.socketType)
        fdesc._setCloseOnExec(s.fileno())
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s

    def _doAccept(self):
        try:
            # disconnecting is apparently set by loseConnection, which
            # calls stopReading first, which will send a signal to
            # interrupt this thread.  In the event that we hit this
            # test before we hit .accept(), go ahead and check for it
            # as an exit condition.
            while not self.disconnecting:
                try:
                    skt, addr = self.socket.accept()
                except socket.error as e:
                    # EINTR means we were sent a signal, at the least
                    # the one this thread responds to;
                    # EINVAL means this socket was shutdown
                    if e.args[0] in (errno.EINTR, errno.EINVAL):
                        return
                    elif e.args[0] == errno.EPERM:
                        # Netfilter on Linux may have rejected the
                        # connection, but we get told to try to accept()
                        # anyway.
                        continue
                    elif e.args[0] in (errno.EMFILE, errno.ENOBUFS,
                                       errno.ENFILE, errno.ENOMEM,
                                       errno.ECONNABORTED):

                        # Linux gives EMFILE when a process is not allowed
                        # to allocate any more file descriptors.  *BSD and
                        # Win32 give (WSA)ENOBUFS.  Linux can also give
                        # ENFILE if the system is out of inodes, or ENOMEM
                        # if there is insufficient memory to allocate a new
                        # dentry.  ECONNABORTED is documented as possible on
                        # both Linux and Windows, but it is not clear
                        # whether there are actually any circumstances under
                        # which it can happen (one might expect it to be
                        # possible if a client sends a FIN or RST after the
                        # server sends a SYN|ACK but before application code
                        # calls accept(2), however at least on Linux this
                        # _seems_ to be short-circuited by syncookies.

                        log.msg("Could not accept new connection (%s)" % (
                            errno.errorcode[e.args[0]],))
                        break
                    raise

                fdesc._setCloseOnExec(skt.fileno())
                skt.setblocking(0)
                self.reactor.callFromThread(self._finishConnection,
                                            skt, addr)
        except:
            # Note that in TLS mode, this will possibly catch SSL.Errors
            # raised by self.socket.accept()
            #
            # There is no "except SSL.Error:" above because SSL may be
            # None if there is no SSL support.  In any case, all the
            # "except SSL.Error:" suite would probably do is log.deferr()
            # and return, so handling it here works just as well.
            log.deferr()

    def _finishConnection(self, skt, addr):
        protocol = self.factory.buildProtocol(self._buildAddr(addr))
        if protocol is None:
            skt.close()
            return
        s = self.sessionno
        self.sessionno = s+1
        transport = self.transport(skt, protocol, addr, self, s, self.reactor)
        protocol.makeConnection(transport)

    def startReading(self):
        # this is called after self.startListening, which sets
        # self.fileno
        self.fakeFileno, self._writeFakeFileno = os.pipe()
        self.realFileno, self.fileno = self.fileno, lambda: self.fakeFileno
        self.thread = InterruptableThread(target=self._doAccept)
        self.thread.start()
        Port.startReading(self)

    def stopReading(self):
        try:
            self.thread.interrupt()
        except OSError as e:
            if not self.socketIsShared or e.errno != errno.ESRCH:
                raise
        else:
            self.thread.join()
        Port.stopReading(self)
        os.close(self._writeFakeFileno)


def listenTCP(reactor, port, factory, backlog=50, interface='',
              willBeShared=False):
    p = ThreadedAcceptPort(port, factory, backlog, interface, reactor)
    p.socketIsShared = willBeShared
    p.startListening()
    return p


def adoptStreamPort(reactor, fileDescriptor, addressFamily, factory):
        """
        Create a new L{IListeningPort} from an already-initialized socket.

        This just dispatches to a suitable port implementation (eg from
        L{IReactorTCP}, etc) based on the specified C{addressFamily}.

        @see: L{twisted.internet.interfaces.IReactorSocket.adoptStreamPort}
        """
        if addressFamily not in (socket.AF_INET, socket.AF_INET6):
            raise error.UnsupportedAddressFamily(addressFamily)

        p = ThreadedAcceptPort._fromListeningDescriptor(
            reactor, fileDescriptor, addressFamily, factory)
        p.socketIsShared = True
        p.startListening()
        return p
