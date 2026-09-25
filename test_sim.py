"""python test_sim.py -- fails loudly if the flight model or camera breaks."""
import math

from sim import CAM_PITCH, H, NEAR, Sim, TAKEOFF_ALT, W, project

DT = 1 / 60


def fly(sim, seconds, rc=(0, 0, 0, 0)):
    sim.rc = rc
    for _ in range(int(seconds / DT)):
        sim.step(DT)
    return sim


# grounded: sticks do nothing, it does not sink through the floor
s = fly(Sim(), 2, rc=(0, 100, 100, 0))
assert s.pos == [0.0, 0.0, 0.0], s.pos

# takeoff climbs to TAKEOFF_ALT and then holds it, hands off
s = Sim()
s.takeoff()
fly(s, 8)
assert abs(s.pos[2] - TAKEOFF_ALT) < 0.05, s.pos[2]
assert s.note == "hover"
fly(s, 5)
assert abs(s.pos[2] - TAKEOFF_ALT) < 0.05, "did not hold altitude"

# throttle up, then let go: it pins the new height rather than sinking back
fly(s, 3, rc=(0, 0, 100, 0))
climbed = s.pos[2]
assert climbed > TAKEOFF_ALT + 1, climbed
fly(s, 6)
assert abs(s.pos[2] - climbed) < 0.2, (climbed, s.pos[2])

# forward stick flies along the heading, not along the world axes
s = Sim()
s.takeoff()
fly(s, 4, rc=(0, 100, 0, 0))
assert s.pos[1] > 3 and abs(s.pos[0]) < 0.01, s.pos
s.yaw = 90.0
before = s.pos[0]
fly(s, 4, rc=(0, 100, 0, 0))
assert s.pos[0] - before > 3, s.pos

# yaw stick turns, and wraps instead of running off to 400 degrees
s = Sim()
s.takeoff()
fly(s, 5, rc=(0, 0, 0, 100))
assert 0 <= s.yaw < 360 and abs(s.yaw - 90) < 5, s.yaw

# land settles on the ground and stays there; emergency gets there faster
s = Sim()
s.takeoff()
fly(s, 8)
crash = Sim()
crash.pos, crash.flying = list(s.pos), True
s.land()
crash.emergency()
fly(s, 0.5)
fly(crash, 0.5)
assert crash.pos[2] < s.pos[2] < TAKEOFF_ALT, (crash.pos[2], s.pos[2])
fly(s, 10)
assert s.pos == [0.0, 0.0, 0.0] and s.vel == [0.0, 0.0, 0.0], (s.pos, s.vel)

# camera: 10m straight ahead of a level-ish camera at the origin projects to
# the middle of the screen, a point behind it reports depth behind the near plane
size = (W, H)
x, y, z = project([0, 10, 0], [0, 0, 0], 0.0, size)
assert abs(z - 10 * math.cos(CAM_PITCH)) < 1e-9, z
assert abs(x - W / 2) < 1e-6, x
assert project([0, -10, 0], [0, 0, 0], 0.0, size)[2] <= NEAR
# turning the camera right swings a point ahead of it to the left of the screen
assert project([0, 10, 0], [0, 0, 0], math.radians(20), size)[0] < x

# resizing recentres rather than zooming: same point, same depth, new centre
big = (1920, 1080)
xb, yb, zb = project([0, 10, 0], [0, 0, 0], 0.0, big)
assert abs(zb - z) < 1e-9 and abs(xb - big[0] / 2) < 1e-6, (zb, xb)
assert abs((xb - big[0] / 2) - (x - W / 2)) < 1e-6, "offset from centre moved"

# track: fly through a ground gate, get stopped (not crashed) by the wall
# under a raised one, climb over the wall and through the hole to finish a lap
track = [(0, 5, "x", 0.0), (0, 15, "x", 3.0)]
s = Sim(track=track)
s.takeoff()
fly(s, 8, rc=(0, 100, 0, 0))
assert s.next_gate == 1, s.next_gate
assert s.flying and s.touching and 13 < s.pos[1] < 15, (s.pos, s.note)
fly(s, 2.5, rc=(0, 0, 100, 0))
assert s.pos[2] > 4.0, s.pos  # a wall at your nose must not pin you in place
fly(s, 3, rc=(0, 100, 0, 0))
assert s.pos[1] > 15 and s.laps == 1 and s.next_gate == 0, (s.pos, s.laps)
# over the top of a gate is not through it
s = Sim(track=[(0, 5, "x", 0.0)])
s.takeoff()
fly(s, 4, rc=(0, 0, 100, 0))
fly(s, 6, rc=(0, 100, 0, 0))
assert s.pos[1] > 5 and s.laps == 0, (s.pos, s.laps)
assert Sim().hit() is False, "takeoff pad must be clear"

# FPV pitch: tilted down, a point level with the lens sits above centre; both
# views render a frame without blowing up (drone on the ground and in the air)
from sim import FPV_PITCH, draw
import pygame
assert project([0, 10, 0], [0, 0, 0], 0.0, size, FPV_PITCH)[1] < H / 2
pygame.init()
surf = pygame.Surface(size)
fonts = (pygame.font.SysFont(None, 40), pygame.font.SysFont(None, 24))
for alt in (0.0, 2.0):
    s = Sim()
    s.pos[2] = alt
    draw(surf, s, fonts, [0, 0, alt + 0.1], 0.0, fpv=True)
    draw(surf, s, fonts, [0, -6, alt + 2.5], 0.0, fpv=False)
pygame.quit()

print("sim ok")
