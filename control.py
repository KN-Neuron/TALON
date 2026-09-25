"""Control mixing: PS4 pad always wins, BCI fills the gaps."""
import time
from collections import namedtuple

# Channels are drone RC values, -100..100 each.
Channels = namedtuple("Channels", "lr fb ud yaw")
ZERO = Channels(0, 0, 0, 0)

# --- calibration knobs (sticks drift, drones differ) ---
DEADZONE = 0.12     # raw stick units to ignore around centre
MAX_SPEED = 60      # pad full deflection -> this many RC units
BCI_SPEED = 40      # how hard a BCI command pushes
BCI_PULSE = 1.0     # seconds one BCI command stays active
PAD_HOLD = 1.5      # seconds the pad keeps priority after you let go


def scale(v, deadzone=DEADZONE, max_speed=MAX_SPEED):
    """Raw axis float (-1..1) -> RC int, deadzone removed and rescaled."""
    if abs(v) < deadzone:
        return 0
    v = (abs(v) - deadzone) / (1 - deadzone) * (1 if v > 0 else -1)
    return int(round(max(-1.0, min(1.0, v)) * max_speed))


def mix(pad, bci, pad_active_at, now, hold=PAD_HOLD):
    """Return (channels, source). Pad wins while moving and for `hold` after."""
    if pad != ZERO or now - pad_active_at < hold:
        return pad, "PS4"
    if bci != ZERO:
        return bci, "BCI"
    return ZERO, "IDLE"


class BCI:
    """Call these four methods from your BCI code. Each fires a timed pulse.

    Thread-safe by accident: the only shared state is one tuple, and rebinding
    a tuple is atomic under the GIL.
    """

    def __init__(self, speed=BCI_SPEED, pulse=BCI_PULSE):
        self.speed = speed
        self.pulse = pulse
        self.armed = False          # thoughts do not fly the drone until you say so
        self._active = (ZERO, 0.0)  # (channels, expiry)
        self.last = ""              # for the UI

    def up(self):           self._fire(Channels(0, 0,  self.speed, 0), "up")
    def down(self):         self._fire(Channels(0, 0, -self.speed, 0), "down")
    def forward(self):      self._fire(Channels(0,  self.speed, 0, 0), "forward")
    def rotate_right(self): self._fire(Channels(0, 0, 0,  self.speed), "rotate_right")

    def stop(self):
        self._active = (ZERO, 0.0)
        self.last = "stop"

    def _fire(self, ch, name):
        if not self.armed:
            self.last = f"{name} (disarmed)"
            return
        self._active = (ch, time.monotonic() + self.pulse)
        self.last = name

    def channels(self, now=None):
        ch, expiry = self._active
        return ch if (now or time.monotonic()) < expiry else ZERO
