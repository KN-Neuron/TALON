using System;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace Talon.Editor
{
    public static class ProjectTools
    {
        const string Scene="Assets/TalonGenerated/FreeFlight.unity";
        const string ChallengeScene="Assets/TalonGenerated/FacadeAscent.unity";
        [MenuItem("TALON/Prepare campus project")]
        public static void Configure()
        {
            Directory.CreateDirectory("Assets/TalonGenerated");Directory.CreateDirectory("Assets/TalonGenerated/Resources/Talon");AssetDatabase.Refresh();
            var pipeline=AssetDatabase.LoadAssetAtPath<UniversalRenderPipelineAsset>("Assets/Settings/PC_RPAsset.asset");
            if(!pipeline)throw new Exception("URP template asset missing");
            pipeline.msaaSampleCount=4;pipeline.supportsHDR=true;pipeline.shadowDistance=85;pipeline.shadowCascadeCount=2;
            pipeline.useSRPBatcher=true;
            var serialized=new SerializedObject(pipeline);
            serialized.FindProperty("m_SoftShadowsSupported").boolValue=true;serialized.ApplyModifiedPropertiesWithoutUndo();
            GraphicsSettings.defaultRenderPipeline=pipeline;
            for(int i=0;i<QualitySettings.names.Length;i++){QualitySettings.SetQualityLevel(i);QualitySettings.renderPipeline=pipeline;}
            QualitySettings.SetQualityLevel(Math.Min(1,QualitySettings.names.Length-1));QualitySettings.vSyncCount=1;
            PlayerSettings.companyName="KN Interface";PlayerSettings.productName="TALON";
            PlayerSettings.defaultScreenWidth=1600;PlayerSettings.defaultScreenHeight=900;PlayerSettings.resizableWindow=true;
            PlayerSettings.fullScreenMode=FullScreenMode.Windowed;PlayerSettings.colorSpace=ColorSpace.Linear;
            PlayerSettings.runInBackground=true;
            var lit=Shader.Find("Universal Render Pipeline/Lit");if(!lit)throw new Exception("URP Lit shader missing");
            Seed("Lit",lit,false);Seed("Leaves",lit,true);
            string skyPath="Assets/TalonGenerated/Resources/Talon/Sky.mat";
            if(!AssetDatabase.LoadAssetAtPath<Material>(skyPath))
            {
                var sky=new Material(Shader.Find("Skybox/Procedural"));sky.SetFloat("_SunSize",.025f);sky.SetFloat("_AtmosphereThickness",1.1f);
                sky.SetColor("_SkyTint",new Color(.57f,.61f,.65f));sky.SetFloat("_Exposure",1.2f);AssetDatabase.CreateAsset(sky,skyPath);
            }
            var scene=EditorSceneManager.NewScene(NewSceneSetup.EmptyScene,NewSceneMode.Single);
            new GameObject("TALON · Campus bootstrap").AddComponent<TalonApp>();
            EditorSceneManager.SaveScene(scene,Scene);
            scene=EditorSceneManager.NewScene(NewSceneSetup.EmptyScene,NewSceneMode.Single);
            var challengeApp=new GameObject("TALON · Facade ascent bootstrap").AddComponent<TalonApp>();
            challengeApp.InitialLevel=GameLevel.FacadeAscent;
            EditorSceneManager.SaveScene(scene,ChallengeScene);
            EditorSceneManager.OpenScene(Scene);
            AssetDatabase.DeleteAsset("Assets/TalonGenerated/Campus.unity");
            AssetDatabase.DeleteAsset("Assets/TalonGenerated/SsvepChallenge.unity");
            EditorBuildSettings.RemoveConfigObject("com.unity.input.settings.actions");
            EditorBuildSettings.scenes=new[]{new EditorBuildSettingsScene(Scene,true),new EditorBuildSettingsScene(ChallengeScene,true)};
            EditorUtility.SetDirty(pipeline);AssetDatabase.SaveAssets();
            Debug.Log("TALON_CONFIGURED: Unity URP, native renderer, Campus scene");
        }
        static void Seed(string name,Shader shader,bool clip)
        {
            string path=$"Assets/TalonGenerated/Resources/Talon/{name}.mat";
            var material=AssetDatabase.LoadAssetAtPath<Material>(path);
            if(!material){material=new Material(shader);AssetDatabase.CreateAsset(material,path);}
            material.enableInstancing=true;
            if(clip){material.SetFloat("_AlphaClip",1);material.SetFloat("_Cull",0);material.EnableKeyword("_ALPHATEST_ON");material.renderQueue=2450;}
            EditorUtility.SetDirty(material);
        }
        static void Check(bool condition,string description){if(!condition)throw new Exception("TALON validation failed: "+description);}
        static void Step(FlightModel model,float seconds,Vector4 ch=default)
        {model.Channels=ch;for(int i=0;i<Mathf.RoundToInt(seconds*60);i++)model.Step(1f/60);}
        [MenuItem("TALON/Validate flight and BCI")]
        public static void Validate()
        {
            Configure();
            Check(GraphicsSettings.defaultRenderPipeline is UniversalRenderPipelineAsset,"URP active");
            var f=new FlightModel();Step(f,2,new Vector4(0,100,100,0));Check(f.Position==Vector3.zero,"grounded ignores sticks");
            f.Takeoff();Step(f,8);Check(Mathf.Abs(f.Position.y-1.2f)<.05f,"takeoff and altitude hold");
            Step(f,3,new Vector4(0,0,100,0));float altitude=f.Position.y;Step(f,6);Check(Mathf.Abs(f.Position.y-altitude)<.2f,"climb then hold");
            var crash=new FlightModel();crash.Position=f.Position;crash.Flying=true;f.Land();crash.Emergency();Step(f,.5f);Step(crash,.5f);Check(crash.Position.y<f.Position.y,"emergency descent faster");
            Step(f,12);Check(f.Position.y==0&&!f.Flying,"landing completes");
            f=new FlightModel(new[]{new Gate(0,5,true,0),new Gate(0,15,true,3)});f.Takeoff();Step(f,8,new Vector4(0,100,0,0));
            Check(f.NextGate==1&&f.Touching&&f.Position.z>13&&f.Position.z<15,"gate passage and wall collision");
            Step(f,2.5f,new Vector4(0,0,100,0));Step(f,3,new Vector4(0,100,0,0));Check(f.Laps==1,"raised gate and lap count");
            var c=new ControlState();Check(!c.Fire("up",0),"BCI disarmed by default");c.Toggle();Check(c.Fire("forward",10),"BCI armed");
            Check(c.Mix(Vector4.zero,Vector4.zero,10.2).y==40,"BCI pulse");Check(c.Mix(Vector4.zero,Vector4.zero,11.1)==Vector4.zero,"pulse expires");
            c.Fire("forward",20);Check(c.Mix(new Vector4(30,0,0,0),Vector4.zero,20).x==30,"pad wins");
            Check(c.Mix(Vector4.zero,Vector4.zero,20.5)==Vector4.zero,"manual priority hold");Check(c.Mix(Vector4.zero,Vector4.zero,22)==Vector4.zero,"old pulse cannot resume");
            Check(ControlState.Scale(.05f)==0&&Mathf.Abs(ControlState.Scale(1)-60)<.01f,"deadzone and speed");
            using(var link=new BciLink(0))
            using(var sender=new UdpClient())
            {
                int port=int.Parse(link.Status.Split(':')[1]);
                byte[] bad=Encoding.UTF8.GetBytes("[]"),good=Encoding.UTF8.GetBytes("{\"cmd\":\"up\"}");
                sender.Send(bad,bad.Length,new IPEndPoint(IPAddress.Loopback,port));sender.Send(good,good.Length,new IPEndPoint(IPAddress.Loopback,port));
                System.Threading.Thread.Sleep(30);link.Poll(c,30);
                Check(link.Accepted==1&&link.Rejected==1,"UDP accepts commands and rejects malformed data");
            }
            ValidateFacade();
            Debug.Log("TALON_VALIDATION_PASSED: flight, collisions, gates, laps, altitude, emergency, pad priority, BCI UDP, URP");
        }
        static void ValidateFacade()
        {
            Check(EditorBuildSettings.scenes.Length==2,"two level scenes included");
            var run=new FacadeSession();Vector3 origin=run.Position;
            Check(!run.Choose(MoveDirection.Up),"no direction accepted outside choice window");
            run.StartChoice();run.Choose(MoveDirection.Up);run.Tick(3.9f);
            Check(run.ShowSquares&&run.Position==origin,"four squares remain and drone waits for four seconds");
            run.Choose(MoveDirection.Right);run.Tick(.1f);
            Check(!run.ShowSquares&&run.Phase==FacadePhase.Moving,"squares hide before animation");
            run.Tick(FacadeSession.MoveDuration/2);
            Check(run.Position.x>0&&run.Position.x<1,"movement is animated");
            run.Tick(FacadeSession.MoveDuration);
            Check(Vector3.Distance(run.Position,origin+Vector3.right)<.0001f&&run.Moves==1,"last click selects exactly one metre");
            Check(!run.Choose(MoveDirection.Left),"animation cannot queue a hidden click");
            run.StartChoice();run.Tick(4);
            Check(run.Position==origin+Vector3.right&&run.Phase==FacadePhase.Waiting,"no click means no movement");
            run.StartChoice();run.Choose(MoveDirection.Up);run.Tick(2);run.Pause();run.Tick(30);
            Check(run.Phase==FacadePhase.Paused&&!run.ShowSquares,"pause hides squares and freezes choice");
            run.Resume();Check(run.Remaining==4&&run.Selected==MoveDirection.None,"resumed choice restarts without a stale click");
            run.Choose(MoveDirection.Up);run.Tick(4);run.Tick(.3f);run.Pause();Vector3 paused=run.Position;run.Tick(20);
            Check(run.Position==paused,"pause freezes an in-flight animation");run.Resume();run.Tick(2);
            Check(Vector3.Distance(run.Position,origin+Vector3.right+Vector3.up)<.0001f,"resume finishes original one-metre endpoint");
            run.Reset();
            MoveFacade(run,MoveDirection.Up);MoveFacade(run,MoveDirection.Up);Vector3 before=run.Position;
            MoveFacade(run,MoveDirection.Up);
            Check(run.Blocked==1&&run.Position==before,"swept collision blocks the full step");
            run.Reset();MoveFacade(run,MoveDirection.Down);Check(run.Blocked==1&&run.Position.y==FacadeSession.MinHeight,"lower boundary blocks movement");
            run.Reset();
            MoveFacade(run,MoveDirection.Right,2);MoveFacade(run,MoveDirection.Up,4);
            MoveFacade(run,MoveDirection.Left,4);MoveFacade(run,MoveDirection.Up,3);
            MoveFacade(run,MoveDirection.Right,3);MoveFacade(run,MoveDirection.Up,5);
            Check(run.Phase==FacadePhase.Completed&&Mathf.Abs(run.Position.y-FacadeSession.GoalHeight)<.001f&&run.Blocked==0,"roof is reachable using only four one-metre directions");
            run.Reset();run.StartChoice();run.Choose(MoveDirection.Up);run.Abort();run.Tick(10);
            Check(run.Phase==FacadePhase.Aborted&&run.Position==origin&&!run.ShowSquares,"abort cancels pending movement");
            run.Reset();run.EegMode=true;run.StartChoice();
            Check(run.Phase==FacadePhase.Countdown&&!run.ShowSquares,"EEG starts with countdown");
            Check(!run.Choose(MoveDirection.Right),"EEG ignores manual decisions");
            run.Tick(1.9f);Check(run.Phase==FacadePhase.Countdown,"EEG countdown lasts two seconds");
            run.Tick(.1f);Check(run.Phase==FacadePhase.Preparing,"wait for capture acknowledgement");
            Check(!run.ApplyEegDecision(MoveDirection.Right),"early classification rejected");
            run.BeginStimulating();run.Tick(3.9f);Check(run.ShowSquares&&run.Position==origin,"EEG captures four seconds without moving");
            run.Tick(.1f);Check(run.Phase==FacadePhase.Classifying&&!run.ShowSquares,"squares hide during FBCCA");
            Check(run.ApplyEegDecision(MoveDirection.Right),"FBCCA direction accepted");
            Check(!run.ApplyEegDecision(MoveDirection.Left),"duplicate decision ignored");
            run.Tick(2);Check(run.Position==origin+Vector3.right,"EEG moves exactly one metre");
            run.StartChoice();run.Tick(2);run.BeginStimulating();run.Tick(4);run.CancelTrial();
            Check(!run.ApplyEegDecision(MoveDirection.Up)&&run.Position==origin+Vector3.right,"cancel rejects late classifier result");
            run.StartChoice();run.TrialFailed("device lost");
            Check(run.Phase==FacadePhase.Waiting&&run.Position==origin+Vector3.right,"lost EEG cannot move drone");
            Debug.Log("TALON_EEG_VALIDATION_PASSED: countdown, capture acknowledgement, four-second stimulation, classifier gating, one metre, duplicate rejection, cancellation, device loss");
            Debug.Log("TALON_FACADE_VALIDATION_PASSED: four-second window, click selection, no-click, exact distance, animation, swept obstacles, boundaries, pause/resume, roof route, abort");
        }
        static void MoveFacade(FacadeSession run,MoveDirection direction,int count=1)
        {for(int i=0;i<count;i++){run.StartChoice();run.Choose(direction);run.Tick(4);run.Tick(FacadeSession.MoveDuration+.01f);}}
        [MenuItem("TALON/Build Windows player")]
        public static void Build()
        {
            Validate();Directory.CreateDirectory("Builds/Windows");
            var report=BuildPipeline.BuildPlayer(new BuildPlayerOptions{scenes=new[]{Scene,ChallengeScene},locationPathName="Builds/Windows/TALON.exe",target=BuildTarget.StandaloneWindows64,options=BuildOptions.None});
            if(report.summary.result!=BuildResult.Succeeded)throw new Exception("TALON player build failed: "+report.summary.result);
            Debug.Log("TALON_BUILD_PASSED: "+Path.GetFullPath("Builds/Windows/TALON.exe"));
        }
        [MenuItem("TALON/Build Interface WebGL module")]
        public static void BuildWebGL()
        {
            Configure();ValidateFacade();
            PlayerSettings.WebGL.compressionFormat=WebGLCompressionFormat.Disabled;
            PlayerSettings.WebGL.dataCaching=false;
            PlayerSettings.WebGL.decompressionFallback=false;
            PlayerSettings.WebGL.threadsSupport=false;
            PlayerSettings.WebGL.initialMemorySize=256;
            PlayerSettings.WebGL.maximumMemorySize=2048;
            PlayerSettings.SetScriptingBackend(UnityEditor.Build.NamedBuildTarget.WebGL,ScriptingImplementation.IL2CPP);
            Directory.CreateDirectory("Builds/WebGL");
            var report=BuildPipeline.BuildPlayer(new BuildPlayerOptions{
                scenes=new[]{Scene,ChallengeScene},locationPathName="Builds/WebGL",target=BuildTarget.WebGL,options=BuildOptions.None});
            if(report.summary.result!=BuildResult.Succeeded)throw new Exception("TALON WebGL build failed: "+report.summary.result);
            Debug.Log("TALON_WEBGL_BUILD_PASSED: "+Path.GetFullPath("Builds/WebGL"));
        }
        public static void Preview()
        {
            Configure();var app=UnityEngine.Object.FindAnyObjectByType<TalonApp>();app.Initialize(false);app.SelectLevel(GameLevel.FreeFlight);app.Flight.Position=new Vector3(0,1.2f,0);app.PreviewFrame();
            var rt=new RenderTexture(1440,900,24);rt.Create();
            RenderPipeline.SubmitRenderRequest(app.View,new RenderPipeline.StandardRequest{destination=rt});
            var previous=RenderTexture.active;RenderTexture.active=rt;
            var image=new Texture2D(1440,900,TextureFormat.RGB24,false);image.ReadPixels(new Rect(0,0,1440,900),0,0);image.Apply();
            Directory.CreateDirectory("Logs");File.WriteAllBytes("Logs/Campus-preview.png",image.EncodeToPNG());RenderTexture.active=previous;
            UnityEngine.Object.DestroyImmediate(image);rt.Release();UnityEngine.Object.DestroyImmediate(rt);
            Debug.Log("TALON_PREVIEW_PASSED");
        }
    }
}
