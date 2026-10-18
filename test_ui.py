"""Headless integration checks for panel actions, cleanup and malformed BCI input."""
import json
import os
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
import pygame
import main
from control import BCI
from ui import Dashboard


class Inbox:
    def __init__(self):
        self.messages = iter([b'[]', b'null', b'7', b'"text"', b'\xff', b'{',
                              json.dumps({'cmd': 'up'}).encode()])

    def recvfrom(self, size):
        try:
            return next(self.messages), None
        except StopIteration:
            raise BlockingIOError


bci = BCI()
bci.armed = True
assert main.drain_bci(Inbox(), bci) == 'up'
assert bci.channels().ud > 0

original = Dashboard.draw
original_inbox = main.bci_inbox
frames = []


def draw(self, screen, state, sim, diagnostics, fpv, controls):
    original(self, screen, state, sim, diagnostics, fpv, controls)
    frames.append((state.copy(), diagnostics, fpv))
    frame = len(frames)
    if frame == 1:
        assert state['flight'] == 'Na ziemi'
        # Exercise actual mouse hit detection.
        rect = pygame.Rect(next(r for key, _, r, _ in controls if key == 'takeoff'))
        pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=rect.center))
    elif frame == 2:
        assert sim.flying
        for key in (pygame.K_b, pygame.K_3, pygame.K_F1, pygame.K_v):
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key))
    elif frame == 3:
        assert state['armed'] and diagnostics and fpv
        assert sim.rc[1] > 0
        pygame.image.save(screen, '/tmp/talon-dashboard.png')
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_l))
    elif frame == 4:
        assert not sim.flying and sim.rc == (0, 0, 0, 0)
        pygame.event.post(pygame.event.Event(pygame.QUIT))


arguments = ['main.py', '--sim'] + ([] if os.environ.get('TALON_TEST_3D') else ['--wireframe'])
with patch('sys.argv', arguments), patch.object(Dashboard, 'draw', draw), patch.object(main, 'bci_inbox', lambda: original_inbox(0)):
    main.main()
assert len(frames) == 4
assert not pygame.get_init()
print('ui ok: click takeoff, BCI pulse, diagnostics, camera, land, cleanup')
