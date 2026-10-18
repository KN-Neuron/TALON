using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace Talon
{
    public sealed class CampusWorld
    {
        public readonly List<Bounds> Obstacles=new List<Bounds>();
        public readonly Renderer[] GateStrips=new Renderer[8];
        public Transform Drone;
        public readonly List<Transform> Rotors=new List<Transform>();
        readonly Transform root;
        readonly System.Random rng=new System.Random(71);
        readonly Material grass,road,concrete,wood,metal,glass,bark,dark,paint;
        readonly Material[] leaves=new Material[3];
        Mesh card;
        readonly List<Object> resources=new List<Object>();
        float R(float min,float max)=>(float)(min+rng.NextDouble()*(max-min));
        public CampusWorld(Transform parent)
        {
            root=new GameObject("Campus · KN Interface").transform;root.SetParent(parent,false);
            grass=Mat("Grass",new Color(.34f,.43f,.21f),0,.15f,Surface("grass"));
            road=Mat("Asphalt",new Color(.48f,.49f,.50f),0,.15f,Surface("road"));
            concrete=Mat("Concrete",new Color(.66f,.65f,.58f),0,.25f,Surface("concrete"));
            wood=Mat("Timber",new Color(.57f,.39f,.22f),0,.35f,Surface("wood"));
            metal=Mat("Brushed metal",new Color(.31f,.36f,.36f),.75f,.65f);
            glass=Mat("Sky glass",new Color(.26f,.41f,.49f),.65f,.88f);
            bark=Mat("Bark",new Color(.39f,.31f,.22f),0,.15f,Surface("wood"));
            dark=Mat("Carbon",new Color(.07f,.09f,.10f),.3f,.45f);
            paint=Mat("Ivory paint",new Color(.82f,.83f,.75f),.12f,.4f);
            Texture2D canopy=LeafTexture();
            for(int i=0;i<3;i++)
            {
                leaves[i]=Mat("Canopy "+i,new Color(1,i==2?.89f:1,i==2?.7f:1),0,.15f,canopy,true);
            }
            card=new Mesh{name="Leaf card"};resources.Add(card);
            card.vertices=new[]{new Vector3(-1,-1,0),new Vector3(1,-1,0),new Vector3(1,1,0),new Vector3(-1,1,0)};
            card.uv=new[]{new Vector2(0,0),new Vector2(1,0),new Vector2(1,1),new Vector2(0,1)};
            card.triangles=new[]{0,2,1,0,3,2};card.RecalculateNormals();card.RecalculateBounds();
            Ground();Buildings();Trees();Details();Gates();BuildDrone(parent);
            StaticBatchingUtility.Combine(root.gameObject);
        }
        Material Mat(string name,Color color,float metallic=0,float smoothness=.3f,Texture2D texture=null,bool clip=false)
        {
            var seed=Resources.Load<Material>(clip?"Talon/Leaves":"Talon/Lit");
            var m=seed!=null?new Material(seed):new Material(Shader.Find("Universal Render Pipeline/Lit"));
            m.name=name;m.color=color;m.SetFloat("_Metallic",metallic);m.SetFloat("_Smoothness",smoothness);m.enableInstancing=true;
            if(texture)m.SetTexture("_BaseMap",texture);
            if(clip){m.SetFloat("_AlphaClip",1);m.SetFloat("_Cutoff",.45f);m.SetFloat("_Cull",0);m.EnableKeyword("_ALPHATEST_ON");m.renderQueue=2450;}
            resources.Add(m);return m;
        }
        GameObject Shape(PrimitiveType type,string name,Vector3 pos,Vector3 scale,Material material,Transform parent=null)
        {
            var go=GameObject.CreatePrimitive(type);go.name=name;go.transform.SetParent(parent?parent:root,false);
            go.transform.localPosition=pos;go.transform.localScale=scale;
            Object.DestroyImmediate(go.GetComponent<Collider>());
            go.GetComponent<Renderer>().sharedMaterial=material;
            return go;
        }
        GameObject Box(string name,Vector3 pos,Vector3 scale,Material mat,Transform parent=null)=>Shape(PrimitiveType.Cube,name,pos,scale,mat,parent);
        void Beam(string name,Vector3 a,Vector3 b,float radius,Material mat,Transform parent=null)
        {
            var go=Shape(PrimitiveType.Cylinder,name,(a+b)/2,new Vector3(radius*2,Vector3.Distance(a,b)/2,radius*2),mat,parent);
            go.transform.localRotation=Quaternion.FromToRotation(Vector3.up,(b-a).normalized);
        }
        Texture2D Surface(string kind)
        {
            const int n=128;var t=new Texture2D(n,n,TextureFormat.RGB24,true){name=kind,wrapMode=TextureWrapMode.Repeat,anisoLevel=8};
            var pixels=new Color[n*n];
            for(int y=0;y<n;y++)for(int x=0;x<n;x++)
            {
                float noise=R(-.05f,.05f), v=.85f+noise;
                if(kind=="grass")v+=Mathf.PerlinNoise(x*.08f,y*.08f)*.25f;
                if(kind=="wood")v+=Mathf.Sin(y*.5f+Mathf.Sin(x*.06f)*2)*.06f;
                if(kind=="concrete"&&(x%32<1||y%32<1))v-=.16f;
                pixels[y*n+x]=new Color(v,v,v);
            }
            t.SetPixels(pixels);t.Apply(true,true);resources.Add(t);return t;
        }
        Texture2D LeafTexture()
        {
            const int n=256;var t=new Texture2D(n,n,TextureFormat.RGBA32,true){name="Oak canopy",wrapMode=TextureWrapMode.Clamp,anisoLevel=4};
            var px=new Color[n*n];
            for(int leaf=0;leaf<230;leaf++)
            {
                float cx=R(22,234),cy=R(22,234);if(new Vector2(cx-128,cy-128).sqrMagnitude>112*112)continue;
                float rx=R(6,13),ry=R(3,6),a=R(0,Mathf.PI*2),co=Mathf.Cos(a),si=Mathf.Sin(a),tint=R(.7f,1.2f);
                for(int y=Mathf.Max(0,(int)cy-15);y<Mathf.Min(n,(int)cy+15);y++)for(int x=Mathf.Max(0,(int)cx-15);x<Mathf.Min(n,(int)cx+15);x++)
                {
                    float dx=x-cx,dy=y-cy,u=dx*co+dy*si,v=-dx*si+dy*co;
                    if(u*u/(rx*rx)+v*v/(ry*ry)<1)px[y*n+x]=new Color(.39f*tint,.53f*tint,.21f*tint,1);
                }
            }
            t.SetPixels(px);t.Apply(true,true);resources.Add(t);return t;
        }
        void Ground()
        {
            var soil=Box("Lawn",new Vector3(15,-.14f,15),new Vector3(220,.25f,220),grass);
            var mat=new Material(grass);resources.Add(mat);mat.mainTextureScale=Vector2.one*80;soil.GetComponent<Renderer>().sharedMaterial=mat;
            Path(new Vector3(0,.025f,13),new Vector3(7.8f,.07f,64));
            Path(new Vector3(30,.026f,15),new Vector3(7.8f,.07f,38));
            Path(new Vector3(15,.027f,30),new Vector3(38,.07f,7.8f));
            Path(new Vector3(15,.028f,0),new Vector3(38,.07f,7.8f));
            Box("Launch pad",new Vector3(0,.085f,-2),new Vector3(3.3f,.05f,3.3f),dark);
            var marker=Mat("Launch marking",new Color(.89f,.72f,.28f));
            Box("H cross",new Vector3(0,.116f,-2),new Vector3(1.8f,.01f,.14f),marker);
            foreach(float x in new[]{-.85f,.85f})Box("H upright",new Vector3(x,.116f,-2),new Vector3(.14f,.01f,1.8f),marker);
        }
        void Path(Vector3 pos,Vector3 size)
        {
            Box("Concrete verge",pos-Vector3.up*.035f,size+new Vector3(.4f,.03f,.4f),concrete);
            var surface=new Material(road);resources.Add(surface);surface.mainTextureScale=new Vector2(size.x/2,size.z/2);
            Box("Park path",pos,size,surface);
        }
        void Buildings()
        {
            float[,] buildings={{-26,18,18,37,12},{54,18,21,40,16},{14,62,57,17,11},{-29,-23,24,16,8}};
            for(int i=0;i<4;i++)
            {
                float x=buildings[i,0],z=buildings[i,1],w=buildings[i,2],d=buildings[i,3],h=buildings[i,4];
                var bounds=new Bounds(new Vector3(x,h/2,z),new Vector3(w,h,d));Obstacles.Add(bounds);
                Box("Campus building",bounds.center,bounds.size,concrete);
                Box("Roof parapet",new Vector3(x,h,z),new Vector3(w+.3f,.25f,d+.3f),metal);
                for(float y=2.4f;y<h-1;y+=3.2f)foreach(float side in new[]{-1f,1f})
                {
                    Box("Glass facade",new Vector3(x,y,z+side*(d/2+.03f)),new Vector3(w-.8f,1.8f,.08f),glass);
                    Box("Glass facade",new Vector3(x+side*(w/2+.03f),y,z),new Vector3(.08f,1.8f,d-.8f),glass);
                    for(float u=-w/2+.8f;u<w/2;u+=1.25f)Box("Window mullion",new Vector3(x+u,y,z+side*(d/2+.09f)),new Vector3(.055f,1.8f,.08f),paint);
                    for(float u=-d/2+.8f;u<d/2;u+=1.25f)Box("Window mullion",new Vector3(x+side*(w/2+.09f),y,z+u),new Vector3(.08f,1.8f,.055f),paint);
                }
                Box("Entrance canopy",new Vector3(x,3.1f,z-d/2-1.1f),new Vector3(6,.18f,3),metal);
                foreach(float dx in new[]{-2.7f,2.7f})Beam("Canopy support",new Vector3(x+dx,0,z-d/2-2.2f),new Vector3(x+dx,3.1f,z-d/2-2.2f),.055f,metal);
                Box("Entrance",new Vector3(x,1.35f,z-d/2-.07f),new Vector3(3,2.7f,.12f),glass);
                Box("Entry paving",new Vector3(x,.035f,z-d/2-2),new Vector3(8,.08f,4),concrete);
                foreach(float dx in new[]{-w/4,w/4})Box("Roof ventilation",new Vector3(x+dx,h+.55f,z),new Vector3(2.7f,.8f,3),metal);
            }
        }
        void Trees()
        {
            var points=new List<Vector2>();
            for(int z=-12;z<52;z+=9)points.Add(new Vector2(-10,z));
            for(int z=-9;z<51;z+=10)points.Add(new Vector2(40,z));
            for(int x=-4;x<35;x+=9)points.Add(new Vector2(x,43));
            for(int x=4;x<36;x+=10)points.Add(new Vector2(x,-11));
            foreach(float x in new[]{10f,21f})foreach(float z in new[]{10f,21f})points.Add(new Vector2(x,z));
            int species=0;
            foreach(var point in points)
            {
                float x=point.x+R(-1,1),z=point.y+R(-1,1),height=R(7,11),trunk=height*.56f;
                Beam("Oak trunk",new Vector3(x,0,z),new Vector3(x+.15f,trunk,z),.25f,bark);
                Obstacles.Add(new Bounds(new Vector3(x,trunk/2,z),new Vector3(.7f,trunk,.7f)));
                for(int branch=0;branch<7;branch++)
                {
                    float a=branch*2.4f;
                    var centre=new Vector3(x+Mathf.Cos(a)*1.3f,trunk+R(0,1.5f),z+Mathf.Sin(a)*1.3f);
                    if(branch<4)Beam("Oak branch",new Vector3(x,trunk*.65f,z),centre,.085f,bark);
                    for(int j=0;j<4;j++)
                    {
                        var leaf=new GameObject("Canopy leaves");leaf.transform.SetParent(root,false);
                        leaf.transform.localPosition=centre+new Vector3(R(-.4f,.4f),R(-.3f,.6f),R(-.4f,.4f));
                        leaf.transform.localRotation=Quaternion.Euler(R(-45,45),R(0,360),R(-35,35));leaf.transform.localScale=Vector3.one*R(1.7f,2.4f);
                        leaf.AddComponent<MeshFilter>().sharedMesh=card;
                        leaf.AddComponent<MeshRenderer>().sharedMaterial=leaves[species%3];
                    }
                }
                species++;
            }
        }
        void Details()
        {
            foreach(float x in new[]{-4.8f,34.8f})for(int z=-8;z<=44;z+=13)
            {
                Beam("Bollard",new Vector3(x,0,z),new Vector3(x,.82f,z),.065f,metal);
                Box("Lamp diffuser",new Vector3(x,.94f,z),new Vector3(.19f,.22f,.19f),paint);
                Box("Lamp cap",new Vector3(x,1.07f,z),new Vector3(.23f,.04f,.23f),metal);
            }
            foreach(var p in new[]{new Vector2(8,7),new Vector2(23,24),new Vector2(-7,29),new Vector2(37,7)})
            {
                for(int i=0;i<4;i++)
                {
                    Box("Bench seat",new Vector3(p.x,.48f,p.y+i*.13f),new Vector3(2,.08f,.1f),wood);
                    Box("Bench back",new Vector3(p.x,.66f+i*.13f,p.y+.48f),new Vector3(2,.10f,.08f),wood);
                }
                foreach(float dx in new[]{-.75f,.75f})Box("Bench feet",new Vector3(p.x+dx,.23f,p.y+.23f),new Vector3(.08f,.46f,.46f),metal);
            }
            foreach(var p in new[]{new Vector2(8,8),new Vector2(22,22),new Vector2(-6,34),new Vector2(36,-4)})
            {
                Box("Planter",new Vector3(p.x,.14f,p.y),new Vector3(2.5f,.28f,1.4f),concrete);
                for(int i=0;i<8;i++)Shape(PrimitiveType.Sphere,"Plant",new Vector3(p.x+R(-1,1),.4f,p.y+R(-.4f,.4f)),new Vector3(.35f,.40f,.35f),grass);
            }
            foreach(float z in new[]{6f,24f})
            {
                Shape(PrimitiveType.Cylinder,"Litter bin",new Vector3(-5.7f,.35f,z),new Vector3(.52f,.35f,.52f),metal);
                Shape(PrimitiveType.Cylinder,"Bin lid",new Vector3(-5.7f,.73f,z),new Vector3(.60f,.035f,.60f),dark);
            }
        }
        void Gates()
        {
            for(int i=0;i<Course.Gates.Length;i++)
            {
                var g=Course.Gates[i];foreach(var bounds in Course.Frame(g))Box("Gate "+(i+1),bounds.center,bounds.size,paint);
                var strip=Mat("Gate light "+i,new Color(.12f,.72f,.52f),.1f,.45f);
                strip.EnableKeyword("_EMISSION");strip.SetColor("_EmissionColor",new Color(.05f,.65f,.34f));
                Vector3 centre=new Vector3(g.x,g.bottom+Course.Height+.08f,g.z);
                var go=Box("Gate progress light",centre,g.spansX?new Vector3(7,.09f,.43f):new Vector3(.43f,.09f,7),strip);
                GateStrips[i]=go.GetComponent<Renderer>();
                foreach(float side in new[]{-1f,1f})
                {
                    var position=g.spansX?new Vector3(g.x+side*(Course.Width/2+.08f),g.bottom+Course.Height/2,g.z-.24f)
                        :new Vector3(g.x-.24f,g.bottom+Course.Height/2,g.z+side*(Course.Width/2+.08f));
                    Box("Gate vertical light",position,new Vector3(.09f,Course.Height,.09f),strip);
                }
            }
        }
        public void SetVisible(bool visible){root.gameObject.SetActive(visible);}
        public void SetLevel(bool challenge)
        {
            foreach(var strip in GateStrips)
            {
                strip.sharedMaterial.color=challenge?new Color(.16f,.65f,.48f):new Color(.50f,.55f,.48f);
                strip.sharedMaterial.SetColor("_EmissionColor",new Color(.08f,.11f,.10f));
            }
        }
        void BuildDrone(Transform parent)
        {
            Drone=new GameObject("TALON · Quadcopter").transform;Drone.SetParent(parent,false);
            Box("Carbon frame",new Vector3(0,.15f,0),new Vector3(.34f,.15f,.48f),dark,Drone);
            Box("Battery",new Vector3(0,.26f,-.04f),new Vector3(.20f,.13f,.30f),metal,Drone);
            Box("Camera",new Vector3(0,.18f,.28f),new Vector3(.22f,.20f,.13f),dark,Drone);
            Shape(PrimitiveType.Sphere,"Lens",new Vector3(0,.18f,.35f),new Vector3(.10f,.10f,.04f),glass,Drone);
            foreach(float x in new[]{-.43f,.43f})foreach(float z in new[]{-.40f,.40f})
            {
                Beam("Arm",new Vector3(0,.10f,0),new Vector3(x,.10f,z),.033f,dark,Drone);
                Shape(PrimitiveType.Cylinder,"Motor",new Vector3(x,.16f,z),new Vector3(.14f,.055f,.14f),metal,Drone);
                var rotor=new GameObject("Rotor").transform;rotor.SetParent(Drone,false);rotor.localPosition=new Vector3(x,.23f,z);
                Box("Propeller",Vector3.zero,new Vector3(.46f,.012f,.035f),dark,rotor);
                Box("Propeller",Vector3.zero,new Vector3(.035f,.012f,.46f),dark,rotor);Rotors.Add(rotor);
            }
        }
        public void Dispose()
        {
            foreach(var resource in resources)if(resource)Object.DestroyImmediate(resource);
        }
    }
}
