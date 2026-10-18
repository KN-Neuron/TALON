"""GPU integration check: real frames, resize, cameras and campus collisions.

Run on a desktop or with an available offscreen OpenGL backend.
"""
import os
import time
os.environ.setdefault('SDL_VIDEODRIVER','dummy')
os.environ.setdefault('SDL_AUDIODRIVER','dummy')
import pygame
import numpy as np
from scenery import ParkRenderer
from sim import Sim
from world import obstacles

pygame.init()
sim=Sim()
sim.boxes.extend(obstacles())
assert not sim.hit(), 'launch area must be clear'
sim.pos=[-26,18,1]
assert sim.hit(), 'building must collide'
sim.pos=[0,0,1.2]
sim.flying=True
quality=os.environ.get('TALON_TEST_QUALITY','balanced')
renderer=ParkRenderer(quality=quality)
try:
    for _ in range(3):
        frame=renderer.render(sim,(960,640))
    start=time.perf_counter()
    for _ in range(30):
        renderer.render(sim,(960,640))
    print(f'Render benchmark ({quality}, internal {renderer.buffer_size}): {30/(time.perf_counter()-start):.1f} fps (including readback)')
    assert not renderer.filter_quad.getShader().getErrorFlag(), 'postprocess shader must compile'
    assert renderer.filters.buffers, 'postprocessing buffer must exist'
    pixels=pygame.surfarray.array3d(frame)
    assert pixels.std()>20, 'frame should contain actual scenery'
    pygame.image.save(frame,'/tmp/talon-park-chase.png')
    fpv=renderer.render(sim,(800,500),True)
    assert fpv.get_size()==(800,500)
    assert renderer.drone.isHidden()
    pygame.image.save(fpv,'/tmp/talon-park-fpv.png')
    renderer.render(sim,(960,640),False)
    assert not renderer.drone.isHidden()
finally:
    renderer.close()
    pygame.quit()
print('scenery ok: textured scene, resize, FPV/chase, campus collisions, cleanup')
