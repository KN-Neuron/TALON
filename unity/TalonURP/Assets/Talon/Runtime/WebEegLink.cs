#if UNITY_WEBGL && !UNITY_EDITOR
using System;
using UnityEngine;

namespace Talon
{
    // The host owns hardware and FBCCA. Unity owns stimulus and movement timing.
    public sealed class EegLink : IDisposable
    {
        [Serializable] public sealed class Reply
        {
            public string type, id, direction, error, status;
            public bool ok, simulated;
            public float sampleRateHz, winnerHz;
        }
        int sequence;
        string connectId, beginId, classifyId, captureId;
        double deadline;
        public bool Connected { get; private set; }
        public bool Connecting => connectId != null;
        public bool Simulated { get; private set; }
        public string Status { get; private set; } = "Połącz urządzenie w zakładce Device w Interface.";
        public string LastDecision { get; private set; } = "Brak decyzji EEG";
        public event Action CaptureReady;
        public event Action<MoveDirection> Decision;
        public event Action<string> Failed;
        string NextId() => (++sequence).ToString();
        void Send(string type, string id = null, string capture = null, float seconds = 0)
        {
            TalonInterfaceBridge.Current?.Send(type, id, capture, seconds);
        }
        public void Connect()
        {
            if(Connected || Connecting)return;
            connectId=NextId();deadline=Time.realtimeSinceStartupAsDouble+40;
            Status="Oczekiwanie na EEG z Interface…";Send("connect",connectId);
        }
        public void Begin()
        {
            if(!Connected){Error("Połącz EEG w Interface.");return;}
            Cancel();beginId=NextId();captureId=beginId;
            deadline=Time.realtimeSinceStartupAsDouble+5;Send("begin",beginId,captureId);
        }
        public void Classify(float seconds)
        {
            classifyId=NextId();deadline=Time.realtimeSinceStartupAsDouble+20;
            Send("classify",classifyId,captureId,seconds);
        }
        public void Cancel()
        {
            beginId=classifyId=captureId=null;Send("cancel");
        }
        public void Accept(Reply reply)
        {
            if(reply == null)return;
            if(reply.type=="lost")
            {Connected=false;connectId=null;Error(reply.error);return;}
            if(reply.id==connectId && connectId!=null)
            {
                connectId=null;
                if(!reply.ok){Error(reply.error);return;}
                Connected=true;Simulated=reply.simulated;
                Status=reply.status ?? (Simulated?"TEST: syntetyczne EEG":"EEG z Interface");
            }
            else if(reply.id==beginId && beginId!=null)
            {
                beginId=null;
                if(!reply.ok){Error(reply.error);return;}
                CaptureReady?.Invoke();
            }
            else if(reply.id==classifyId && classifyId!=null)
            {
                classifyId=captureId=null;
                if(!reply.ok){Error(reply.error);return;}
                if(!Enum.TryParse(reply.direction,true,out MoveDirection direction) || direction==MoveDirection.None || !Enum.IsDefined(typeof(MoveDirection),direction))
                {Error("Nieznany kierunek FBCCA.");return;}
                LastDecision=$"FBCCA: {FacadeSession.Name(direction)} · {reply.winnerHz:0.00} Hz";
                Decision?.Invoke(direction);
            }
        }
        public void Poll()
        {
            if((connectId!=null||beginId!=null||classifyId!=null)&&Time.realtimeSinceStartupAsDouble>deadline)
            {Connected=false;connectId=null;Error("Przekroczono czas oczekiwania na Interface.");}
        }
        void Error(string error)
        {Cancel();Status=error??"Błąd EEG";Failed?.Invoke(Status);}
        public void Disconnect()
        {Cancel();connectId=null;Connected=false;Send("disconnect");Status="EEG odłączone od modułu. Urządzeniem zarządza Interface.";}
        public void Dispose(){Disconnect();}
    }
}
#endif
