"""SSVEP stimulus window: four flashing squares, one per drone command.

The frequencies are 60/11, 60/9, 60/7 and 60/5 Hz -- a set that
lands on whole frames at a 60Hz refresh, and far enough apart that their
harmonics do not collide below 25Hz.

Modulation is a sinusoid sampled off the wall clock rather than a frame
counter, so the frequency stays correct whatever your monitor actually runs
at. The measured FPS is on screen: if it is not pinned at your refresh rate,
the stimulus is dropping frames and no decoder will like it.

Picking a square (keys 1-4, or a click) sends its command to main.py on UDP
9001, which is where a real decoder would write instead.
"""
import json
import math
import socket
import time

import pygame

BCI_PORT = 9001          # main.py's BCI inbox
HUD_H = 56               # px reserved at the top for the fps/help text
W, H = 1280, 760         # starting size; the window is resizable
SQUARE_WAVE = False      # True if your decoder prefers hard on/off flicker
FILL = 0.66              # square size as a fraction of its grid cell -- the
                         # rest is gap. Lower it if neighbouring squares still
                         # bleed into each other in your recordings.

# freq Hz -> command name main.py expects, the label drawn on the square, and
# where it sits on a 2x2 grid (col, row). List order is the 1-4 key order,
# which matches main.py's keyboard BCI keys.
STIMULI = [(60 / 9, "up", "up", 0, 0),
           (60 / 11, "down", "down", 0, 1),
           (60 / 7, "forward", "forward", 1, 0),
           (60 / 5, "rotate_right", "rotate right", 1, 1)]

BG, FG, DIM, ACCENT = (0, 0, 0), (235, 235, 240), (110, 110, 125), (90, 160, 255)


def level(freq, t):
    """0..1 luminance for this stimulus at time t."""
    phase = (freq * t) % 1.0
    if SQUARE_WAVE:
        return 1.0 if phase < 0.5 else 0.0
    return 0.5 * (1 + math.sin(2 * math.pi * phase))


def layout(w, h):
    """Squares and matching fonts for the current window size.

    Each square sits centred in its quarter of the window (below the HUD), so
    they are spread evenly and maximising pushes them apart rather than just
    growing them.
    """
    top = HUD_H
    pitch_x, pitch_y = w / 2, (h - top) / 2
    box = min(pitch_x, pitch_y) * FILL
    boxes = [pygame.Rect(0, 0, box, box) for _ in STIMULI]
    for r, (_, _, _, col, row) in zip(boxes, STIMULI):
        r.center = ((col + 0.5) * pitch_x, top + (row + 0.5) * pitch_y)
    fonts = [pygame.font.SysFont(None, max(12, int(box * f)))
             for f in (0.22, 0.13, 0.11)]
    return boxes, fonts


def main():
    pygame.init()
    flags = pygame.RESIZABLE
    try:
        # vsync is what keeps the jitter down to nothing; the timing maths is
        # correct without it, just noisier.
        screen = pygame.display.set_mode((W, H), flags, vsync=1)
    except pygame.error:
        screen = pygame.display.set_mode((W, H), flags)
    pygame.display.set_caption("SSVEP stimulus")
    hud = pygame.font.SysFont(None, 22)
    clock = pygame.time.Clock()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    boxes, fonts = layout(*screen.get_size())
    selected, selected_at = -1, -999.0
    t0 = time.monotonic()
    running = True
    while running:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
                continue
            if e.type == pygame.VIDEORESIZE:
                screen = pygame.display.set_mode(e.size, flags)
                boxes, fonts = layout(*e.size)
                continue
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                running = False
                continue
            if e.type == pygame.KEYDOWN and pygame.K_1 <= e.key <= pygame.K_4:
                selected = e.key - pygame.K_1
            elif e.type == pygame.MOUSEBUTTONDOWN:
                hit = [i for i, b in enumerate(boxes) if b.collidepoint(e.pos)]
                if not hit:
                    continue
                selected = hit[0]
            else:
                continue
            selected_at = time.monotonic()
            sock.sendto(json.dumps({"cmd": STIMULI[selected][1]}).encode(),
                        ("127.0.0.1", BCI_PORT))

        # one clock read for the whole frame, so all four share a phase origin
        now = time.monotonic()
        t = now - t0
        screen.fill(BG)
        for i, ((freq, _, label, _, _), box) in enumerate(zip(STIMULI, boxes)):
            v = int(255 * level(freq, t))
            pygame.draw.rect(screen, (v, v, v), box)
            if i == selected and now - selected_at < 0.6:
                pygame.draw.rect(screen, ACCENT, box.inflate(14, 14), 4)
            # labels flip black/white with the square, so they stay readable at
            # every phase. 255 - v would go invisible as the square passes
            # mid-grey, which is exactly twice a cycle.
            ink = (0, 0, 0) if v > 127 else (255, 255, 255)
            lines = (f"{freq:.2f} Hz", label, f"[{i + 1}]")
            imgs = [f.render(s, True, ink) for f, s in zip(fonts, lines)]
            y = box.centery - sum(im.get_height() for im in imgs) / 2
            for im in imgs:
                screen.blit(im, (box.centerx - im.get_width() // 2, y))
                y += im.get_height()

        fps = clock.get_fps()
        screen.blit(hud.render(f"{fps:5.1f} fps  (must hold at your refresh rate "
                               f"or the flicker is wrong)", True,
                               DIM if fps > 55 else (255, 90, 90)), (20, 16))
        screen.blit(hud.render("keys 1-4 or click to fire that command   |   "
                               "resize or maximise for wider spacing",
                               True, DIM), (20, 36))
        pygame.display.flip()
        clock.tick(240)  # vsync paces us; this only stops a failed vsync spinning

    pygame.quit()


def demo():
    """The only thing worth checking here is that the maths gives real Hz."""
    for freq, _, _, _, _ in STIMULI:
        rising = sum(level(freq, i / 1000.0) > 0.5 >= level(freq, (i - 1) / 1000.0)
                     for i in range(1, 10_001))
        assert abs(rising - freq * 10) <= 1, (freq, rising)
    assert level(10, 0.0) == 0.5 and level(10, 0.025) > 0.99

    pygame.init()
    pygame.display.set_mode((1, 1))
    for size in ((1280, 760), (1920, 1080), (700, 500)):
        boxes, _ = layout(*size)
        assert all(b.width == b.height for b in boxes), "not square"
        assert all(0 <= b.left and b.right <= size[0] for b in boxes), "off screen"
        assert all(0 <= b.top and b.bottom <= size[1] for b in boxes), "off screen"
        for i, a in enumerate(boxes):          # no two squares touch
            for b in boxes[i + 1:]:
                assert not a.colliderect(b), (size, a, b)
        assert all(b.top >= HUD_H for b in boxes), "under the HUD"
        # evenly spread: every square centred in its own quarter below the HUD
        cx = sorted({b.centerx for b in boxes})
        cy = sorted({b.centery for b in boxes})
        assert len(cx) == len(cy) == 2, (cx, cy)
        assert abs(cx[0] - size[0] / 4) <= 1 and abs(cx[1] - size[0] * 3 / 4) <= 1
        assert abs((cy[0] - HUD_H) * 3 - (cy[1] - HUD_H)) <= 3, cy
    pygame.quit()
    print("ssvep ok:", ", ".join(f"{f:.2f}Hz={n}" for f, n, _, _, _ in STIMULI))


if __name__ == "__main__":
    import sys
    demo() if "--test" in sys.argv else main()
