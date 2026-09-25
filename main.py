"""PS4 pad + BCI -> drone, with a pygame UI. Run: python main.py [--mock|--sim]"""
import argparse
import json
import os
import socket
import subprocess
import sys
import time

import pygame

from control import BCI, Channels, ZERO, mix, scale
from drone import make_drone

# --- pad mapping. Indices differ per driver: the console prints the index of
# every button you press, so fix these once for your DS4 and forget it. ---
AX_LR, AX_FB, AX_YAW, AX_UD = 0, 1, 2, 3   # left stick X/Y, right stick X/Y
BTN_TAKEOFF, BTN_LAND, BTN_EMERGENCY = 3, 0, 1  # triangle, cross, circle
BTN_PHOTO, BTN_BCI = 2, 4                       # square, L1

RATE = 20  # Hz. Tello wants RC packets at >=10Hz or it drifts to a stop.
BCI_PORT = 9001  # ssvep.py, or your real decoder, posts command names here
BCI_PULSES = ("up", "down", "forward", "rotate_right", "stop")  # -> BCI methods


def bci_inbox(port=BCI_PORT):
    """UDP socket a decoder writes {"cmd": "up"} to. Non-blocking, fire-and-forget."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", port))
    s.setblocking(False)
    return s


def drain_bci(sock, bci):
    """Apply every command waiting on the socket. Returns the last one applied."""
    last = ""
    while True:
        try:
            data, _ = sock.recvfrom(256)
        except (BlockingIOError, OSError):
            return last
        try:
            cmd = json.loads(data).get("cmd")
        except ValueError:
            continue
        if cmd in BCI_PULSES:  # whitelist: this socket is reachable, not trusted
            getattr(bci, cmd)()
            last = cmd

BG, FG, DIM = (18, 18, 22), (235, 235, 240), (110, 110, 125)
SRC_COLOR = {"PS4": (80, 220, 120), "BCI": (90, 160, 255), "IDLE": (110, 110, 125)}


def read_pad(js):
    if js is None:
        return ZERO
    a = js.get_axis
    return Channels(scale(a(AX_LR)), -scale(a(AX_FB)), -scale(a(AX_UD)), scale(a(AX_YAW)))


def snap(drone):
    os.makedirs("photos", exist_ok=True)
    path = os.path.join("photos", time.strftime("%Y%m%d-%H%M%S.jpg"))
    return drone.photo(path) or "no camera"


def draw(screen, fonts, drone, bci, ch, source, js, battery, note):
    big, mid, small = fonts
    screen.fill(BG)

    def text(s, font, x, y, color=FG):
        screen.blit(font.render(s, True, color), (x, y))

    text("DRONE CONTROL", mid, 20, 16)
    text(f"{drone.name}   bat {battery}%   {'FLYING' if drone.flying else 'grounded'}",
         small, 20, 48, DIM)

    pad_state = "PS4 connected" if js else "PS4 DISCONNECTED"
    text(pad_state, small, 20, 70, FG if js else (255, 90, 90))

    text(source, big, 20, 100, SRC_COLOR[source])
    text("BCI ARMED" if bci.armed else "BCI disarmed", small, 200, 106,
         SRC_COLOR["BCI"] if bci.armed else DIM)
    text(f"last: {bci.last or '-'}", small, 200, 126, DIM)
    text(note, small, 330, 70, DIM)

    for i, (label, val) in enumerate(zip(("roll", "pitch", "throttle", "yaw"), ch)):
        y = 175 + i * 46
        text(label, small, 20, y + 6, DIM)
        x0, w = 110, 380
        pygame.draw.rect(screen, (40, 40, 50), (x0, y, w, 22), border_radius=4)
        pygame.draw.line(screen, DIM, (x0 + w // 2, y), (x0 + w // 2, y + 22))
        px = int(val / 100 * (w // 2))
        if px:
            pygame.draw.rect(screen, SRC_COLOR[source],
                             (x0 + w // 2 + min(px, 0), y + 3, abs(px), 16), border_radius=3)
        text(f"{val:+4d}", small, x0 + w + 12, y + 6)

    text("triangle/T takeoff   cross/L land   circle/SPACE EMERGENCY", small, 20, 356, DIM)
    text("square/P photo   L1/B arm BCI   1-4 fake BCI commands", small, 20, 374, DIM)
    pygame.display.flip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true", help="no drone, just the UI")
    ap.add_argument("--sim", action="store_true",
                    help="fly sim.py and open the SSVEP stimulus window")
    ap.add_argument("--connect", help="MAVLink target, e.g. COM3 or udpin:0.0.0.0:14550")
    args = ap.parse_args()

    kids = [subprocess.Popen([sys.executable, f]) for f in ("sim.py", "ssvep.py")] \
        if args.sim else []
    if kids:
        time.sleep(1.0)  # let sim.py bind 9000 before we start shouting at it

    pygame.init()
    # SCALED|RESIZABLE: the HUD has fixed pixel coordinates, so let SDL
    # stretch it to whatever size the window is dragged to.
    screen = pygame.display.set_mode((640, 400), pygame.SCALED | pygame.RESIZABLE)
    pygame.display.set_caption("drone control")
    fonts = (pygame.font.SysFont(None, 56),
             pygame.font.SysFont(None, 30),
             pygame.font.SysFont(None, 22))
    clock = pygame.time.Clock()

    drone = make_drone(args.mock, args.connect, args.sim)
    bci = BCI()
    inbox = bci_inbox()
    js = pygame.joystick.Joystick(0) if pygame.joystick.get_count() else None

    def toggle_bci():
        bci.armed = not bci.armed
        if not bci.armed:
            bci.stop()

    pad_active_at = -999.0
    battery, next_battery = 0, 0.0
    note = ""
    running = True
    while running:
        now = time.monotonic()
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.JOYDEVICEADDED:
                js = pygame.joystick.Joystick(e.device_index)
            elif e.type == pygame.JOYDEVICEREMOVED:
                js = None
                # the pad IS the emergency stop: without it, get on the ground
                bci.armed = False
                bci.stop()
                if drone.flying:
                    drone.land()
                note = "pad lost -> landed"
            elif e.type == pygame.JOYBUTTONDOWN:
                print(f"[pad] button {e.button}")
                if e.button == BTN_TAKEOFF: drone.takeoff()
                elif e.button == BTN_LAND: drone.land()
                elif e.button == BTN_EMERGENCY: drone.emergency()
                elif e.button == BTN_PHOTO: note = snap(drone)
                elif e.button == BTN_BCI: toggle_bci()
                pad_active_at = now
            elif e.type == pygame.KEYDOWN:
                # keyboard stands in for hardware while you develop
                {pygame.K_t: drone.takeoff, pygame.K_l: drone.land,
                 pygame.K_SPACE: drone.emergency, pygame.K_b: toggle_bci,
                 pygame.K_1: bci.up, pygame.K_2: bci.down,
                 pygame.K_3: bci.forward, pygame.K_4: bci.rotate_right,
                 }.get(e.key, lambda: None)()
                if e.key == pygame.K_p:
                    note = snap(drone)
                if e.key == pygame.K_ESCAPE:
                    running = False

        drain_bci(inbox, bci)

        pad = read_pad(js)
        if pad != ZERO:
            pad_active_at = now
        ch, source = mix(pad, bci.channels(now), pad_active_at, now)
        if source == "PS4" and pad == ZERO:
            bci.stop()  # pad is holding priority: don't let a stale pulse resume

        if drone.flying:
            drone.send_rc(ch)

        if now >= next_battery:
            try:
                battery = drone.battery()
            except Exception:
                pass
            next_battery = now + 3

        draw(screen, fonts, drone, bci, ch, source, js, battery, note)
        clock.tick(RATE)

    drone.close()
    inbox.close()
    for k in kids:
        k.terminate()
    pygame.quit()


if __name__ == "__main__":
    main()
