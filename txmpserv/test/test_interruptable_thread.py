from twisted.trial import unittest
import time
import errno
import signal
import txmpserv.interruptable_thread as T


class TestInterruptableThread(unittest.TestCase):
    signals = (T.InterruptableThread.interruptSignal,
               signal.SIGUSR2)

    def setUp(self):
        self.originalHandlers = {}
        for sig in self.signals:
            self.originalHandlers[sig] = signal.signal(sig, T.noop)

    def tearDown(self):
        for sig, originalHandler in self.originalHandlers.items():
            signal.signal(sig, originalHandler)

    def _assertInterrupted(self, thread):
        self.assertFalse(thread.daemon)
        with self.assertRaises(T.ThreadNotStarted):
            thread.interrupt()

        thread.start()
        self.assertTrue(thread.isAlive())

        thread.interrupt()
        thread.join()

        self.assertFalse(thread.isAlive())
        with self.assertRaises(OSError) as exc_cm:
            thread.interrupt()

        exc = exc_cm.exception
        self.assertEqual(exc.errno, errno.ESRCH)

    def test_interrupt(self):
        thread = T.InterruptableThread(target=lambda: time.sleep(10 << 20))
        self._assertInterrupted(thread)

    def test_interrupt_withUserSignal(self):
        thread = T.InterruptableThread(target=lambda: time.sleep(10 << 20),
                                       interruptSignal=signal.SIGUSR2)
        self._assertInterrupted(thread)
