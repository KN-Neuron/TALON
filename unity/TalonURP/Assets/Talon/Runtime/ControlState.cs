using UnityEngine;
namespace Talon
{
    public sealed class ControlState
    {
        public bool Armed {get;private set;}
        public string Last {get;private set;}="—";
        public string Source {get;private set;}="Oczekiwanie";
        Vector4 pulse;
        double expires,manualAt=double.NegativeInfinity;
        public static float Scale(float value)
        {
            float v=Mathf.Abs(value);
            return v<.12f?0:Mathf.Sign(value)*Mathf.Clamp01((v-.12f)/.88f)*60;
        }
        public void Toggle(){Armed=!Armed;Stop();}
        public void Disarm(){Armed=false;Stop();}
        public void Stop(){pulse=Vector4.zero;expires=0;}
        public bool Fire(string command,double now)
        {
            if(command=="stop"){Stop();Last="stop";return true;}
            Vector4 ch;
            switch(command)
            {
                case "up":ch=new Vector4(0,0,40,0);break;
                case "down":ch=new Vector4(0,0,-40,0);break;
                case "forward":ch=new Vector4(0,40,0,0);break;
                case "rotate_right":ch=new Vector4(0,0,0,40);break;
                default:return false;
            }
            Last=Armed?command:command+" (BCI wyłączone)";
            if(!Armed)return false;
            pulse=ch;expires=now+1;return true;
        }
        public Vector4 Mix(Vector4 pad,Vector4 keyboard,double now)
        {
            Vector4 manual=pad.sqrMagnitude>.001f?pad:keyboard;
            if(manual.sqrMagnitude>.001f)
            {
                manualAt=now;Stop();Source=pad.sqrMagnitude>.001f?"Pad":"Klawiatura";return manual;
            }
            if(now-manualAt<1.5){Stop();Source="Pierwszeństwo ręczne";return Vector4.zero;}
            if(now<expires&&Armed){Source="BCI";return pulse;}
            Source="Oczekiwanie";return Vector4.zero;
        }
    }
}
