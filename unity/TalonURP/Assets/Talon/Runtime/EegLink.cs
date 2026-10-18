#if !UNITY_WEBGL || UNITY_EDITOR
using System;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.IO;
using UnityEngine;

namespace Talon
{
    // Owns only the subprocess launched for this TALON instance. Unity never
    // blocks on Bluetooth or FBCCA, and cancelled request IDs cannot move a drone.
    public sealed class EegLink : IDisposable
    {
        [Serializable] sealed class Reply
        {
            public string type,id,command,error,direction;
            public bool ok,simulated;
            public float sampleRateHz,winnerHz;
        }
        [Serializable] sealed class Request
        {public string id,command,captureId;public float seconds;}
        readonly ConcurrentQueue<string> inbox=new ConcurrentQueue<string>();
        Process process;
        string connectId,beginId,classifyId,captureId;
        int sequence,processGeneration;
        double deadline;
        public bool Connected {get;private set;}
        public bool Connecting=>connectId!=null;
        public bool Simulated {get;private set;}
        public string Status {get;private set;}="Czepek niepołączony";
        public string LastDecision {get;private set;}="Brak decyzji EEG";
        public event Action CaptureReady;
        public event Action<MoveDirection> Decision;
        public event Action<string> Failed;
        public void Connect()
        {
            if(Connected||Connecting)return;
            try
            {
                if(process==null||process.HasExited)
                {
                    DisposeProcess();
                    string config=Path.Combine(Path.GetDirectoryName(Application.dataPath),"eeg-launcher.txt");
                    if(!File.Exists(config))throw new IOException("Brak środowiska EEG. Uruchom unity/tools/Setup-EEG.ps1 w Windows.");
                    string[] lines=File.ReadAllLines(config);
                    if(lines.Length<2||!File.Exists(lines[0])||!File.Exists(lines[1]))
                        throw new IOException("Nie znaleziono Pythona EEG. Uruchom Setup-EEG.ps1.");
                    string args="-u \""+lines[1]+"\"";
                    if(Array.IndexOf(Environment.GetCommandLineArgs(),"--talon-eeg-simulate")>=0)args+=" --simulate";
                    process=new Process{StartInfo=new ProcessStartInfo(lines[0],args){UseShellExecute=false,
                        RedirectStandardInput=true,RedirectStandardOutput=true,RedirectStandardError=true,CreateNoWindow=true,
                        StandardOutputEncoding=System.Text.Encoding.UTF8,StandardErrorEncoding=System.Text.Encoding.UTF8}};
                    int generation=processGeneration;
                    process.OutputDataReceived+=(s,e)=>{if(e.Data!=null&&generation==processGeneration)inbox.Enqueue(e.Data);};
                    // Diagnostics are bounded by the OS pipe reader, never written to protocol stdout.
                    process.ErrorDataReceived+=(s,e)=>{if(e.Data!=null)UnityEngine.Debug.Log("TALON EEG: "+e.Data);};
                    process.StartInfo.EnvironmentVariables["PYTHONIOENCODING"]="utf-8";
                    process.Start();process.BeginOutputReadLine();process.BeginErrorReadLine();
                }
                Status="Wyszukiwanie BA MAXI 009…";connectId=Send("connect");
                deadline=Time.realtimeSinceStartupAsDouble+40;
            }
            catch(Exception e){Error(e.Message);}
        }
        string Send(string command,string capture=null,float seconds=0)
        {
            if(process==null||process.HasExited)throw new IOException("Proces EEG nie działa.");
            string id=(++sequence).ToString();
            process.StandardInput.WriteLine(JsonUtility.ToJson(new Request{id=id,command=command,captureId=capture,seconds=seconds}));
            process.StandardInput.Flush();return id;
        }
        public void Begin()
        {
            if(!Connected){Error("Najpierw połącz czepek EEG.");return;}
            Cancel();
            try{beginId=Send("begin");captureId=beginId;deadline=Time.realtimeSinceStartupAsDouble+5;}
            catch(Exception e){Error(e.Message);}
        }
        public void Classify(float seconds)
        {
            try{classifyId=Send("classify",captureId,seconds);deadline=Time.realtimeSinceStartupAsDouble+20;}
            catch(Exception e){Error(e.Message);}
        }
        public void Cancel()
        {
            beginId=classifyId=captureId=null;
            try{if(process!=null&&!process.HasExited)Send("cancel");}catch(Exception){}
        }
        public void Poll()
        {
            for(int i=0;i<64&&inbox.TryDequeue(out string line);i++)
            {
                Reply reply;
                try{reply=JsonUtility.FromJson<Reply>(line);}catch(ArgumentException){continue;}
                if(reply==null)continue;
                if(reply.type=="lost"){Connected=false;Error(reply.error);continue;}
                if(reply.type!="response")continue;
                if(reply.id==connectId)
                {
                    connectId=null;
                    if(!reply.ok){Error(reply.error);continue;}
                    Connected=true;Simulated=reply.simulated;
                    Status=Simulated?"TEST: syntetyczne EEG":$"BA MAXI 009 · {reply.sampleRateHz:0} Hz · 6 kanałów";
                }
                else if(reply.id==beginId)
                {
                    beginId=null;
                    if(!reply.ok){Error(reply.error);continue;}
                    CaptureReady?.Invoke();
                }
                else if(reply.id==classifyId)
                {
                    classifyId=captureId=null;
                    if(!reply.ok){Error(reply.error);continue;}
                    if(!Enum.TryParse(reply.direction,out MoveDirection direction)||direction==MoveDirection.None)
                    {Error("Klasyfikator zwrócił nieznany kierunek.");continue;}
                    LastDecision=$"FBCCA: {FacadeSession.Name(direction)} · {reply.winnerHz:0.00} Hz";
                    Decision?.Invoke(direction);
                }
            }
            if(process!=null&&process.HasExited&&(Connected||Connecting||beginId!=null||classifyId!=null))
            {Connected=false;Error("Proces EEG zakończył działanie. Połącz ponownie.");}
            if((connectId!=null||beginId!=null||classifyId!=null)&&Time.realtimeSinceStartupAsDouble>deadline)
            {
                Connected=false;Error("Przekroczono czas oczekiwania na EEG. Połącz ponownie.");DisposeProcess();
            }
        }
        void Error(string text)
        {Cancel();connectId=null;Status=text??"Błąd EEG";Failed?.Invoke(Status);}
        public void Disconnect()
        {Dispose();Status="Czepek rozłączony";LastDecision="Brak decyzji EEG";}
        void DisposeProcess()
        {
            processGeneration++;
            while(inbox.TryDequeue(out _)){}
            if(process==null)return;
            try
            {
                if(!process.HasExited)
                {
                    process.StandardInput.WriteLine("{\"command\":\"shutdown\"}");process.StandardInput.Flush();
                    // Never block Unity's render thread waiting for the SDK.
                    var owned=process;
                    System.Threading.Tasks.Task.Run(()=>{try{if(!owned.WaitForExit(5000))owned.Kill();}catch(Exception){}finally{owned.Dispose();}});
                }
                else process.Dispose();
            }
            catch(Exception){process.Dispose();}
            process=null;
        }
        public void Dispose(){Cancel();connectId=null;Connected=false;DisposeProcess();}
    }
}

#endif
