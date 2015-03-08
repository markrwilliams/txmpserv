import os
import cffi
import threading
import signal


ffi = cffi.FFI()

ffi.cdef('''
struct _cffi_pthread {
    ...;
};

typedef struct _cffi_pthread _cffi_pthread_t;

void _cffi_pthread_self(_cffi_pthread_t* thread);

int _cffi_pthread_kill(_cffi_pthread_t* thread, int sig);
''')

lib = ffi.verify('''
#include <pthread.h>

struct _cffi_pthread {
    pthread_t id;
};

typedef struct _cffi_pthread _cffi_pthread_t;

void _cffi_pthread_self(_cffi_pthread_t* thread)
{
    thread->id = pthread_self();
}


int _cffi_pthread_kill(_cffi_pthread_t* thread, int sig)
{
    return pthread_kill(thread->id, sig);
}

''',
                 ext_package='txta',
                 libraries=['pthread'])


def _pthread_self():
    thread = ffi.new('_cffi_pthread_t*')
    lib._cffi_pthread_self(thread)
    return thread


def _pthread_kill(thread, sig):
    ret = lib._cffi_pthread_kill(thread, sig)
    if ret:
        raise OSError(ret, os.strerror(ret))


def noop(*args):
    return None


class ThreadNotStarted(Exception):
    pass


class InterruptableThread(threading.Thread):
    interruptSignal = signal.SIGUSR1

    def __init__(self, *args, **kwargs):
        interruptSignal = kwargs.pop('interruptSignal', None)
        if interruptSignal:
            self.interruptSignal = interruptSignal
        self._pthread_identifier = None
        super(InterruptableThread, self).__init__(*args, **kwargs)

    def _Thread__bootstrap_inner(self):
        self._pthread_identifier = _pthread_self()
        super(InterruptableThread, self)._Thread__bootstrap_inner()

    def interrupt(self):
        if self._pthread_identifier is None:
            raise ThreadNotStarted
        _pthread_kill(self._pthread_identifier, self.interruptSignal)
