"""Small campus props and batched vegetation; decoration leaves the course clear."""
import math
import random

from panda3d.core import TextNode


class ParkDetails:
    def _details(self):
        self._grass()
        self._curbs()
        self._flowerbeds()
        for x,y in ((-5.7,6),(35.7,19),(8,39)):
            self._bin(x,y)
        for x,y in ((-5.6,19),(35.6,2)):
            self._bike_rack(x,y)
        for x,y in ((0,8),(30,23),(17,30)):
            self._drain(x,y)
        self._sign(-5.7,-3,'TALON / CAMPUS','TRASA TRENINGOWA')
        self._sign(35.8,27,'PARK / SEKTOR B','STREFA LOTOW')
        # Separate curb joints and narrow planted edges give the ground scale.
        for y in range(-14,42,4):
            self.box((-4.17,y,.065),(.28,.035,.10),(.40,.41,.37))
            self.box((34.17,y,.065),(.28,.035,.10),(.40,.41,.37))

    def _curbs(self):
        for x in (-4.06,4.06,25.94,34.06):
            self.box((x,15,.072),(.20,20.7,.15),(.65,.66,.60),tex='concrete',repeat=(.3,16))
        for y in (-4.06,4.06,25.94,34.06):
            self.box((15,y,.072),(20.7,.20,.15),(.65,.66,.60),tex='concrete',repeat=(16,.3))

    def _grass(self):
        from scenery import mesh
        rng=random.Random(401)
        vertices,normals,uvs,triangles=[],[],[],[]
        amount=1800 if self.quality=='low' else 3800
        for _ in range(amount):
            x,y=rng.uniform(-14,45),rng.uniform(-16,48)
            road=(min(abs(x),abs(x-30))<4.65 and -20<y<45) or (min(abs(y),abs(y-30))<4.65 and -5<x<35)
            if road:
                continue
            h=rng.uniform(.07,.24)
            for angle in (rng.random()*math.tau,rng.random()*math.tau):
                dx,dy=math.cos(angle)*.026,math.sin(angle)*.026
                index=len(vertices)
                vertices.extend([(x-dx,y-dy,.01),(x+dx,y+dy,.01),(x+dx*2,y+dy*2,h)])
                normals.extend([(0,0,1)]*3)
                uvs.extend([(0,0),(1,0),(.5,1)])
                triangles.append((index,index+1,index+2))
        grass=mesh('grass-blades',vertices,normals,uvs,triangles)
        grass.reparentTo(self.static); grass.setColor(.32,.42,.17,1); grass.setTwoSided(True)

    def _flowerbeds(self):
        rng=random.Random(42)
        for x,y in ((8,8),(22,22),(-6.5,34),(36.5,-4)):
            self.box((x,y,.15),(2.7,1.5,.30),(.52,.51,.44),tex='concrete')
            self.box((x,y,.31),(2.43,1.23,.045),(.20,.15,.10))
            for i in range(15):
                fx,fy=x+rng.uniform(-1.1,1.1),y+rng.uniform(-.48,.48)
                h=rng.uniform(.40,.68)
                self.pole((fx,fy,.32),(fx,fy,h),.014,(.25,.38,.16))
                self.place(self.bud,(fx,fy,h-.10),(.10,.05,.05),(.26,.39,.16))
                tint=(.72,.52,.32) if i%3==0 else ((.64,.38,.53) if i%3==1 else (.84,.81,.64))
                for j in range(5):
                    a=j*math.tau/5
                    self.place(self.bud,(fx+math.cos(a)*.045,fy+math.sin(a)*.045,h),(.045,.045,.025),tint)
                self.place(self.bud,(fx,fy,h+.015),(.025,.025,.022),(.83,.66,.27))

    def _bin(self,x,y):
        self.place(self.cylinder,(x,y,.05),(.28,.28,.70),(.22,.29,.28),material='metal')
        self.place(self.cylinder,(x,y,.75),(.31,.31,.07),(.32,.37,.35),material='metal')
        self.place(self.cylinder,(x,y,.83),(.19,.19,.012),(.07,.09,.09))
        for i in range(12):
            a=i*math.tau/12
            self.box((x+math.cos(a)*.28,y+math.sin(a)*.28,.39),(.035,.035,.61),(.39,.44,.41),material='metal')

    def _bike_rack(self,x,y):
        for offset in (-.6,0,.6):
            previous=None
            points=[(x+offset,y-.30,.05),(x+offset,y-.30,.56)]
            points.extend((x+offset,y+math.cos(a)*.30,.56+math.sin(a)*.30) for a in [math.pi-j*math.pi/12 for j in range(13)])
            points.append((x+offset,y+.30,.05))
            for point in points:
                if previous:
                    self.pole(previous,point,.025,(.44,.50,.51),material='metal')
                previous=point

    def _drain(self,x,y):
        self.box((x,y,.096),(.75,.49,.02),(.22,.25,.25),material='metal')
        for i in range(9):
            self.box((x-.31+i*.077,y,.109),(.026,.39,.013),(.07,.09,.10))
        for dx in (-.32,.32):
            for dy in (-.18,.18):
                self.place(self.cylinder,(x+dx,y+dy,.113),(.018,.018,.008),(.48,.52,.53),material='metal')

    def _sign(self,x,y,title,subtitle):
        self.pole((x,y,0),(x,y,1.8),.035,(.35,.39,.37),material='metal')
        self.box((x,y,1.7),(1.5,.09,.48),(.18,.28,.26))
        for text,z,scale,color in ((title,1.77,.105,(.90,.92,.86,1)),(subtitle,1.60,.07,(.67,.76,.68,1))):
            node=TextNode('park-sign'); node.setText(text); node.setAlign(TextNode.ACenter); node.setTextColor(*color)
            label=self.static.attachNewNode(node); label.setPos(x,y-.052,z); label.setScale(scale)
