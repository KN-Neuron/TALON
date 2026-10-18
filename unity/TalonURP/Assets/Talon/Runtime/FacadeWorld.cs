using System.Collections.Generic;
using UnityEngine;

namespace Talon
{
    // A separate straight-on facade, while the free-flight campus is preserved.
    public sealed class FacadeWorld
    {
        readonly GameObject root;
        readonly List<Material> materials=new List<Material>();
        public FacadeWorld(Transform parent)
        {
            root=new GameObject("Level 02 · Facade ascent");root.transform.SetParent(parent,false);
            Material wall=Mat(new Color(.64f,.64f,.59f),.15f),trim=Mat(new Color(.31f,.36f,.38f),.4f);
            Material glass=Mat(new Color(.20f,.35f,.43f),.85f),obstacle=Mat(new Color(.54f,.37f,.22f),.35f);
            Material green=Mat(new Color(.16f,.62f,.41f),.4f),dark=Mat(new Color(.10f,.14f,.17f),.25f);
            Box("Building",new Vector3(0,6.35f,7),new Vector3(14,12.7f,10),wall);
            Box("Roof rim",new Vector3(0,12.8f,6.9f),new Vector3(14.6f,.24f,10.6f),trim);
            Box("Roof destination",new Vector3(0,13.12f,1.6f),new Vector3(11,.12f,.3f),green);
            for(int row=0;row<5;row++)for(int col=0;col<6;col++)
            {
                float x=-5.7f+col*2.28f,y=1.4f+row*2.35f;
                Box("Window recess",new Vector3(x,y,1.96f),new Vector3(1.5f,1.5f,.08f),trim);
                Box("Window glass",new Vector3(x,y,1.90f),new Vector3(1.3f,1.28f,.04f),glass);
                Box("Window divider",new Vector3(x,y,1.86f),new Vector3(.045f,1.3f,.04f),trim);
            }
            foreach(var rect in FacadeSession.Obstacles)
            {
                Box("Balcony / obstacle",new Vector3(rect.center.x,rect.center.y,.85f),new Vector3(rect.width,rect.height,2.5f),obstacle);
                Box("Obstacle front lip",new Vector3(rect.center.x,rect.center.y+.12f,-.42f),new Vector3(rect.width,.15f,.12f),trim);
                for(float x=rect.xMin+.3f;x<rect.xMax;x+=.65f)
                    Box("Obstacle caution stripe",new Vector3(x,rect.center.y,-.48f),new Vector3(.22f,.20f,.02f),dark);
            }
            Box("Courtyard",new Vector3(0,-.2f,3),new Vector3(60,.3f,45),wall);
            Box("Launch platform",new Vector3(0,.1f,0),new Vector3(2.5f,.2f,2),trim);
            foreach(float x in new[]{-6.5f,6.5f})Box("Facade side column",new Vector3(x,6.3f,1.8f),new Vector3(.18f,12.6f,.25f),trim);
            StaticBatchingUtility.Combine(root);
        }
        Material Mat(Color color,float smoothness)
        {
            var seed=Resources.Load<Material>("Talon/Lit");var mat=new Material(seed){color=color,enableInstancing=true};
            mat.SetFloat("_Smoothness",smoothness);materials.Add(mat);return mat;
        }
        void Box(string name,Vector3 position,Vector3 size,Material mat)
        {
            var go=GameObject.CreatePrimitive(PrimitiveType.Cube);go.name=name;go.transform.SetParent(root.transform,false);
            go.transform.localPosition=position;go.transform.localScale=size;Object.DestroyImmediate(go.GetComponent<Collider>());
            go.GetComponent<Renderer>().sharedMaterial=mat;
        }
        public void SetActive(bool active){root.SetActive(active);}
        public void Dispose(){if(root)Object.DestroyImmediate(root);foreach(var mat in materials)Object.DestroyImmediate(mat);}
    }
}
