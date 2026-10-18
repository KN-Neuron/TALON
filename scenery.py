"""Panda3D park renderer. The existing flight model remains the source of truth.

Renders into a GPU buffer and copies the result to the Pygame dashboard. All
meshes and textures are generated locally; no external asset downloads needed.
"""
import math
import random
from pathlib import Path

import numpy as np
import pygame
from panda3d.core import (
    AlphaTestAttrib, AmbientLight, AntialiasAttrib, DirectionalLight, Fog, Geom, GeomNode,
    GeomTriangles, GeomVertexData, GeomVertexFormat, GeomVertexWriter,
    GraphicsOutput, Material, NodePath, Shader, Texture, Vec3, loadPrcFileData,
)
from world import BUILDINGS, trees
from details import ParkDetails

QUALITY = {
    "low": {"size": (800, 500), "shadow": 1024},
    "balanced": {"size": (1024, 640), "shadow": 2048},
    "high": {"size": (1440, 900), "shadow": 4096},
}


def mesh(name, vertices, normals, uvs, triangles):
    data = GeomVertexData(name, GeomVertexFormat.getV3n3t2(), Geom.UHStatic)
    data.setNumRows(len(vertices))
    writers = [GeomVertexWriter(data, col) for col in ('vertex', 'normal', 'texcoord')]
    for p, n, uv in zip(vertices, normals, uvs):
        writers[0].addData3(*p)
        writers[1].addData3(*n)
        writers[2].addData2(*uv)
    primitive = GeomTriangles(Geom.UHStatic)
    for tri in triangles:
        primitive.addVertices(*tri)
    geom = Geom(data)
    geom.addPrimitive(primitive)
    node = GeomNode(name)
    node.addGeom(geom)
    return NodePath(node)


def box_mesh():
    vertices, normals, uvs, tris = [], [], [], []
    faces = [((1, 0, 0), [(1,-1,-1),(1,1,-1),(1,1,1),(1,-1,1)]),
             ((-1,0,0), [(-1,1,-1),(-1,-1,-1),(-1,-1,1),(-1,1,1)]),
             ((0,1,0), [(1,1,-1),(-1,1,-1),(-1,1,1),(1,1,1)]),
             ((0,-1,0), [(-1,-1,-1),(1,-1,-1),(1,-1,1),(-1,-1,1)]),
             ((0,0,1), [(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]),
             ((0,0,-1), [(-1,1,-1),(1,1,-1),(1,-1,-1),(-1,-1,-1)])]
    for n, points in faces:
        start = len(vertices)
        vertices.extend([(x/2,y/2,z/2) for x,y,z in points])
        normals.extend([n]*4)
        uvs.extend([(0,0),(1,0),(1,1),(0,1)])
        tris.extend([(start,start+1,start+2),(start,start+2,start+3)])
    return mesh('box', vertices, normals, uvs, tris)


def rounded_mesh(rings=12, sides=20):
    vertices, normals, uvs, tris = [], [], [], []
    for j in range(rings+1):
        phi = math.pi * j / rings
        for i in range(sides+1):
            theta = math.tau*i/sides
            n = (math.sin(phi)*math.cos(theta), math.sin(phi)*math.sin(theta), math.cos(phi))
            vertices.append(n)
            normals.append(n)
            uvs.append((i/sides,j/rings))
    for j in range(rings):
        for i in range(sides):
            a=j*(sides+1)+i
            tris.extend([(a,a+sides+1,a+1),(a+1,a+sides+1,a+sides+2)])
    return mesh('rounded', vertices, normals, uvs, tris)


def cylinder_mesh(sides=24):
    vertices, normals, uvs, tris = [], [], [], []
    for i in range(sides+1):
        a = math.tau*i/sides
        for z in (0,1):
            vertices.append((math.cos(a),math.sin(a),z))
            normals.append((math.cos(a),math.sin(a),0))
            uvs.append((i/sides,z))
    for i in range(sides):
        a=i*2
        tris.extend([(a,a+2,a+1),(a+1,a+2,a+3)])
    for z, normal in ((0,(0,0,-1)),(1,(0,0,1))):
        center=len(vertices)
        vertices.append((0,0,z)); normals.append(normal); uvs.append((.5,.5))
        for i in range(sides):
            a=len(vertices)
            for theta in (math.tau*i/sides, math.tau*(i+1)/sides):
                vertices.append((math.cos(theta), math.sin(theta),z)); normals.append(normal); uvs.append((0,0))
            tris.append((center,a,a+1) if z else (center,a+1,a))
    return mesh('cylinder', vertices, normals, uvs, tris)


def texture(kind):
    rng = np.random.default_rng(16)
    size = 256
    yy, xx = np.mgrid[:size,:size]
    noise = rng.normal(0,1,(size,size))
    if kind == 'grass':
        frequencies=np.fft.fftfreq(size)
        power=frequencies[:,None]**2+frequencies[None,:]**2
        coarse=np.fft.ifft2(np.fft.fft2(noise)*np.exp(-power/.002)).real
        coarse=coarse/max(.001,coarse.std())
        value = noise*7 + coarse*5
        color = np.array([84,105,53]) + value[:,:,None]*np.array([.8,1,.5])
        # Fine blades, with a seamless repeating tile.
        blades = rng.random((size,size)) > .94
        color[blades] += np.array([18,22,7])
    elif kind == 'asphalt':
        color = np.array([67,70,72]) + noise[:,:,None]*5
    elif kind == 'glass':
        vertical = yy / (size-1)
        reflection = np.exp(-((vertical-.44)/.12)**2)*35
        color = np.array([83,119,136]) + (vertical*-24+reflection)[:,:,None]
    elif kind == 'wood':
        grain=5*np.sin(yy*.25+np.sin(xx*.04)*1.5)+noise*2
        color=np.array([141,105,66])+grain[:,:,None]
    elif kind == 'bark':
        value = 10*np.sin(xx*.5) + noise*7
        color = np.array([103,85,65]) + value[:,:,None]
    else:
        joints = ((xx % 64 < 2) | (yy % 64 < 2))*-22
        color = np.array([163,163,149]) + (noise*3+joints)[:,:,None]
    pixels = np.clip(color,0,255).astype('uint8')
    tex=Texture(kind)
    tex.setup2dTexture(size,size,Texture.TUnsignedByte,Texture.FRgb8)
    tex.setRamImageAs(pixels.tobytes(),'RGB')
    tex.setMinfilter(Texture.FTLinearMipmapLinear)
    tex.setMagfilter(Texture.FTLinear)
    tex.setAnisotropicDegree(8)
    return tex


def leaf_texture():
    """An alpha-cut canopy atlas with individual leaves, generated at startup."""
    rng=np.random.default_rng(35)
    size=256
    yy,xx=np.mgrid[:size,:size]
    pixels=np.zeros((size,size,4),dtype='uint8')
    for _ in range(260):
        cx,cy=rng.uniform(25,231,2)
        if ((cx-128)/112)**2+((cy-128)/112)**2>1:
            continue
        a=rng.uniform(0,math.tau)
        dx,dy=xx-cx,yy-cy
        u,v=dx*math.cos(a)+dy*math.sin(a),-dx*math.sin(a)+dy*math.cos(a)
        rx,ry=rng.uniform(6,13),rng.uniform(3,6)
        mask=(u/rx)**2+(v/ry)**2<1
        shade=rng.uniform(.65,1.35)
        pixels[mask,:3]=np.clip(np.array([99,131,55])*shade,0,255).astype('uint8')
        pixels[mask,3]=255
        vein=mask & (abs(v)<.4)
        pixels[vein,:3]=np.array([132,150,66])
    tex=Texture('oak-leaves')
    tex.setup2dTexture(size,size,Texture.TUnsignedByte,Texture.FRgba8)
    tex.setRamImageAs(pixels.tobytes(),'RGBA')
    tex.setMinfilter(Texture.FTLinearMipmapLinear)
    tex.setMagfilter(Texture.FTLinear)
    return tex


class ParkRenderer(ParkDetails):
    def __init__(self, size=None, shadows=True, quality='balanced'):
        if quality not in QUALITY:
            raise ValueError(f'Unknown graphics quality: {quality}')
        self.quality=quality
        size=size or QUALITY[quality]['size']
        from direct.showbase.ShowBase import ShowBase
        loadPrcFileData('', '\n'.join([
            'window-type offscreen', f'win-size {size[0]} {size[1]}',
            'audio-library-name null', 'sync-video false', 'show-frame-rate-meter false',
            'framebuffer-multisample false', 'multisamples 0',
            'notify-level warning', 'textures-power-2 none',
        ]))
        self.base = ShowBase(windowType='offscreen')
        if self.base.win is None:
            self.base.destroy()
            raise RuntimeError('Nie udało się utworzyć kontekstu 3D. Użyj --sim --wireframe.')
        self.base.disableMouse()
        self.root = self.base.render
        self.base.setBackgroundColor(.66,.77,.85,1)
        self.root.setAntialias(AntialiasAttrib.MMultisample)
        self.base.camLens.setFov(72)
        self.base.camLens.setNearFar(.06,350)
        self.cube, self.sphere, self.cylinder = box_mesh(), rounded_mesh(), cylinder_mesh()
        self.bud=rounded_mesh(5,8)
        self.shrub=rounded_mesh(8,12)
        self.textures = {kind:texture(kind) for kind in ('grass','asphalt','bark','concrete','glass','wood')}
        self.materials={}
        for name,shine,specular in (('metal',48,.38),('glass',90,.55),('paint',24,.16)):
            material=Material(name)
            material.setShininess(shine)
            material.setSpecular((specular,specular,specular,1))
            self.materials[name]=material
        self.leaves = leaf_texture()
        self.leaf_card = mesh('leaf-card', [(-1,0,-1),(1,0,-1),(1,0,1),(-1,0,1)], [(0,-1,0)]*4, [(0,0),(1,0),(1,1),(0,1)], [(0,1,2),(0,2,3)])
        self.static = self.root.attachNewNode('campus')
        self.gates=[]
        self.props=[]
        self.camera_pos=None
        self.last_fpv=None
        self.time=0
        self.buffer_size=size
        self.texture=Texture('park-frame')
        self.base.win.addRenderTexture(self.texture, GraphicsOutput.RTMCopyRam, GraphicsOutput.RTPColor)
        ambient=AmbientLight('sky-fill'); ambient.setColor((.53,.57,.62,1))
        self.root.setLight(self.root.attachNewNode(ambient))
        sun=DirectionalLight('late-afternoon-sun'); sun.setColor((.88,.82,.71,1))
        if shadows:
            sun.setShadowCaster(True,QUALITY[quality]['shadow'],QUALITY[quality]['shadow'])
            sun.getLens().setFilmSize(100,100)
            sun.getLens().setNearFar(1,180)
        self.sun=self.root.attachNewNode(sun)
        self.sun.setPos(-35,-40,65); self.sun.lookAt(15,15,0)
        self.root.setLight(self.sun)
        self.root.setShaderAuto()
        fog=Fog('distance-haze'); fog.setColor(.66,.77,.85); fog.setExpDensity(.006)
        self.root.setFog(fog)
        self._sky()
        self._park()
        self._details()
        self._drone()
        self.static.flattenStrong()
        self._postprocess()

    def place(self, shape, position, scale, color, parent=None, tex=None, repeat=(1,1), material=None):
        node=shape.copyTo(parent if parent is not None else self.static)
        node.setPos(*position); node.setScale(*scale); node.setColor(*color,1)
        if material:
            node.setMaterial(self.materials[material])
        if tex:
            from panda3d.core import TextureStage
            node.setTexture(self.textures[tex])
            node.setTexScale(TextureStage.getDefault(),*repeat)
        return node

    def box(self, pos, size, color, **kwargs):
        return self.place(self.cube,pos,size,color,**kwargs)

    def pole(self, a, b, radius, color, parent=None, tex=None, material=None):
        node=self.place(self.cylinder,a,(radius,radius,(Vec3(*b)-Vec3(*a)).length()),color,parent=parent,tex=tex,material=material)
        node.lookAt(Vec3(*b)); node.setP(node.getP()-90)
        return node

    def _postprocess(self):
        from direct.filter.FilterManager import FilterManager
        self.filters=FilterManager(self.base.win,self.base.cam)
        scene=Texture('unfiltered-park')
        self.scene_texture=scene
        scene.setMinfilter(Texture.FTLinear); scene.setMagfilter(Texture.FTLinear)
        scene.setWrapU(Texture.WMClamp); scene.setWrapV(Texture.WMClamp)
        self.filter_quad=self.filters.renderSceneInto(colortex=scene)
        if self.filter_quad is None:
            self.filters.cleanup()
            self.base.destroy()
            raise RuntimeError('Nie udało się utworzyć filtra wygładzania obrazu.')
        shader_dir=Path(__file__).resolve().parent/'shaders'
        shader=Shader.load(Shader.SLGLSL,str(shader_dir/'scene.vert'),str(shader_dir/'scene.frag'))
        self.filter_quad.setShader(shader)
        self.filter_quad.setShaderInput('scene',scene)
        self.filter_quad.setShaderInput('pixel_size',(1/self.buffer_size[0],1/self.buffer_size[1]))

    def _sky(self):
        rng=np.random.default_rng(91)
        width,height=512,256
        sky=np.zeros((height,width,3),dtype='float64')
        # Equirectangular sky: light horizon, blue zenith and soft cloud banks.
        yy,xx=np.mgrid[:height,:width]
        altitude=np.clip((height/2-yy)/(height/2),0,1)
        horizon=np.array([193,211,218])
        zenith=np.array([93,145,189])
        sky[:]=horizon+(zenith-horizon)*altitude[:,:,None]**.65
        noise=rng.normal(0,1,(height,width))
        fy,fx=np.fft.fftfreq(height),np.fft.fftfreq(width)
        power=fy[:,None]**2+fx[None,:]**2
        clouds=np.fft.ifft2(np.fft.fft2(noise)*np.exp(-power/.0008)).real
        clouds/=max(.001,clouds.std())
        cloud=np.clip((clouds-.05)*.6,0,.85)*np.clip(altitude*5,0,1)
        sky=sky*(1-cloud[:,:,None])+np.array([235,236,227])*cloud[:,:,None]
        tex=Texture('cloudy-sky')
        tex.setup2dTexture(width,height,Texture.TUnsignedByte,Texture.FRgb8)
        tex.setRamImageAs(np.clip(sky,0,255).astype('uint8').tobytes(),'RGB')
        tex.setMinfilter(Texture.FTLinear); tex.setMagfilter(Texture.FTLinear)
        sky_node=self.place(self.sphere,(15,15,0),(175,175,175),(1,1,1),parent=self.root)
        sky_node.setTexture(tex)
        sky_node.setTwoSided(True)
        sky_node.setLightOff(); sky_node.setShaderOff(); sky_node.setFogOff()
        sky_node.setDepthWrite(False); sky_node.setBin('background',0)

    def _park(self):
        self.box((15,15,-.24),(240,240,.45),(1,1,1),tex='grass',repeat=(90,90))
        # Asphalt loop follows the actual gate course, with concrete edging.
        paths=[((0,13,.005),(7.8,64,.06)),((30,15,.006),(7.8,38,.06)),
               ((15,30,.007),(38,7.8,.06)),((15,0,.008),(38,7.8,.06))]
        for pos,size in paths:
            self.box((pos[0],pos[1],-.01),(size[0]+.5,size[1]+.5,.12),(.67,.66,.6))
            self.box((pos[0],pos[1],.055),size,(1,1,1),tex='asphalt',repeat=(size[0]/3,size[1]/3))
        self.box((0,-2,.10),(3.4,3.4,.05),(.22,.26,.28))
        self.box((0,-2,.132),(2.9,.12,.015),(.95,.8,.3))
        self.box((0,-2,.133),(.12,2.9,.015),(.95,.8,.3))
        # Perimeter garden paths and planted beds.
        self.box((15,49,.02),(82,3,.08),(1,1,1),tex='concrete',repeat=(32,2))
        rng=random.Random(2026)
        for x,y,height,species in trees():
            self._tree(x,y,height,species,rng)
        for building in BUILDINGS:
            self._building(*building)
        for y in (-8,5,18,33,44):
            for x in (-4.8,34.8):
                self._lamp(x,y)
        for x,y in ((8,7),(23,24),(-7,29),(37,7)):
            self._bench(x,y)
        # Reeds, grasses and small shrubs soften the edges of the path.
        for i in range(150):
            x,y=rng.uniform(-60,80),rng.uniform(-35,80)
            if -6<x<36 and -6<y<36:
                continue
            self.place(self.shrub,(x,y,.24),(rng.uniform(.3,.9),.5,.35),(.24,.34,.14))
        from sim import TRACK, gate_boxes
        for index,gate in enumerate(TRACK):
            group=self.root.attachNewNode(f'gate-{index}')
            for x0,y0,z0,x1,y1,z1 in gate_boxes(gate):
                self.box(((x0+x1)/2,(y0+y1)/2,(z0+z1)/2),
                         (x1-x0,y1-y0,z1-z0),(.94,.96,.94),parent=group)
            cx,cy,axis,bottom=gate
            # Thin luminous inset follows the opening, not the collision frame.
            from sim import GATE_W,GATE_H
            hw=GATE_W/2
            for side in (-1,1):
                pos=(cx+side*(hw+.09),cy-.23,bottom+GATE_H/2) if axis=='x' else (cx-.23,cy+side*(hw+.09),bottom+GATE_H/2)
                self.box(pos,(.09,.09,GATE_H),(.12,.8,.61),parent=group)
            self.gates.append(group)
            from panda3d.core import TextNode
            text=TextNode(f'number-{index}'); text.setText(f'{index+1:02}'); text.setAlign(TextNode.ACenter)
            text.setTextColor(.12,.18,.19,1)
            label=group.attachNewNode(text); label.setScale(.38)
            label.setPos(cx,cy-.24,bottom+GATE_H+.5)
            if axis=='y':
                label.setH(90)

    def _tree(self,x,y,h,species,rng):
        trunk=h*.56
        self.pole((x,y,0),(x+.15,y,trunk),.26,(1,1,1),tex='bark')
        palette=[(.30,.43,.16),(.39,.46,.17),(.47,.43,.17)]
        base=palette[species]
        for i in range(11):
            a=i*2.4
            spread=1.5 if i<7 else .8
            cx,cy=x+math.cos(a)*spread,y+math.sin(a)*spread
            cz=trunk+rng.uniform(-.4,1.7)+(1 if i>7 else 0)
            if i<5:
                self.pole((x,y,trunk*.65),(cx,cy,cz),.10,(.37,.29,.20))
            tint=rng.uniform(.85,1.15)
            # Overlapping leaf cards break up the crown silhouette and expose
            # individual leaves, instead of rendering solid balloon-like lobes.
            for j in range(6):
                leaf=self.place(self.leaf_card,(cx+rng.uniform(-.7,.7),cy+rng.uniform(-.7,.7),cz+rng.uniform(-.6,.6)),
                                (rng.uniform(1.6,2.3),1,rng.uniform(1.6,2.3)),
                                (tint, tint*(.95 if species==2 else 1), tint*(.7 if species==2 else 1)))
                leaf.setTexture(self.leaves)
                leaf.setTwoSided(True)
                leaf.setAttrib(AlphaTestAttrib.make(AlphaTestAttrib.MGreaterEqual,.5))
                leaf.setHpr(rng.uniform(0,360),rng.uniform(-55,55),rng.uniform(-35,35))

    def _building(self,x,y,w,d,h):
        self.box((x,y,h/2),(w,d,h),(.81,.79,.70),tex='concrete',repeat=(w/3,h/3))
        self.box((x,y,h+.15),(w+.5,d+.5,.3),(.24,.28,.30))
        # Recessed glass strips and pale structural mullions on all facades.
        for z in np.arange(2.4,h-1,3.2):
            for side in (-1,1):
                fy=y+side*(d/2+.015)
                self.box((x,fy,z),(w-.9,.08,1.8),(1,1,1),tex='glass',material='glass',repeat=(w/4,1))
                self.box((x,fy,z-.85),(w,.18,.13),(.61,.64,.61))
                for wx in np.arange(x-w/2+.8,x+w/2,.95):
                    self.box((float(wx),fy+side*.06,z),(.055,.10,1.8),(.66,.69,.67))
                fx=x+side*(w/2+.015)
                self.box((fx,y,z),(.08,d-.9,1.8),(1,1,1),tex='glass',material='glass',repeat=(d/4,1))
                for wy in np.arange(y-d/2+.8,y+d/2,1.3):
                    self.box((fx+side*.06,float(wy),z),(.10,.055,1.8),(.66,.69,.67))
        for dx in (-w*.25,w*.25):
            self.box((x+dx,y,h+.65),(2.8,3.5,.9),(.48,.52,.52))
            for i in range(6):
                self.box((x+dx-1.2+i*.45,y,h+1.13),(.08,3,.06),(.18,.23,.24))
        # Entrance canopy, supports and glass doors.
        fy=y-d/2-1.2
        self.box((x,fy,3.25),(6,3,.22),(.26,.31,.32))
        for dx in (-2.7,2.7):
            self.pole((x+dx,fy-1.2,0),(x+dx,fy-1.2,3.2),.07,(.58,.60,.58))
        self.box((x,y-d/2-.06,1.4),(3,.12,2.8),(.13,.26,.30))
        self.box((x,fy,.04),(7,4,.12),(1,1,1),tex='concrete',repeat=(5,3))

    def _lamp(self,x,y):
        self.pole((x,y,0),(x,y,.85),.065,(.23,.28,.29))
        self.box((x,y,.94),(.19,.19,.24),(.98,.94,.70))
        self.box((x,y,1.08),(.23,.23,.04),(.17,.22,.23))

    def _bench(self,x,y):
        for i in range(4):
            self.box((x,y+i*.13,.48),(2,.10,.08),(1,1,1),tex='wood',repeat=(3,.3))
            self.box((x,y+.48,.66+i*.13),(2,.08,.10),(1,1,1),tex='wood',repeat=(3,.3))
        for dx in (-.75,.75):
            self.box((x+dx,y+.23,.23),(.08,.46,.46),(.18,.23,.24))

    def _drone(self):
        self.drone=self.root.attachNewNode('quadcopter')
        dark=(.08,.10,.12)
        self.box((0,0,.13),(.34,.48,.16),dark,parent=self.drone)
        self.box((0,-.04,.25),(.20,.30,.13),(.29,.32,.32),parent=self.drone,material='metal')
        self.box((0,.28,.18),(.22,.13,.20),dark,parent=self.drone)
        self.place(self.cylinder,(0,.35,.18),(.06,.06,.035),(.15,.32,.38),parent=self.drone,material='glass').setP(-90)
        for x in (-.43,.43):
            for y in (-.40,.40):
                self.pole((0,0,.09),(x,y,.09),.035,dark,parent=self.drone)
                self.place(self.cylinder,(x,y,.09),(.07,.07,.11),(.27,.30,.32),parent=self.drone)
                self.box((x,y,.045),(.18,.15,.045),(.21,.73,.48) if y>0 else (.27,.31,.33),parent=self.drone)
                prop=self.drone.attachNewNode('propeller')
                prop.setPos(x,y,.22)
                for angle in (0,90):
                    blade=self.box((0,0,0),(.46,.035,.012),(.19,.22,.24),parent=prop)
                    blade.setH(angle)
                self.props.append(prop)
        for x in (-.18,.18):
            self.pole((x,-.17,.08),(x,-.17,-.06),.022,dark,parent=self.drone)

    def render(self, sim, size, fpv=False, dt=1/60):
        # Keep a fixed render target to avoid reallocating GPU buffers while
        # dragging the dashboard. The lens accounts for the output aspect ratio.
        target=self.buffer_size
        self.base.camLens.setAspectRatio(size[0]/size[1])
        self.time+=dt
        x,y,z=sim.pos
        a=math.radians(sim.yaw)
        forward=Vec3(math.sin(a),math.cos(a),0)
        self.drone.setPos(x,y,z+.12)
        self.drone.setH(-sim.yaw)
        self.drone.setP(-sim.rc[1]*.10 if sim.flying else 0)
        self.drone.setR(sim.rc[0]*.10 if sim.flying else 0)
        self.drone.hide() if fpv else self.drone.show()
        for i,prop in enumerate(self.props):
            prop.setH(self.time*(2200 if sim.flying else 0)*(1 if i%2 else -1))
        desired=Vec3(x,y,max(.6,z+.8))+forward*.32 if fpv else Vec3(x,y,max(1.65,z+2.7))-forward*6
        if self.camera_pos is None or self.last_fpv!=fpv or fpv:
            self.camera_pos=desired
        else:
            self.camera_pos+=(desired-self.camera_pos)*min(1,dt*6)
        self.last_fpv=fpv
        self.base.camera.setPos(self.camera_pos)
        self.base.camera.lookAt(Vec3(x,y,z+.65)+forward*(12 if fpv else 2.2))
        for i,gate in enumerate(self.gates):
            gate.setColorScale((.44,1,.75,1) if i==sim.next_gate else (1,.91,.75,1))
        self.base.graphicsEngine.renderFrame()
        if not self.texture.hasRamImage():
            raise RuntimeError('Silnik 3D nie zwrócił obrazu.')
        data=bytes(self.texture.getRamImageAs('RGB'))
        frame=pygame.image.frombuffer(data,target,'RGB')
        frame=pygame.transform.flip(frame,False,True)
        return frame if target==size else pygame.transform.smoothscale(frame,size)

    def close(self):
        self.filters.cleanup()
        self.base.destroy()
