"""Device calls stay off the UI thread and emergency follows a blocked call."""
from threading import Event, get_ident
from transport import Transport

ui_thread = get_ident()
started, release = Event(), Event()
calls = []


class Device:
    name = 'TEST'

    def battery(self):
        assert get_ident() != ui_thread
        started.set()
        assert release.wait(2)
        return 75

    def emergency(self):
        calls.append('emergency')

    def close(self):
        calls.append('close')


t = Transport(Device)
t.pending.result(timeout=2)
t.poll()
assert t.connected
assert t.command('battery')
assert started.wait(2)
assert t.command('emergency'), 'emergency must remain available during telemetry'
assert not t.command('takeoff'), 'cannot queue takeoff behind emergency'
release.set()
t.pending.result(timeout=2)
t.poll()
assert not t.flying
t.close()
assert calls == ['emergency', 'close']


def fail():
    raise RuntimeError('connection failed')


t = Transport(fail)
try:
    t.pending.result(timeout=2)
except RuntimeError:
    pass
t.poll()
assert not t.connected and t.error == 'connection failed'
t.close()
print('transport ok: nonblocking calls, emergency ordering, connection failure, cleanup')
