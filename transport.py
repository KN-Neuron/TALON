"""One transport owner keeps blocking device calls outside the UI thread."""
from concurrent.futures import ThreadPoolExecutor
import time


class Transport:
    def __init__(self, factory):
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.drone = None
        self.pending = self.pool.submit(self._connect, factory)
        self.action = 'connect'
        self.flying = False
        self.battery = None
        self.name = 'Łączenie'
        self.connected = False
        self.error = ''
        self.next_battery = 0
        self.last_rc = 0

    def _connect(self, factory):
        self.drone = factory()
        return self.drone.name

    @property
    def busy(self):
        return self.pending is not None

    def poll(self):
        if self.pending is None or not self.pending.done():
            return
        try:
            result = self.pending.result()
            self.error = ''
            if self.action == 'connect':
                self.name, self.connected = result, True
            elif self.action == 'battery':
                self.battery = result
            elif self.action == 'photo':
                if not result:
                    self.error = 'Zdjęcie niedostępne — brak obrazu z kamery.'
            elif self.action == 'takeoff':
                self.flying = True
            elif self.action in ('land', 'emergency'):
                self.flying = False
        except Exception as exc:
            self.error = str(exc)
            if self.action == 'connect':
                self.name = 'Błąd połączenia'
        self.pending = None

    def command(self, action, *args):
        if not self.connected:
            return False
        if self.busy:
            if self.action == action or self.action == 'emergency':
                return False
            # Device calls remain serial. Flight commands jump ahead of the
            # next telemetry/RC update; emergency also follows a running takeoff.
            if action not in ('land', 'emergency') and (
                    action != 'takeoff' or self.action not in ('battery', 'send_rc')):
                return False
        self.action = action
        self.pending = self.pool.submit(getattr(self.drone, action), *args)
        return True

    def tick(self, channels, now):
        self.poll()
        if self.busy or not self.connected:
            return
        if now >= self.next_battery:
            self.next_battery = now + 3
            self.command('battery')
        elif self.flying and now - self.last_rc >= 0.05:
            self.last_rc = now
            self.command('send_rc', channels)

    def close(self):
        # Queue cleanup after an outstanding device operation, even on error.
        def cleanup():
            if self.drone is not None:
                self.drone.close()
        future = self.pool.submit(cleanup)
        self.pool.shutdown(wait=True)
        future.result()
