using System;
using System.Diagnostics;
using System.IO;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace Talon
{
    public sealed class TalonApp : MonoBehaviour
    {
        public FlightModel Flight {get;private set;}
        public ControlState Controls {get;private set;}
        public BciLink Bci {get;private set;}
        public EegLink Eeg {get;private set;}
        FacadePhase previousFacadePhase;
        public Camera View {get;private set;}
        public bool Fpv {get;private set;}
        public GameLevel InitialLevel=GameLevel.FreeFlight;
        public GameLevel Level {get;private set;}
        public FacadeSession Facade {get;private set;}
        public bool MenuOpen {get;private set;}=true;
        public bool HasSelectedLevel {get;private set;}
        public bool IsChallenge=>Level==GameLevel.FacadeAscent;
        public string LevelName=>IsChallenge?"02 / WEJŚCIE NA DACH":"01 / SWOBODNY LOT";
        public bool Diagnostics;
        public string Note="Strzałki: ruch · W/S: wysokość · A/D: obrót · F1: diagnostyka";
        public float Fps {get;private set;}
        public string QualityName {get;private set;}="Zbalansowana";
        public string PadName=>Gamepad.current?.displayName??"Klawiatura";
        CampusWorld world;
        FacadeWorld facadeWorld;
        Transform cameraRig;
        Vector3 cameraVelocity;
        TalonHud hud;
#if !UNITY_WEBGL || UNITY_EDITOR
        Process stimulus;
#endif
        float rotorAngle;
        double fpsStarted;
        int frames,quality=1;
        bool initialized;

        void Start()
        {
            Initialize(true);
#if !UNITY_WEBGL || UNITY_EDITOR
            if(Array.IndexOf(Environment.GetCommandLineArgs(),"--talon-smoke")>=0)
                gameObject.AddComponent<PlayerSmoke>();
#endif
        }
        public void Initialize(bool network)
        {
            if(initialized)return;initialized=true;
            Application.targetFrameRate=120;Application.runInBackground=true;QualitySettings.vSyncCount=1;
            Time.fixedDeltaTime=1f/60;
            fpsStarted=Time.realtimeSinceStartupAsDouble;
            Level=InitialLevel;Facade=new FacadeSession{EegMode=true};Facade.Reset();
            Eeg=new EegLink();
            Eeg.CaptureReady+=()=>{if(IsChallenge&&!MenuOpen)Facade.BeginStimulating();else Eeg.Cancel();};
            Eeg.Decision+=direction=>{if(IsChallenge&&!MenuOpen)Facade.ApplyEegDecision(direction);};
            Eeg.Failed+=error=>{if(IsChallenge)Facade.TrialFailed(error);};
            Controls=new ControlState();Flight=new FlightModel();Flight.TrackProgress=!IsChallenge;
            world=new CampusWorld(transform);Flight.Obstacles.AddRange(world.Obstacles);
            facadeWorld=new FacadeWorld(transform);world.SetVisible(!IsChallenge);facadeWorld.SetActive(IsChallenge);
            if(IsChallenge)SyncFacade();
            var lightGo=new GameObject("Afternoon sun");lightGo.transform.SetParent(transform);
            var sun=lightGo.AddComponent<Light>();sun.type=LightType.Directional;sun.intensity=1.5f;sun.color=new Color(1,.94f,.82f);
            sun.shadows=LightShadows.Soft;sun.shadowStrength=.75f;sun.shadowBias=.03f;sun.shadowNormalBias=.25f;
            lightGo.transform.rotation=Quaternion.Euler(46,-35,0);RenderSettings.sun=sun;
            RenderSettings.ambientMode=AmbientMode.Trilight;RenderSettings.ambientSkyColor=new Color(.58f,.68f,.8f);
            RenderSettings.ambientEquatorColor=new Color(.46f,.49f,.45f);RenderSettings.ambientGroundColor=new Color(.25f,.27f,.21f);
            RenderSettings.fog=true;RenderSettings.fogMode=FogMode.ExponentialSquared;RenderSettings.fogColor=new Color(.66f,.76f,.84f);RenderSettings.fogDensity=.005f;
            var sky=Resources.Load<Material>("Talon/Sky");if(sky)RenderSettings.skybox=sky;
            var volume=new GameObject("Global color and exposure").AddComponent<Volume>();volume.transform.SetParent(transform);volume.isGlobal=true;
            var profile=ScriptableObject.CreateInstance<VolumeProfile>();volume.profile=profile;
            profile.Add<Tonemapping>().mode.Override(TonemappingMode.ACES);
            profile.Add<ColorAdjustments>().postExposure.Override(.3f);
            var vignette=profile.Add<Vignette>();vignette.intensity.Override(.14f);vignette.smoothness.Override(.55f);
            cameraRig=new GameObject("Flight camera").transform;cameraRig.SetParent(transform);
            View=cameraRig.gameObject.AddComponent<Camera>();View.tag="MainCamera";View.fieldOfView=72;View.nearClipPlane=.05f;View.farClipPlane=300;
            View.backgroundColor=RenderSettings.fogColor;View.allowHDR=true;View.allowMSAA=true;
            var data=View.GetUniversalAdditionalCameraData();data.renderPostProcessing=true;data.antialiasing=AntialiasingMode.SubpixelMorphologicalAntiAliasing;
            data.antialiasingQuality=AntialiasingQuality.High;
            world.SetLevel(IsChallenge);
            hud=new TalonHud(this);SetQuality(1);UpdateCamera(1,true);
#if UNITY_WEBGL && !UNITY_EDITOR
            gameObject.AddComponent<TalonInterfaceBridge>();
#endif
            if(network)
            {
                bool remote=Array.IndexOf(Environment.GetCommandLineArgs(),"--bci-remote")>=0;
                Bci=new BciLink(9001,remote);
                if(remote)Note="BCI: odbiór z sieci lokalnej włączony";
                InputSystem.onDeviceChange+=DeviceChange;
            }
        }
        void DeviceChange(InputDevice device,InputDeviceChange change)
        {
            if(device is Gamepad&&(change==InputDeviceChange.Disconnected||change==InputDeviceChange.Removed))
            {Controls.Disarm();if(!IsChallenge&&Flight.Flying)Flight.Land();Note="Pad odłączony.";}
        }
        void Update()
        {
            if(!initialized)return;
            double now=Time.realtimeSinceStartupAsDouble;
            var key=Keyboard.current;var pad=Gamepad.current;
            if(key!=null)
            {
                if(key.tKey.wasPressedThisFrame)Act("takeoff");if(key.lKey.wasPressedThisFrame)Act("land");
                if(key.spaceKey.wasPressedThisFrame)Act("emergency");if(key.bKey.wasPressedThisFrame)Act("bci");
                if(key.vKey.wasPressedThisFrame)Act("camera");if(key.f1Key.wasPressedThisFrame)Act("diagnostics");
                if(key.f2Key.wasPressedThisFrame)Act("quality");if(key.pKey.wasPressedThisFrame)Act("photo");
                if(key.escapeKey.wasPressedThisFrame)Act(IsChallenge&&Facade.IsTrial?"cancel_trial":"menu");
                if(key.digit1Key.wasPressedThisFrame)TestSignal("up",now);if(key.digit2Key.wasPressedThisFrame)TestSignal("down",now);
                if(key.digit3Key.wasPressedThisFrame)TestSignal("forward",now);if(key.digit4Key.wasPressedThisFrame)TestSignal("rotate_right",now);
            }
            if(pad!=null)
            {
                if(pad.buttonNorth.wasPressedThisFrame)Act("takeoff");if(pad.buttonSouth.wasPressedThisFrame)Act("land");
                if(pad.buttonEast.wasPressedThisFrame)Act("emergency");if(pad.buttonWest.wasPressedThisFrame)Act("photo");
                if(pad.leftShoulder.wasPressedThisFrame)Act("bci");
            }
            Bci?.Poll(Controls,now);Eeg.Poll();
            Vector4 manual=Vector4.zero,keyboard=Vector4.zero;
            if(pad!=null)
            {
                var left=pad.leftStick.ReadValue();var right=pad.rightStick.ReadValue();
                manual=new Vector4(ControlState.Scale(left.x),ControlState.Scale(left.y),ControlState.Scale(right.y),ControlState.Scale(right.x));
            }
            if(Application.isFocused&&key!=null)
                keyboard=new Vector4((key.rightArrowKey.isPressed?60:0)-(key.leftArrowKey.isPressed?60:0),
                    (key.upArrowKey.isPressed?60:0)-(key.downArrowKey.isPressed?60:0),
                    (key.wKey.isPressed?60:0)-(key.sKey.isPressed?60:0),(key.dKey.isPressed?60:0)-(key.aKey.isPressed?60:0));
            Flight.Channels=!IsChallenge&&!MenuOpen&&Flight.Flying?Controls.Mix(manual,keyboard,now):Vector4.zero;
            if(IsChallenge)
            {
                if(!MenuOpen)Facade.Tick(Time.unscaledDeltaTime);
                if(Facade.EegMode&&Facade.Phase!=previousFacadePhase)
                {
                    if(Facade.Phase==FacadePhase.Preparing)Eeg.Begin();
                    else if(Facade.Phase==FacadePhase.Classifying)Eeg.Classify(Facade.TrialDuration);
                }
                previousFacadePhase=Facade.Phase;SyncFacade();
            }
            frames++;
            if(now-fpsStarted>.5){Fps=(float)(frames/(now-fpsStarted));frames=0;fpsStarted=now;}
            hud.Refresh();
        }
        void FixedUpdate()
        {
            if(!initialized)return;
            if(!IsChallenge)Flight.Step(Time.fixedDeltaTime);
        }
        void SyncFacade()
        {
            Flight.Position=Facade.Position;Flight.Velocity=Facade.Velocity;Flight.Yaw=0;
            Flight.Channels=Vector4.zero;Flight.Flying=Facade.Phase!=FacadePhase.Aborted;
            Flight.HoverAltitude=Facade.Position.y;Flight.TrackProgress=false;
        }
        void LateUpdate()
        {
            if(!initialized)return;
            world.Drone.position=Flight.Position+Vector3.up*.13f;
            var target=Quaternion.Euler(-Flight.Channels.y*.10f,Flight.Yaw,-Flight.Channels.x*.10f);
            world.Drone.rotation=Quaternion.Slerp(world.Drone.rotation,target,1-Mathf.Exp(-12*Time.deltaTime));
            rotorAngle=Flight.Flying?rotorAngle+2200*Time.deltaTime:rotorAngle;
            for(int i=0;i<world.Rotors.Count;i++)world.Rotors[i].localRotation=Quaternion.Euler(0,rotorAngle*(i%2==0?1:-1),0);

            UpdateCamera(Time.deltaTime,false);
        }
        public void PreviewFrame(){LateUpdate();UpdateCamera(1,true);}
        void UpdateCamera(float dt,bool snap)
        {
            View.rect=new Rect(0,60f/Screen.height,Mathf.Clamp01(1-320f/Screen.width),Mathf.Clamp01(1-124f/Screen.height));
            if(IsChallenge)
            {
                View.orthographic=true;View.orthographicSize=7.8f;
                cameraRig.position=new Vector3(0,7.2f,-23);cameraRig.rotation=Quaternion.identity;
                world.Drone.gameObject.SetActive(true);return;
            }
            View.orthographic=false;
            var forward=Quaternion.Euler(0,Flight.Yaw,0)*Vector3.forward;
            Vector3 desired=Fpv?Flight.Position+Vector3.up*.55f+forward*.37f:Flight.Position+Vector3.up*2.6f-forward*6;
            cameraRig.position=snap||Fpv?desired:Vector3.SmoothDamp(cameraRig.position,desired,ref cameraVelocity,.16f,Mathf.Infinity,dt);
            Vector3 look=Flight.Position+Vector3.up*.60f+forward*(Fpv?14:2.2f);
            cameraRig.rotation=Quaternion.LookRotation(look-cameraRig.position,Vector3.up);
            world.Drone.gameObject.SetActive(!Fpv);
            View.rect=new Rect(0,60f/Screen.height,Mathf.Clamp01(1-320f/Screen.width),Mathf.Clamp01(1-124f/Screen.height));
        }
        public void SelectLevel(GameLevel level)
        {
            Level=level;MenuOpen=false;HasSelectedLevel=true;
            Eeg.Cancel();Controls=new ControlState();Facade.Reset();previousFacadePhase=FacadePhase.Ready;
            Flight=new FlightModel();Flight.Obstacles.AddRange(world.Obstacles);
            Flight.TrackProgress=!IsChallenge;
            cameraVelocity=Vector3.zero;Fpv=false;world.SetVisible(!IsChallenge);facadeWorld.SetActive(IsChallenge);
            if(IsChallenge)SyncFacade();UpdateCamera(1,true);
            Note=IsChallenge?"Połącz czepek EEG, kliknij Start i skup wzrok na jednym kwadracie.":"Swobodny lot — bez limitu czasu i punktacji.";
        }
        void TestSignal(string command,double now)
        {
            if(!IsChallenge&&!MenuOpen)Controls.Fire(command,now);
        }
        public void Act(string action)
        {
            switch(action)
            {
                case "level_free":SelectLevel(GameLevel.FreeFlight);return;
                case "level_ssvep":
                case "level_facade":SelectLevel(GameLevel.FacadeAscent);return;
                case "menu":
                    if(MenuOpen){if(HasSelectedLevel)MenuOpen=false;}
                    else {if(IsChallenge){Eeg.Cancel();Facade.Pause();}Controls.Disarm();Flight.Channels=Vector4.zero;MenuOpen=true;}
                    return;
                case "emergency":
                    if(IsChallenge){Eeg.Cancel();Facade.Abort();}
                    Controls.Disarm();Flight.Emergency();return;
                case "quit":
#if UNITY_WEBGL && !UNITY_EDITOR
                    TalonInterfaceBridge.Current?.RequestExit();
#else
                    Application.Quit();
#endif
                    return;
            }
            if(MenuOpen)return;
            switch(action)
            {
                case "takeoff":
                    if(IsChallenge)
                    {
                        if(Facade.EegMode&&!Eeg.Connected){Note="Najpierw połącz czepek EEG.";return;}
                        if(Facade.Phase==FacadePhase.Paused)Facade.Resume();
                        else if(Facade.Phase==FacadePhase.Completed||Facade.Phase==FacadePhase.Aborted){Facade.Reset();Facade.StartChoice();}
                        else Facade.StartChoice();
                    }
                    else {Controls.Stop();Flight.Takeoff();}
                    break;
                case "retry":
                    if(IsChallenge){Eeg.Cancel();Facade.Reset();SyncFacade();}
                    break;
                case "land":if(IsChallenge){Eeg.Cancel();Facade.Pause();}else {Controls.Stop();Flight.Land();}break;

                case "eeg_connect":
                    if(IsChallenge)
                    {if(Eeg.Connected){Eeg.Disconnect();Facade.CancelTrial();}else Eeg.Connect();}
                    break;
                case "eeg_mode":
                    if(IsChallenge&&Facade.Phase!=FacadePhase.Moving)
                    {Eeg.Cancel();Facade.CancelTrial();Facade.EegMode=!Facade.EegMode;}
                    break;
                case "trial_less":if(!Facade.IsTrial)Facade.TrialDuration=Mathf.Max(4,Facade.TrialDuration-.5f);break;
                case "trial_more":if(!Facade.IsTrial)Facade.TrialDuration=Mathf.Min(10,Facade.TrialDuration+.5f);break;
                case "cancel_trial":Eeg.Cancel();Facade.CancelTrial();break;
                case "choose_up":ChooseFacade(MoveDirection.Up);break;
                case "choose_down":ChooseFacade(MoveDirection.Down);break;
                case "choose_left":ChooseFacade(MoveDirection.Left);break;
                case "choose_right":ChooseFacade(MoveDirection.Right);break;
                case "bci":
                    if(!IsChallenge){Controls.Toggle();Note=Controls.Armed?"BCI gotowe":"BCI wyłączone";}
                    break;
                case "camera":if(!IsChallenge){Fpv=!Fpv;UpdateCamera(1,true);}break;
                case "diagnostics":Diagnostics=!Diagnostics;break;
                case "quality":SetQuality((quality+1)%3);break;
                case "photo":
#if UNITY_WEBGL && !UNITY_EDITOR
                    Note="Zrzut ekranu: użyj narzędzia systemowego.";break;
#else
                    string folder=Path.Combine(Path.GetDirectoryName(Application.dataPath),"Captures");Directory.CreateDirectory(folder);
                    ScreenCapture.CaptureScreenshot(Path.Combine(folder,DateTime.Now.ToString("yyyyMMdd-HHmmss")+".png"));Note="Zdjęcie zapisane w "+folder;break;
#endif
                case "stimuli":if(!IsChallenge)OpenStimuli();break;
            }
        }
        void ChooseFacade(MoveDirection direction)
        {if(IsChallenge)Facade.Choose(direction);}
        void SetQuality(int value)
        {
            quality=value;QualityName=new[]{"Lekka","Zbalansowana","Wysoka"}[value];
            var pipeline=QualitySettings.renderPipeline as UniversalRenderPipelineAsset;
            if(!pipeline)pipeline=GraphicsSettings.defaultRenderPipeline as UniversalRenderPipelineAsset;
            if(pipeline)
            {
                pipeline.msaaSampleCount=value==0?2:4;pipeline.renderScale=value==2?1.15f:(value==0?.8f:1);
                pipeline.shadowDistance=value==0?45:85;pipeline.shadowCascadeCount=value==0?1:2;
            }
        }
        void OpenStimuli()
        {
#if UNITY_WEBGL && !UNITY_EDITOR
            Note="Próby EEG w Interface są dostępne w poziomie 02 · Wejście na dach.";
#else
            // An explicit optional launcher, configured only for this project.
            string config=Path.Combine(Path.GetDirectoryName(Application.dataPath),"bci-launcher.txt");
            if(!File.Exists(config)){Note="Uruchom ssvep.py w Pythonie — ten sam protokół UDP :9001.";return;}
            if(stimulus!=null&&!stimulus.HasExited)return;
            string launcher=File.ReadAllText(config).Trim();
            try{stimulus=Process.Start(new ProcessStartInfo(launcher){UseShellExecute=true});Note="Otworzono bodźce SSVEP";}
            catch(Exception e){Note="Nie udało się otworzyć SSVEP: "+e.Message;}
#endif
        }
        public void SuspendInput()
        {
            if(!initialized)return;
            Controls.Stop();Flight.Channels=Vector4.zero;
            if(IsChallenge){Eeg.Cancel();Facade.Pause();}
        }
        void OnApplicationFocus(bool focused){if(!focused)SuspendInput();}
        void OnDestroy()
        {
            InputSystem.onDeviceChange-=DeviceChange;Eeg?.Dispose();Bci?.Dispose();hud?.Dispose();world?.Dispose();facadeWorld?.Dispose();
            // Do not terminate external Python/EEG processes owned by the user.
        }
    }
}
