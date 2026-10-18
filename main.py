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
    for _ in range(128):
        try:
            data, _ = sock.recvfrom(256)
        except (BlockingIOError, OSError):
            return last
        try:
            message = json.loads(data)
            if not isinstance(message, dict):
                continue
            cmd = message.get("cmd")
        except (ValueError, UnicodeError):
            continue
        if cmd in BCI_PULSES:  # whitelist: this socket is reachable, not trusted
            getattr(bci, cmd)()
            last = cmd
    return last

def read_pad(js):
    if js is None:
        return ZERO
    a = js.get_axis
    return Channels(scale(a(AX_LR)), -scale(a(AX_FB)), -scale(a(AX_UD)), scale(a(AX_YAW)))


def snap(drone):
    os.makedirs("photos", exist_ok=True)
    path = os.path.join("photos", time.strftime("%Y%m%d-%H%M%S.jpg"))
    return drone.photo(path) or "no camera"


def main():
    from pathlib import Path
    from ui import Dashboard, buttons
    from transport import Transport

    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument('--mock', action='store_true', help='panel demonstracyjny')
    mode.add_argument('--sim', action='store_true', help='symulator w panelu')
    mode.add_argument('--connect', help='adres MAVLink')
    ap.add_argument('--wireframe', action='store_true', help='lekki widok liniowy zamiast grafiki 3D')
    ap.add_argument('--no-shadows', action='store_true', help='wyłącz cienie w trybie 3D')
    ap.add_argument('--quality', choices=('low', 'balanced', 'high'), default='balanced', help='jakość obrazu 3D')
    args = ap.parse_args()
    pygame.init()
    screen = pygame.display.set_mode((1180, 760), pygame.RESIZABLE)
    pygame.display.set_caption('TALON · Sterowanie')
    ui, clock = Dashboard(), pygame.time.Clock()
    sim = None
    if args.sim:
        from sim import Sim
        sim = Sim()
    transport = None if sim else Transport(lambda: make_drone(args.mock, args.connect))
    inbox, stimuli = None, None
    bci = BCI()
    js = pygame.joystick.Joystick(0) if pygame.joystick.get_count() else None
    diagnostics, fpv, running = False, False, True
    pad_active_at, manual_until = -999.0, -999.0
    channels, source, note = ZERO, 'Oczekiwanie', 'Strzałki: ruch · W/S: wysokość · A/D: obrót · F1: pomoc'
    controls = []

    def flight_status():
        if sim:
            if sim.note == 'EMERGENCY':
                return 'Silniki wyłączone'
            if not sim.flying:
                return 'Lądowanie' if sim.pos[2] > 0.05 else 'Na ziemi'
            return 'Startowanie' if sim.note == 'takeoff' else ('Kontakt z bramką' if sim.touching else 'W locie')
        if not transport.connected:
            return 'Błąd połączenia' if transport.error else 'Łączenie…'
        if transport.busy and transport.action in ('takeoff', 'land', 'emergency'):
            return {'takeoff': 'Startowanie…', 'land': 'Lądowanie…', 'emergency': 'Wyłączanie silników…'}[transport.action]
        return 'Lot zadany' if transport.flying else 'Lot niezadany'

    def action(name):
        nonlocal diagnostics, fpv, stimuli, note, channels, manual_until
        if name == 'bci':
            bci.armed = not bci.armed
            bci.stop()
            note = 'BCI gotowe' if bci.armed else 'BCI wyłączone'
        elif name == 'diagnostics':
            diagnostics = not diagnostics
        elif name == 'camera':
            fpv = not fpv
        elif name == 'stimuli':
            if stimuli is None or stimuli.poll() is not None:
                stimuli = subprocess.Popen([sys.executable, str(Path(__file__).with_name('ssvep.py'))])
            note = 'Bodźce SSVEP otwarte. Włącz BCI, aby przyjmować polecenia.'
        elif name in ('takeoff', 'land', 'emergency'):
            if name == 'takeoff' and ((sim and (sim.flying or sim.pos[2] > 0.05)) or
                    (transport and (transport.flying or (transport.busy and transport.action not in ('battery', 'send_rc'))))):
                return
            bci.stop()
            channels = ZERO
            if name != 'takeoff':
                manual_until = time.monotonic() + 0.3
            if sim:
                if name != 'takeoff' or (not sim.flying and sim.pos[2] <= 0.05):
                    sim.rc = ZERO
                    getattr(sim, name)()
            elif transport.command(name):
                note = 'Wysłano polecenie: ' + name
            else:
                note = 'Polecenie niedostępne — sprawdź połączenie.'
        elif name == 'photo':
            os.makedirs('photos', exist_ok=True)
            path = os.path.join('photos', time.strftime('%Y%m%d-%H%M%S.jpg'))
            if sim:
                pygame.image.save(ui.view or screen, path)
                note = 'Zapisano: ' + path
            elif transport.command('photo', path):
                note = 'Zlecono zdjęcie: ' + path

    try:
        if sim and not args.wireframe:
            from scenery import ParkRenderer
            from world import obstacles
            ui.renderer = ParkRenderer(shadows=not args.no_shadows, quality=args.quality)
            sim.boxes.extend(obstacles())
        inbox = bci_inbox()
        while running:
            dt = min(clock.tick(60) / 1000, 0.1)
            ui.render_dt = dt
            now = time.monotonic()
            if transport:
                transport.poll()
            flying = sim.flying if sim else transport.flying
            busy = bool(transport and transport.busy and transport.action in ('connect', 'takeoff', 'land', 'emergency'))
            controls = buttons(screen.get_size(), flying, bci.armed, diagnostics, fpv, busy)
            if sim and sim.pos[2] > 0.05 and not sim.flying:
                controls = [(key, label, rect, enabled and key != 'takeoff') for key, label, rect, enabled in controls]
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    running = False
                elif e.type == pygame.VIDEORESIZE:
                    screen = pygame.display.set_mode((max(1000, e.w), max(680, e.h)), pygame.RESIZABLE)
                elif e.type == pygame.JOYDEVICEADDED:
                    if js is None:
                        js = pygame.joystick.Joystick(e.device_index)
                elif e.type == pygame.JOYDEVICEREMOVED and js and e.instance_id == js.get_instance_id():
                    js = None
                    bci.armed = False
                    bci.stop()
                    if flying:
                        action('land')
                    note = 'Pad odłączony — BCI wyłączone, zlecono lądowanie.'
                elif e.type == pygame.WINDOWFOCUSLOST:
                    bci.stop()
                    channels = ZERO
                elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    for key, _, rect, enabled in controls:
                        if enabled and pygame.Rect(rect).collidepoint(e.pos):
                            action(key)
                            break
                elif e.type == pygame.JOYBUTTONDOWN:
                    name = {BTN_TAKEOFF: 'takeoff', BTN_LAND: 'land', BTN_EMERGENCY: 'emergency', BTN_PHOTO: 'photo', BTN_BCI: 'bci'}.get(e.button)
                    if name:
                        action(name)
                elif e.type == pygame.KEYDOWN:
                    if e.key == pygame.K_ESCAPE:
                        running = False
                    name = {pygame.K_t: 'takeoff', pygame.K_l: 'land', pygame.K_SPACE: 'emergency', pygame.K_b: 'bci', pygame.K_p: 'photo', pygame.K_v: 'camera', pygame.K_F1: 'diagnostics'}.get(e.key)
                    if name:
                        action(name)
                    elif pygame.K_1 <= e.key <= pygame.K_4:
                        (bci.up, bci.down, bci.forward, bci.rotate_right)[e.key - pygame.K_1]()
            if not running:
                break
            received = drain_bci(inbox, bci)
            if received:
                note = ('BCI: ' + received) if bci.armed else 'Polecenie pominięte — BCI wyłączone'
            pad = read_pad(js)
            keys = pygame.key.get_pressed()
            keyboard = ZERO
            if pygame.key.get_focused():
                keyboard = Channels(60 * (keys[pygame.K_RIGHT] - keys[pygame.K_LEFT]),
                                    60 * (keys[pygame.K_UP] - keys[pygame.K_DOWN]),
                                    60 * (keys[pygame.K_w] - keys[pygame.K_s]),
                                    60 * (keys[pygame.K_d] - keys[pygame.K_a]))
            manual = pad if pad != ZERO else keyboard
            if manual != ZERO:
                pad_active_at = now
                source = 'Pad' if pad != ZERO else 'Klawiatura'
                bci.stop()
            channels, mixed = mix(manual, bci.channels(now), pad_active_at, now)
            if mixed == 'PS4' and manual == ZERO:
                bci.stop()
                source = 'Przerwa po sterowaniu'
            elif mixed != 'PS4':
                source = 'BCI' if mixed == 'BCI' else 'Oczekiwanie'
            if now < manual_until:
                channels = ZERO
            if sim:
                sim.rc = channels if sim.flying else ZERO
                sim.step(dt)
            else:
                transport.tick(channels, now)
            state = dict(name='Symulator' if sim else transport.name,
                         battery=sim.battery() if sim else transport.battery,
                         connection='Połączono' if sim or transport.connected else 'Brak połączenia',
                         flight=flight_status(), source=source, armed=bci.armed,
                         pad=js.get_name() if js else 'Brak · dostępna klawiatura',
                         channels=channels, last=bci.last,
                         note=('Błąd: ' + transport.error) if transport and transport.error else note)
            busy = bool(transport and (not transport.connected or (transport.busy and transport.action in ('takeoff', 'land', 'emergency'))))
            controls = buttons(screen.get_size(), sim.flying if sim else transport.flying, bci.armed, diagnostics, fpv, busy)
            controls = [(key, label, rect, enabled and not (
                (key == 'camera' and sim is None) or
                (key == 'takeoff' and sim and sim.pos[2] > 0.05 and not sim.flying)))
                for key, label, rect, enabled in controls]
            ui.draw(screen, state, sim, diagnostics, fpv, controls)
    finally:
        try:
            if transport:
                transport.close()
        finally:
            if inbox:
                inbox.close()
            if stimuli is not None and stimuli.poll() is None:
                stimuli.terminate()
                try:
                    stimuli.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    stimuli.kill()
                    stimuli.wait()
            if ui.renderer is not None:
                ui.renderer.close()
            pygame.quit()


if __name__ == '__main__':
    main()
