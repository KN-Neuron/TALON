using System;
using System.Collections.Generic;
using UnityEngine;

namespace Talon
{
    [Serializable]
    public struct Gate
    {
        public float x, z, bottom;
        public bool spansX;
        public Gate(float x, float z, bool spansX, float bottom)
        { this.x=x; this.z=z; this.spansX=spansX; this.bottom=bottom; }
    }

    public static class Course
    {
        public const float Width=7, Height=3.5f, Post=.4f;
        public static readonly Gate[] Gates={
            new Gate(0,10,true,0), new Gate(0,20,true,3),
            new Gate(10,30,false,3), new Gate(20,30,false,0),
            new Gate(30,20,true,0), new Gate(30,10,true,3),
            new Gate(20,0,false,0), new Gate(10,0,false,0)};

        public static IEnumerable<Bounds> Frame(Gate g)
        {
            float top=g.bottom+Height, hw=Width/2, p=Post;
            yield return Box(g,-hw-p,-hw,0,top+p);
            yield return Box(g,hw,hw+p,0,top+p);
            yield return Box(g,-hw,hw,top,top+p);
            if(g.bottom>0) yield return Box(g,-hw,hw,0,g.bottom);
        }
        static Bounds Box(Gate g,float u0,float u1,float lo,float hi)
        {
            return g.spansX ? new Bounds(new Vector3(g.x+(u0+u1)/2,(lo+hi)/2,g.z),new Vector3(u1-u0,hi-lo,Post))
                : new Bounds(new Vector3(g.x,(lo+hi)/2,g.z+(u0+u1)/2),new Vector3(Post,hi-lo,u1-u0));
        }
    }

    // Port of sim.py: velocity control, altitude hold and forgiving collisions.
    // A fixed timestep drives this model independently of rendering frame rate.
    public sealed class FlightModel
    {
        public Vector3 Position, Velocity;
        public float Yaw, HoverAltitude;
        public Vector4 Channels;
        public bool Flying, Touching;
        public bool TrackProgress=true;
        public int NextGate, Laps;
        public string State="Na ziemi";
        public readonly List<Bounds> Obstacles=new List<Bounds>();
        public readonly Gate[] Gates;
        float fallSpeed=.8f;
        public FlightModel(Gate[] gates=null)
        {
            Gates=gates??Course.Gates;
            foreach(var gate in Gates) Obstacles.AddRange(Course.Frame(gate));
        }
        public void Takeoff()
        {
            if(Flying||Position.y>.05f)return;
            Flying=true; HoverAltitude=1.2f; fallSpeed=.8f; Channels=Vector4.zero; State="Startowanie";
        }
        public void Land(){ Flying=false; HoverAltitude=0; fallSpeed=.8f; Channels=Vector4.zero; State="Lądowanie"; }
        public void Emergency(){ Flying=false; HoverAltitude=0; fallSpeed=6; Channels=Vector4.zero; State="Silniki wyłączone"; }
        public bool Hits(Vector3 pos)
        {
            foreach(var raw in Obstacles)
            {
                var b=raw; b.Expand(new Vector3(.7f,.2f,.7f));
                if(b.Contains(pos))return true;
            }
            return false;
        }
        public void Step(float dt)
        {
            Vector3 target;
            if(!Flying) target=new Vector3(0,Position.y>0?-fallSpeed:0,0);
            else
            {
                Yaw=Mathf.Repeat(Yaw+Channels.w*.9f*dt,360);
                var rotation=Quaternion.Euler(0,Yaw,0);
                target=rotation*new Vector3(Channels.x*.03f,0,Channels.y*.03f);
                target.y=Channels.z*.015f;
                if(Mathf.Abs(Channels.z)>.001f) HoverAltitude=Position.y;
                else
                {
                    float gap=HoverAltitude-Position.y;
                    target.y=Mathf.Clamp(gap*2,-1.5f,1.5f);
                    if(Mathf.Abs(gap)<.05f&&State=="Startowanie") State="W locie";
                }
            }
            Vector3 old=Position;
            Velocity=Vector3.Lerp(Velocity,target,Mathf.Min(1,3*dt));
            Position+=Velocity*dt;
            Touching=Flying&&Hits(Position);
            if(Touching)
            {
                Position=new Vector3(old.x,Position.y,old.z); Velocity.x=Velocity.z=0;
                if(Hits(Position)){Position.y=old.y;Velocity.y=0;}
            }
            if(Flying&&TrackProgress&&Gates.Length>0)
            {
                var g=Gates[NextGate];
                float before=g.spansX?old.z:old.x, after=g.spansX?Position.z:Position.x;
                float centre=g.spansX?g.z:g.x, across=g.spansX?Position.x-g.x:Position.z-g.z;
                if((before<centre)!=(after<centre)&&Mathf.Abs(across)<Course.Width/2&&Position.y>g.bottom&&Position.y<g.bottom+Course.Height)
                {NextGate=(NextGate+1)%Gates.Length;if(NextGate==0)Laps++;}
            }
            if(Position.y<=0)
            {
                Position.y=Velocity.y=0;
                if(!Flying){Velocity=Vector3.zero;if(State=="Lądowanie")State="Na ziemi";}
            }
        }
    }
}
