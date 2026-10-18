#if !UNITY_WEBGL || UNITY_EDITOR
using System.Collections;
using System.IO;
using System.Net.Sockets;
using System.Text;
using UnityEngine;
using UnityEngine.UIElements;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.LowLevel;

namespace Talon
{
    public sealed class PlayerSmoke : MonoBehaviour
    {
        IEnumerator SendForward()
        {
            using(var sender=new UdpClient())
            {
                var packet=Encoding.UTF8.GetBytes("{\"cmd\":\"forward\"}");
                for(int i=0;i<4;i++){sender.Send(packet,packet.Length,"127.0.0.1",9001);yield return new WaitForSecondsRealtime(.3f);}
            }
        }
        IEnumerator Capture(string file)
        {
            string folder=Path.Combine(Path.GetDirectoryName(Application.dataPath),"Captures");Directory.CreateDirectory(folder);
            yield return new WaitForEndOfFrame();ScreenCapture.CaptureScreenshot(Path.Combine(folder,file));yield return null;
        }
        IEnumerator Start()
        {
            yield return new WaitForSecondsRealtime(1);var app=GetComponent<TalonApp>();
            yield return Capture("Unity-level-menu.png");
            if(!app.MenuOpen){Fail("initial menu missing");yield break;}
            app.Act("level_free");app.Act("takeoff");yield return new WaitForSecondsRealtime(3);
            if(app.Flight.Position.y<.8f||app.IsChallenge){Fail("free-flight takeoff failed");yield break;}
            app.Act("bci");float before=app.Flight.Position.z;yield return SendForward();
            if(app.Bci.Accepted<4||app.Flight.Position.z<before+.3f){Fail("free-flight UDP motion failed");yield break;}
            app.Controls.Disarm();yield return Capture("Unity-chase.png");
            app.Act("camera");yield return new WaitForSecondsRealtime(.3f);yield return Capture("Unity-FPV.png");

            app.Act("level_facade");app.Act("eeg_mode");var origin=app.Facade.Position;
            if(!app.IsChallenge||app.Controls.Armed||!app.View.orthographic){Fail("facade selection/camera failed");yield break;}
            app.Act("takeoff");yield return new WaitForSecondsRealtime(.2f);
            if(!app.Facade.ShowSquares){Fail("four direction squares missing");yield break;}
            // Exercise the real Button activation callback, not a direct model call.
            var doc=app.GetComponentInChildren<UIDocument>();var button=doc.rootVisualElement.Q<Button>("choose_right");
            var mouse=InputSystem.AddDevice<Mouse>("TalonSmokeMouse");
            var centre=button.worldBound.center;var cursor=new Vector2(centre.x,Screen.height-centre.y);
            InputSystem.QueueStateEvent(mouse,new MouseState{position=cursor}.WithButton(UnityEngine.InputSystem.LowLevel.MouseButton.Left));
            yield return null;yield return null;
            InputSystem.QueueStateEvent(mouse,new MouseState{position=cursor});
            yield return null;yield return null;
            if(app.Facade.Selected!=MoveDirection.Right){Fail("direction button did not select");yield break;}
            yield return Capture("Unity-facade-choice.png");
            yield return new WaitForSecondsRealtime(2.5f);
            if(!app.Facade.ShowSquares||app.Facade.Position!=origin){Fail("drone moved before four-second window closed");yield break;}
            yield return new WaitForSecondsRealtime(2.8f);
            if(app.Facade.ShowSquares||Vector3.Distance(app.Facade.Position,origin+Vector3.right)>.001f){Fail("one-metre click animation failed");yield break;}
            yield return Capture("Unity-facade-moved.png");
            var position=app.Facade.Position;yield return SendForward();
            if(app.Facade.Position!=position||app.Controls.Armed){Fail("UDP controlled click-only level");yield break;}
            app.Act("takeoff");yield return new WaitForSecondsRealtime(4.2f);
            if(app.Facade.ShowSquares||app.Facade.Position!=position){Fail($"no-click window: phase={app.Facade.Phase}, remaining={app.Facade.Remaining}, selected={app.Facade.Selected}, position={app.Facade.Position}, expected={position}");yield break;}
            app.Act("takeoff");app.Act("choose_up");app.Act("menu");yield return new WaitForSecondsRealtime(.3f);
            if(!app.MenuOpen||app.Facade.ShowSquares||app.Facade.Phase!=FacadePhase.Paused){Fail("menu failed to pause selection");yield break;}
            app.Act("menu");app.Act("takeoff");
            if(!app.Facade.ShowSquares||app.Facade.Selected!=MoveDirection.None){Fail("resume retained stale click");yield break;}
            app.Act("retry");if(app.Facade.Position!=origin||app.Facade.Moves!=0){Fail("retry failed");yield break;}
            // Explicit synthetic source exercises the real Python process, JSON
            // protocol, six-channel capture, FBCCA and the Unity state machine.
            app.Act("eeg_mode");app.Act("eeg_connect");
            float timeout=Time.realtimeSinceStartup+40;
            while(!app.Eeg.Connected&&Time.realtimeSinceStartup<timeout)yield return null;
            if(!app.Eeg.Connected||!app.Eeg.Simulated){Fail("synthetic EEG subprocess connection: "+app.Eeg.Status);yield break;}
            app.Act("takeoff");yield return new WaitForSecondsRealtime(.5f);
            if(app.Facade.Phase!=FacadePhase.Countdown||app.Facade.ShowSquares){Fail("EEG countdown missing");yield break;}
            timeout=Time.realtimeSinceStartup+6;
            while(!app.Facade.ShowSquares&&Time.realtimeSinceStartup<timeout)yield return null;
            if(!app.Facade.ShowSquares){Fail("EEG capture did not start: "+app.Eeg.Status);yield break;}
            app.Act("choose_left");
            if(app.Facade.Selected!=MoveDirection.None){Fail("click chose direction in EEG mode");yield break;}
            yield return Capture("Unity-facade-eeg.png");
            yield return new WaitForSecondsRealtime(3.2f);
            if(!app.Facade.ShowSquares||app.Facade.Position!=origin){Fail("EEG squares/capture too short");yield break;}
            timeout=Time.realtimeSinceStartup+25;
            while(app.Facade.Moves==0&&Time.realtimeSinceStartup<timeout)yield return null;
            if(app.Facade.Position!=origin+Vector3.right||app.Facade.Moves!=1){Fail("FBCCA one-metre move: "+app.Eeg.Status+" / "+app.Facade.Message);yield break;}
            app.Act("takeoff");app.Act("cancel_trial");
            yield return new WaitForSecondsRealtime(.2f);
            if(app.Facade.IsTrial||app.Facade.Moves!=1){Fail("EEG cancel failed");yield break;}
            app.Act("takeoff");
            timeout=Time.realtimeSinceStartup+8;
            while(!app.Facade.ShowSquares&&Time.realtimeSinceStartup<timeout)yield return null;
            app.Act("menu");yield return new WaitForSecondsRealtime(.2f);
            if(app.Facade.Phase!=FacadePhase.Paused||app.Facade.ShowSquares){Fail("EEG menu did not cancel capture");yield break;}
            app.Act("menu");app.Act("retry");
            app.Act("eeg_connect");
            if(app.Eeg.Connected){Fail("disconnect did not release EEG");yield break;}
            app.Act("level_free");if(app.IsChallenge||app.Flight.Flying||app.Controls.Armed){Fail("return to free flight failed");yield break;}
            Debug.Log($"TALON_PLAYER_SMOKE_PASSED: level menu, free flight UDP, facade camera, actual square button, four-second visibility, exact one-metre animation, no-click, EEG/UDP isolation, pause, retry, Python EEG process, six-channel FBCCA, EEG countdown, click isolation, cancellation; GPU={SystemInfo.graphicsDeviceName}; FPS={app.Fps:0.0}");
            Application.Quit(0);
        }
        static void Fail(string message){Debug.LogError("TALON_PLAYER_SMOKE_FAILED: "+message);Application.Quit(1);}
    }
}

#endif
