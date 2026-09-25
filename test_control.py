"""python test_control.py -- fails loudly if the priority logic breaks."""
from control import BCI, Channels, ZERO, mix, scale

# deadzone eats drift, full deflection hits max, and it is monotonic
assert scale(0.05) == 0
assert scale(1.0) == 60 and scale(-1.0) == -60
assert 0 < scale(0.5) < 60

pad = Channels(10, 0, 0, 0)
bci_ch = Channels(0, 0, 40, 0)

# pad moving -> pad wins outright
assert mix(pad, bci_ch, pad_active_at=0, now=100) == (pad, "PS4")
# pad just released -> still wins, and it wins with ZERO (drone holds still)
assert mix(ZERO, bci_ch, pad_active_at=100, now=100.5) == (ZERO, "PS4")
# hold expired -> BCI takes over
assert mix(ZERO, bci_ch, pad_active_at=100, now=102) == (bci_ch, "BCI")
# nobody asking for anything
assert mix(ZERO, ZERO, pad_active_at=0, now=100) == (ZERO, "IDLE")

b = BCI(speed=40, pulse=1.0)
assert b.channels(now=0) == ZERO

# disarmed by default: BCI calls are swallowed, drone does not move
b.up()
assert b.channels() == ZERO, "disarmed BCI must not command anything"

b.armed = True
b.up()
t = b._active[1]
assert b.channels(now=t - 0.1) == Channels(0, 0, 40, 0)
assert b.channels(now=t + 0.1) == ZERO, "pulse must expire"
b.forward(); assert b.channels(now=t)[1] == 40 and b.last == "forward"
b.rotate_right(); assert b.channels(now=t)[3] == 40
b.down(); assert b.channels(now=t)[2] == -40
b.stop(); assert b.channels(now=t) == ZERO

print("ok")
