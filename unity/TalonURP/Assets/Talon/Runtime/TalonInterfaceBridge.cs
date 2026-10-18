#if UNITY_WEBGL && !UNITY_EDITOR
using System;
using System.Runtime.InteropServices;
using UnityEngine;
using UnityEngine.Scripting;

namespace Talon
{
    [Preserve]
    public sealed class TalonInterfaceBridge : MonoBehaviour
    {
        [Serializable] sealed class HostEvent
        {public string session,type,id,captureId;public float seconds;}
        [Serializable] sealed class Envelope
        {public string session;}
        [Serializable] sealed class Snapshot
        {public string phase,level;public float x,y;public int moves;}
        [DllImport("__Internal")] static extern void TalonHostEvent(string json);
        [DllImport("__Internal")] static extern string TalonHostSession();
        public static TalonInterfaceBridge Current { get; private set; }
        string session;
        TalonApp app;
        void Awake()
        {
            Current=this;gameObject.name="TalonInterfaceBridge";app=GetComponent<TalonApp>();
            session=TalonHostSession();WebGLInput.captureAllKeyboardInput=false;Send("ready");
        }
        [Preserve] public void Initialize(string id)
        {
            session=id;
            // Let form fields and Interface buttons retain keyboard input.
            WebGLInput.captureAllKeyboardInput=false;
            Send("ready");
        }
        public void Send(string type,string id=null,string capture=null,float seconds=0)
        {
            if(string.IsNullOrEmpty(session))return;
            TalonHostEvent(JsonUtility.ToJson(new HostEvent{session=session,type=type,id=id,captureId=capture,seconds=seconds}));
        }
        [Preserve] public void ReceiveJson(string json)
        {
            try
            {
                if(JsonUtility.FromJson<Envelope>(json)?.session!=session)return;
                app.Eeg.Accept(JsonUtility.FromJson<EegLink.Reply>(json));
            }
            catch(ArgumentException){Debug.LogWarning("Invalid Interface EEG message.");}
        }
        [Preserve] public void Suspend(){app.SuspendInput();}
        [Preserve] public void GetSnapshot()
        {
            TalonHostEvent(JsonUtility.ToJson(new HostEvent{session=session,type="snapshot",id=JsonUtility.ToJson(new Snapshot{
                phase=app.Facade.Phase.ToString(),level=app.Level.ToString(),x=app.Facade.Position.x,y=app.Facade.Position.y,moves=app.Facade.Moves})}));
        }
        public void RequestExit(){Send("exit");}
        void OnDestroy(){if(Current==this)Current=null;}
    }
}
#endif
