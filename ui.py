"""Responsive control panel; drawing has no transport side effects."""
import pygame

BG = (14, 18, 27)
PANEL = (24, 31, 44)
FG = (234, 239, 247)
DIM = (151, 165, 185)
BLUE = (74, 142, 233)
RED = (180, 52, 65)


def buttons(size, flying, armed, diagnostics, fpv, busy=False):
    w, h = size
    x, width = w - 288, 264
    return [
        ('takeoff', 'Start  [T]', (x, 178, 126, 46), not flying and not busy),
        ('land', 'Ląduj  [L]', (x + 138, 178, 126, 46), flying and not busy),
        ('bci', 'BCI: ' + ('włączone' if armed else 'wyłączone') + '  [B]', (x, 240, width, 46), True),
        ('stimuli', 'Otwórz bodźce SSVEP', (x, 302, width, 46), True),
        ('camera', 'Kamera: ' + ('FPV' if fpv else 'pościg') + '  [V]', (x, 364, width, 46), True),
        ('diagnostics', ('Ukryj' if diagnostics else 'Pokaż') + ' diagnostykę  [F1]', (x, 426, width, 42), True),
        ('emergency', 'Wyłącz silniki  [SPACJA]', (x, h - 76, width, 48), True),
    ]


class Dashboard:
    def __init__(self):
        self.font = pygame.font.SysFont('dejavusans', 16)
        self.small = pygame.font.SysFont('dejavusans', 13)
        self.big = pygame.font.SysFont('dejavusans', 25, bold=True)
        self.scene_fonts = (self.big, self.small)
        self.view = None
        self.renderer = None
        self.render_dt = 1 / 60

    def text(self, surface, text, pos, color=FG, font=None):
        surface.blit((font or self.font).render(str(text), True, color), pos)

    def draw(self, screen, state, sim, diagnostics, fpv, controls):
        w, h = screen.get_size()
        screen.fill(BG)
        self.text(screen, 'TALON', (24, 17), font=self.big)
        self.text(screen, state['name'], (150, 27), DIM)
        battery = state['battery']
        self.text(screen, f"{state['connection']}   ·   Bateria {'—' if battery is None else str(battery) + '%'}", (w - 550, 27), DIM)
        area = pygame.Rect(20, 76, w - 336, h - 164)
        pygame.draw.rect(screen, PANEL, area, border_radius=12)
        if sim is not None:
            import math
            if self.renderer is not None:
                self.view = self.renderer.render(sim, area.size, fpv, self.render_dt)
            else:
                from sim import CAM_BACK, CAM_UP, FPV_UP, draw
                if self.view is None or self.view.get_size() != area.size:
                    self.view = pygame.Surface(area.size)
                a = math.radians(sim.yaw)
                cam = ([sim.pos[0], sim.pos[1], sim.pos[2] + FPV_UP] if fpv else
                       [sim.pos[0] - CAM_BACK * math.sin(a), sim.pos[1] - CAM_BACK * math.cos(a), sim.pos[2] + CAM_UP])
                draw(self.view, sim, self.scene_fonts, cam, a, fpv, hud=False)
            screen.blit(self.view, area)
            self.text(screen, f"Wysokość {sim.pos[2]:.1f} m   ·   Prędkość {math.hypot(*sim.vel[:2]):.1f} m/s   ·   Bramka {sim.next_gate + 1}/{len(sim.track)}   ·   Okrążenia {sim.laps}", (28, h - 72), DIM, self.small)
        else:
            self.text(screen, 'Panel sterowania · ' + state['name'], (area.x + 24, area.y + 28), font=self.big)
            self.text(screen, 'Podgląd 3D jest dostępny w trybie symulatora.', (area.x + 24, area.y + 78), DIM)
        x = w - 288
        self.text(screen, state['flight'], (x, 85), font=self.big)
        self.text(screen, 'Sterowanie: ' + state['source'], (x, 128), DIM)
        mouse = pygame.mouse.get_pos()
        for key, label, rect, enabled in controls:
            rect = pygame.Rect(rect)
            color = RED if key == 'emergency' else (BLUE if key == 'bci' and state['armed'] else PANEL)
            if enabled and rect.collidepoint(mouse):
                color = tuple(min(255, c + 22) for c in color)
            pygame.draw.rect(screen, color, rect, border_radius=8)
            self.text(screen, label, (rect.x + 12, rect.y + 13), FG if enabled else DIM, self.small)
        if diagnostics:
            box = pygame.Rect(area.x + 12, area.y + 12, min(460, area.width - 24), 138)
            pygame.draw.rect(screen, PANEL, box, border_radius=8)
            lines = [f"Pad: {state['pad']}", f"Kanały RC: {tuple(state['channels'])}",
                     f"Ostatnie BCI: {state['last'] or '—'}", 'Ruch: strzałki · W/S wysokość · A/D obrót',
                     'BCI: 1 góra · 2 dół · 3 przód · 4 obrót']
            for i, line in enumerate(lines):
                self.text(screen, line, (box.x + 12, box.y + 10 + i * 24), DIM, self.small)
        # Clip long transport errors to the notification area.
        previous = screen.get_clip()
        screen.set_clip(pygame.Rect(24, h - 40, w - 350, 30))
        self.text(screen, state['note'], (24, h - 37), DIM, self.small)
        screen.set_clip(previous)
        pygame.display.flip()
