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


LOCK = RLock()


class ThreadedAcceptPort(Port):
    socketIsShared = False

    def __init__(self, *args, **kwargs):
        Port.__init__(self, *args, **kwargs)
        self.fakeReadable, w = os.pipe()
        os.close(w)
        self.fileno = lambda: self.fakeReadable
        self.acceptThread = None

    def createInternetSocket(self):
        s = socket.socket(self.addressFamily, self.socketType)
        fdesc._setCloseOnExec(s.fileno())
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s

    def _doAccept(self):
        """Called when my socket is ready for reading.

        This accepts a connection and calls self.protocol() to handle the
        wire-level protocol.
        """
        try:
            numAccepts = self.numberAccepts
            for i in range(numAccepts):
                # we need this so we can deal with a factory's buildProtocol
                # calling our loseConnection
                if self.disconnecting:
                    return
                try:
                    skt, addr = self.socket.accept()
                except socket.error as e:
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
                self.reactor.callFromThread(self._finishConnection,
                                            skt, addr)
            else:
                with LOCK:
                    self.numberAccepts = self.numberAccepts+20
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
        self.thread = InterruptableThread(target=self._doAccept)
        self.thread.start()
        Port.startReading(self)

    def doRead(self):
        # there's a race between the reactor calling this and the
        # thread waking up.  this may waste some resources, so
        # consider a different approach
        return

    def stopReading(self):
        try:
            self.thread.interrupt()
        except OSError as e:
            if not self.socketIsShared or e.errno != errno.ESRCH:
                raise
        else:
            self.thread.join()


def listenTCP(reactor, port, factory, backlog=50, interface='',
              willBeshared=False):
    p = ThreadedAcceptPort(port, factory, backlog, interface, reactor)
    p.socketIsShared = willBeshared
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
