#if !UNITY_WEBGL || UNITY_EDITOR
using System;
using System.Net;
using System.Net.Sockets;
using System.Text;
using UnityEngine;

namespace Talon
{
    // Nonblocking and bounded: malformed/flooded UDP cannot block the flight loop.
    // Decoder messages retain the Python protocol: {"cmd":"forward"}.
    public sealed class BciLink : IDisposable
    {
        [Serializable] class Message {public string cmd;}
        public string Status {get;private set;}
        public int Port {get;}
        public int Accepted {get;private set;}
        public int Rejected {get;private set;}
        readonly UdpClient socket;
        public BciLink(int port=9001,bool allowRemote=false)
        {
            Port=port;
            try
            {
                socket=new UdpClient(new IPEndPoint(allowRemote?IPAddress.Any:IPAddress.Loopback,port));
                socket.Client.Blocking=false;
                Status=$"BCI UDP :{((IPEndPoint)socket.Client.LocalEndPoint).Port}";
            }
            catch(SocketException e){Status="BCI niedostępne: "+e.SocketErrorCode;socket?.Dispose();socket=null;}
        }
        public void Poll(ControlState controls,double now)
        {
            if(socket==null)return;
            for(int i=0;i<64;i++)
            {
                try
                {
                    if(socket.Available==0)break;
                    IPEndPoint peer=null;
                    byte[] data=socket.Receive(ref peer);
                    if(data.Length>256){Rejected++;continue;}
                    string text=new UTF8Encoding(false,true).GetString(data);
                    if(!text.TrimStart().StartsWith("{")){Rejected++;continue;}
                    var message=JsonUtility.FromJson<Message>(text);
                    bool accepted=message!=null&&controls.Fire(message.cmd,now);
                    if(accepted)Accepted++;else Rejected++;
                    // Optional acknowledgement lets a WSL decoder verify routing
                    // and arming without interpreting simulator pixels.
                    byte[] ack=Encoding.UTF8.GetBytes(accepted?"{\"accepted\":true}":"{\"accepted\":false}");
                    socket.Send(ack,ack.Length,peer);
                }
                catch(SocketException e)when(e.SocketErrorCode==SocketError.WouldBlock){break;}
                catch(ArgumentException){Rejected++;}
                catch(SocketException e){Status="Błąd BCI: "+e.SocketErrorCode;break;}
            }
        }
        public void Dispose(){socket?.Dispose();}
    }
}

#else
using System;
namespace Talon
{
    public sealed class BciLink : IDisposable
    {
        public string Status => "Interface · klawiatura / pad";
        public int Accepted => 0;
        public int Rejected => 0;
        public BciLink(int port, bool allowRemote = false) { }
        public void Poll(ControlState controls, double now) { }
        public void Dispose() { }
    }
}
#endif
