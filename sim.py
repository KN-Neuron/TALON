"""3D drone simulator window. Talks to main.py over UDP; runs standalone too.

Listens for JSON commands on 127.0.0.1:9000 and flies a simple rigid body:
sticks set a target velocity, a first-order lag gets there. No aerodynamics,
no motor dynamics -- enough to see whether your control mixing does the right
thing, not enough to tune a PID against.
"""
import json
import math
import socket
import time

import pygame

PORT = 9000
W, H = 1100, 700   # starting size; the window is resizable

# --- flight model knobs (a real drone is never this obedient) ---
MAX_SPEED = 3.0     # m/s at full lr/fb stick
MAX_CLIMB = 1.5     # m/s at full throttle stick
MAX_YAW = 90.0      # deg/s at full yaw stick
RESPONSE = 3.0      # 1/s -- how fast velocity chases the stick
ALT_GAIN = 2.0      # 1/s -- altitude-hold P gain (raise it and it overshoots)
FALL_SPEED = 0.8    # m/s descent after land()
CRASH_SPEED = 6.0   # m/s after emergency(): the motors are off
TAKEOFF_ALT = 1.2   # m the auto-takeoff climbs to

# --- track: a clockwise square of gates, because the BCI can only turn right.
# Built to forgive a noisy decoder: big openings, and touching a gate just
# stops the drone where it is -- no crash, send the next command and carry on.
GATE_W, GATE_H = 7.0, 3.5   # m, the hole you fly through
POST = 0.4                  # m, frame thickness
ARM = 0.35                  # m, drone radius for collisions
# (centre x, centre y, axis the gate spans, height of the hole's bottom edge).
# Raised gates (bottom 3.0) need a climb, ground gates (top 3.5) a descent.
TRACK = [(0, 10, "x", 0.0), (0, 20, "x", 3.0),
         (10, 30, "y", 3.0), (20, 30, "y", 0.0),
         (30, 20, "x", 0.0), (30, 10, "x", 3.0),
         (20, 0, "y", 0.0), (10, 0, "y", 0.0)]


def gate_boxes(gate):
    """Frame of one gate as boxes (x0, y0, z0, x1, y1, z1)."""
    cx, cy, spans, bottom = gate
    top, hw, p = bottom + GATE_H, GATE_W / 2, POST
    parts = [(-hw - p, -hw, 0, top + p), (hw, hw + p, 0, top + p),  # posts
             (-hw, hw, top, top + p)]                               # top bar
    if bottom:
        parts.append((-hw, hw, 0, bottom))                          # wall under
    if spans == "x":
        return [(cx + u0, cy - p / 2, z0, cx + u1, cy + p / 2, z1) for u0, u1, z0, z1 in parts]
    return [(cx - p / 2, cy + u0, z0, cx + p / 2, cy + u1, z1) for u0, u1, z0, z1 in parts]


# --- camera ---
FOV = 520           # px at 1m depth
NEAR = 0.15
CAM_BACK, CAM_UP, CAM_PITCH = 6.0, 2.5, math.radians(12)
# FPV: camera on the nose, tilted down like a real FPV mount. V toggles.
FPV_UP, FPV_PITCH = 0.1, math.radians(8)

BG, GRID, FG, DIM = (12, 14, 20), (38, 44, 60), (235, 235, 240), (110, 110, 125)
ACCENT, WARN = (90, 160, 255), (255, 90, 90)
OBST, NEXT = (230, 170, 60), (80, 230, 120)


class Sim:
    """The whole flight model: state plus step(dt), so it is testable alone."""

    def __init__(self, track=TRACK):
        self.track = track
        self.boxes = [b for g in track for b in gate_boxes(g)]
        self.next_gate, self.laps, self.touching = 0, 0, False
        self.pos = [0.0, 0.0, 0.0]   # x east, y north, z up (metres)
        self.vel = [0.0, 0.0, 0.0]
        self.yaw = 0.0               # degrees, 0 = facing +y
        self.rc = (0, 0, 0, 0)
        self.flying = False
        self.hover_alt = 0.0         # metres the altitude hold is pinned to
        self.fall = FALL_SPEED
        self.note = "grounded"
        self.t0 = time.monotonic()

    def takeoff(self):
        self.flying, self.hover_alt, self.fall = True, TAKEOFF_ALT, FALL_SPEED
        self.note = "takeoff"

    def land(self):
        self.flying, self.hover_alt, self.fall = False, 0.0, FALL_SPEED
        self.note = "landing"

    def emergency(self):
        self.flying, self.hover_alt, self.fall = False, 0.0, CRASH_SPEED
        self.note = "EMERGENCY"

    def hit(self):
        """True if the drone is touching any gate frame."""
        x, y, z = self.pos
        return any(x0 - ARM < x < x1 + ARM and y0 - ARM < y < y1 + ARM and
                   z0 - 0.1 < z < z1 + 0.1 for x0, y0, z0, x1, y1, z1 in self.boxes)

    def _check_gate(self, old):
        """Advance to the next gate when this step crossed the current one's hole."""
        if not self.track:
            return
        cx, cy, spans, bottom = self.track[self.next_gate]
        along, c, across, centre = (1, cy, 0, cx) if spans == "x" else (0, cx, 1, cy)
        if ((old[along] < c) != (self.pos[along] < c)
                and abs(self.pos[across] - centre) < GATE_W / 2
                and bottom < self.pos[2] < bottom + GATE_H):
            self.next_gate = (self.next_gate + 1) % len(self.track)
            self.laps += self.next_gate == 0

    def step(self, dt):
        lr, fb, ud, yaw_rate = self.rc
        if not self.flying:
            target = [0.0, 0.0, -self.fall if self.pos[2] > 0 else 0.0]
        else:
            self.yaw = (self.yaw + yaw_rate / 100 * MAX_YAW * dt) % 360
            a = math.radians(self.yaw)
            # body -> world: fb runs along the heading, lr to the right of it
            target = [(fb * math.sin(a) + lr * math.cos(a)) / 100 * MAX_SPEED,
                      (fb * math.cos(a) - lr * math.sin(a)) / 100 * MAX_SPEED,
                      ud / 100 * MAX_CLIMB]
            # altitude hold, like ALT_HOLD/LOITER: the throttle stick sets a
            # climb rate, and letting go pins whatever height you left it at.
            if ud:
                self.hover_alt = self.pos[2]
            else:
                gap = self.hover_alt - self.pos[2]
                target[2] = max(-MAX_CLIMB, min(MAX_CLIMB, gap * ALT_GAIN))
                if abs(gap) < 0.05 and self.note == "takeoff":
                    self.note = "hover"

        old = list(self.pos)
        k = min(1.0, RESPONSE * dt)
        for i in range(3):
            self.vel[i] += (target[i] - self.vel[i]) * k
            self.pos[i] += self.vel[i] * dt
        self.touching = self.flying and self.hit()
        if self.touching:
            # stop at the frame instead of crashing: undo the horizontal move
            # first, so a drone pressed against a wall can still climb out
            self.pos[0], self.pos[1] = old[0], old[1]
            self.vel[0] = self.vel[1] = 0.0
            if self.hit():
                self.pos[2], self.vel[2] = old[2], 0.0
        if self.flying:
            self._check_gate(old)
        if self.pos[2] <= 0.0:
            self.pos[2], self.vel[2] = 0.0, 0.0
            if not self.flying:
                self.vel[0] = self.vel[1] = 0.0
                if self.note in ("landing", "takeoff"):
                    self.note = "grounded"

    def battery(self):
        # ponytail: a clock, not a model. Swap in a current draw if you need one.
        return max(0, int(100 - (time.monotonic() - self.t0) / 30))


def project(p, cam, yaw, size, pitch=CAM_PITCH):
    """World point -> (screen x, screen y, depth). depth <= NEAR means behind us."""
    dx, dy, dz = p[0] - cam[0], p[1] - cam[1], p[2] - cam[2]
    s, c = math.sin(yaw), math.cos(yaw)
    x, z = dx * c - dy * s, dx * s + dy * c
    cp, sp = math.cos(pitch), math.sin(pitch)
    y2, z2 = dz * cp + z * sp, z * cp - dz * sp
    if z2 <= NEAR:
        return 0.0, 0.0, z2
    # FOV is fixed in pixels, so a bigger window shows more world, not a
    # zoomed-in crop of the same view.
    return size[0] / 2 + FOV * x / z2, size[1] / 2 - FOV * y2 / z2, z2


def draw_seg(surf, a, b, cam, yaw, color, width=1, pitch=CAM_PITCH):
    """Line between two world points, near-clipped so it never wraps around."""
    size = surf.get_size()
    pa, pb = project(a, cam, yaw, size, pitch), project(b, cam, yaw, size, pitch)
    if pa[2] <= NEAR and pb[2] <= NEAR:
        return
    if pa[2] <= NEAR or pb[2] <= NEAR:
        far, near = (b, a) if pa[2] <= NEAR else (a, b)
        zf, zn = pa[2] if far is a else pb[2], pb[2] if far is a else pa[2]
        t = (zf - NEAR) / (zf - zn) * 0.999
        mid = [far[i] + (near[i] - far[i]) * t for i in range(3)]
        pa, pb = project(far, cam, yaw, size, pitch), project(mid, cam, yaw, size, pitch)
    pygame.draw.line(surf, color, pa[:2], pb[:2], width)


def rotors(sim):
    """Four rotor centres in world space, front pair first."""
    a, arm = math.radians(sim.yaw), 0.35
    out = []
    for bx, by in ((-1, 1), (1, 1), (1, -1), (-1, -1)):
        out.append([sim.pos[0] + bx * arm * math.cos(a) + by * arm * math.sin(a),
                    sim.pos[1] - bx * arm * math.sin(a) + by * arm * math.cos(a),
                    sim.pos[2]])
    return out


def draw(surf, sim, fonts, cam, cam_yaw, fpv=False):
    big, small = fonts
    w, h = surf.get_size()
    surf.fill(BG)
    pitch = FPV_PITCH if fpv else CAM_PITCH

    def seg(a, b, color, width=1):
        draw_seg(surf, a, b, cam, cam_yaw, color, width, pitch)

    # ground grid, recentred on the drone each frame so it never runs out
    gx, gy = round(sim.pos[0]), round(sim.pos[1])
    for i in range(-20, 21):
        seg([gx + i, gy - 20, 0], [gx + i, gy + 20, 0],
            (70, 80, 105) if (gx + i) % 5 == 0 else GRID)
        seg([gx - 20, gy + i, 0], [gx + 20, gy + i, 0],
            (70, 80, 105) if (gy + i) % 5 == 0 else GRID)

    for gi, gate in enumerate(sim.track):
        color, width = (NEXT, 3) if gi == sim.next_gate else (OBST, 1)
        for x0, y0, z0, x1, y1, z1 in gate_boxes(gate):
            base = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
            for i in range(4):
                (ax, ay), (bx, by) = base[i], base[(i + 1) % 4]
                seg([ax, ay, z0], [bx, by, z0], color, width)
                seg([ax, ay, z1], [bx, by, z1], color, width)
                seg([ax, ay, z0], [ax, ay, z1], color, width)

    arms = rotors(sim)
    shadow = [[r[0], r[1], 0.0] for r in arms]
    for i in range(4):
        seg(shadow[i], shadow[(i + 1) % 4], (28, 32, 44), 2)

    if fpv:
        # the airframe is behind the lens, so draw a crosshair instead of it
        cx, cy = w // 2, h // 2
        pygame.draw.line(surf, ACCENT, (cx - 18, cy), (cx + 18, cy), 2)
        pygame.draw.line(surf, ACCENT, (cx, cy - 18), (cx, cy + 18), 2)
    else:
        if sim.pos[2] > 0.05:
            seg([sim.pos[0], sim.pos[1], 0.0], list(sim.pos), (40, 45, 60))
        for r in arms:
            seg(r, list(sim.pos), (170, 175, 195), 3)
        for i, r in enumerate(arms):
            sx, sy, z = project(r, cam, cam_yaw, (w, h), pitch)
            if z <= NEAR:
                continue
            # front pair coloured, so which way it faces is obvious at a glance
            pygame.draw.circle(surf, ACCENT if i < 2 else (200, 120, 90),
                               (int(sx), int(sy)), max(2, int(FOV * 0.22 / z)), 2)

    state = ("BUMP" if sim.touching else "FLYING") if sim.flying else sim.note.upper()
    color = (WARN if sim.touching else ACCENT) if sim.flying else \
        (WARN if sim.note == "EMERGENCY" else DIM)
    surf.blit(big.render(f"SIM {'FPV' if fpv else 'CHASE'}  " + state, True, color),
              (20, 16))
    for i, line in enumerate((f"alt   {sim.pos[2]:5.2f} m",
                              f"speed {math.hypot(sim.vel[0], sim.vel[1]):5.2f} m/s",
                              f"hdg   {sim.yaw:5.1f} deg",
                              f"pos   {sim.pos[0]:+.1f}, {sim.pos[1]:+.1f}",
                              f"rc    {sim.rc}",
                              f"gate  {sim.next_gate + 1}/{len(sim.track)}   lap {sim.laps}")):
        surf.blit(small.render(line, True, FG), (20, 60 + i * 22))
    surf.blit(small.render("standalone: arrows + WASD fly, T takeoff, L land, "
                           "SPACE emergency, V fpv/chase", True, DIM), (20, h - 28))


def main():
    pygame.init()
    screen = pygame.display.set_mode((W, H), pygame.RESIZABLE)
    pygame.display.set_caption("drone sim")
    fonts = (pygame.font.SysFont(None, 40), pygame.font.SysFont(None, 24))
    clock = pygame.time.Clock()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", PORT))
    sock.setblocking(False)

    sim = Sim()
    cam_yaw = math.radians(sim.yaw)
    fpv = False
    running = True
    while running:
        while True:  # drain the socket, else we fly on stale sticks
            try:
                data, peer = sock.recvfrom(512)
            except (BlockingIOError, OSError):
                break
            msg = json.loads(data)
            cmd = msg.get("c")
            if cmd == "rc":
                sim.rc = tuple(msg["v"])
            elif cmd in ("takeoff", "land", "emergency"):
                getattr(sim, cmd)()
            elif cmd == "state":  # main.py asks: T/L here must not desync it
                sock.sendto(json.dumps({"flying": sim.flying}).encode(), peer)
            elif cmd == "bat":
                sock.sendto(json.dumps({"bat": sim.battery()}).encode(), peer)
            elif cmd == "photo":
                pygame.image.save(screen, msg["path"])
                sock.sendto(json.dumps({"photo": msg["path"]}).encode(), peer)

        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.VIDEORESIZE:
                screen = pygame.display.set_mode(e.size, pygame.RESIZABLE)
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_t:
                    sim.takeoff()
                elif e.key == pygame.K_l:
                    sim.land()
                elif e.key == pygame.K_SPACE:
                    sim.emergency()
                elif e.key == pygame.K_v:
                    fpv = not fpv
                elif e.key == pygame.K_ESCAPE:
                    running = False

        # standalone flying, so the sim window is useful on its own. main.py's
        # RC packets arrive far faster and simply overwrite this.
        k = pygame.key.get_pressed()
        manual = (100 * (k[pygame.K_RIGHT] - k[pygame.K_LEFT]),
                  100 * (k[pygame.K_UP] - k[pygame.K_DOWN]),
                  100 * (k[pygame.K_w] - k[pygame.K_s]),
                  100 * (k[pygame.K_d] - k[pygame.K_a]))
        if any(manual):
            sim.rc = manual

        dt = clock.tick(60) / 1000.0
        sim.step(min(dt, 0.1))  # a dragged window must not teleport the drone

        a = math.radians(sim.yaw)
        if fpv:  # locked to the airframe: no lag, that is the point of FPV
            cam, cam_yaw = [sim.pos[0], sim.pos[1], sim.pos[2] + FPV_UP], a
        else:
            cam = [sim.pos[0] - CAM_BACK * math.sin(a),
                   sim.pos[1] - CAM_BACK * math.cos(a),
                   sim.pos[2] + CAM_UP]
            # shortest way round, else the camera unwinds the long way through 360
            d = (a - cam_yaw + math.pi) % (2 * math.pi) - math.pi
            cam_yaw += d * min(1.0, 4 * dt)
        draw(screen, sim, fonts, cam, cam_yaw, fpv)
        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
