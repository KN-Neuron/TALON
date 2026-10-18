"""Deterministic campus layout shared by graphics and obstacle collisions."""
import random

# Buildings: centre x/y, width/depth, height.
BUILDINGS = [(-26, 18, 18, 37, 12), (54, 18, 21, 40, 16),
             (14, 62, 57, 17, 11), (-29, -23, 24, 16, 8)]


def trees():
    rng = random.Random(71)
    positions = [(-10, y) for y in range(-12, 52, 9)]
    positions += [(40, y) for y in range(-9, 51, 10)]
    positions += [(x, 43) for x in range(-4, 35, 9)]
    positions += [(x, -11) for x in range(4, 36, 10)]
    positions += [(x, y) for x in (10, 21) for y in (10, 21)]
    return [(x + rng.uniform(-1, 1), y + rng.uniform(-1, 1), rng.uniform(7, 11), rng.randrange(3))
            for x, y in positions]


def obstacles():
    boxes = [(x - w / 2, y - d / 2, 0, x + w / 2, y + d / 2, h)
             for x, y, w, d, h in BUILDINGS]
    boxes += [(x - .35, y - .35, 0, x + .35, y + .35, h * .65)
              for x, y, h, _ in trees()]
    return boxes
