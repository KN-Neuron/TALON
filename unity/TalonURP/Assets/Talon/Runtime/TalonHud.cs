using UnityEngine;
using UnityEngine.UIElements;

namespace Talon
{
    public sealed class TalonHud
    {
        readonly TalonApp app;
        readonly GameObject owner;
        readonly PanelSettings settings;
        readonly Label status,source,connection,telemetry,note,debug,level,challengeStats,hint,menuSubtitle,choiceClock,help;
        readonly Button eegConnect,eegMode,trialLess,trialMore,cancelTrial;
        readonly Label eegStatus,trialWindow;
        readonly VisualElement eegPanel;
        readonly Button start,land,bci,camera,quality,retry,continueButton,stimuli,emergency;
        readonly VisualElement diagnostics,challenge,menu,side,controlsArea,choiceOverlay;
        readonly Button[] directionButtons=new Button[4];
        readonly MoveDirection[] directions={MoveDirection.Up,MoveDirection.Down,MoveDirection.Left,MoveDirection.Right};
        public TalonHud(TalonApp app)
        {
            this.app=app;owner=new GameObject("TALON · Interface");owner.transform.SetParent(app.transform);
            settings=ScriptableObject.CreateInstance<PanelSettings>();settings.scaleMode=PanelScaleMode.ConstantPixelSize;settings.sortingOrder=10;
            settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("Talon/DefaultTheme");
            var document=owner.AddComponent<UIDocument>();document.panelSettings=settings;
            var root=document.rootVisualElement;root.pickingMode=PickingMode.Ignore;
            root.style.position=Position.Absolute;root.style.left=0;root.style.right=0;root.style.top=0;root.style.bottom=0;
            root.style.color=new Color(.91f,.94f,.97f);root.style.fontSize=14;
            var header=Panel(root,0,0,0,64);header.style.flexDirection=FlexDirection.Row;header.style.alignItems=Align.Center;
            var title=Label(header,"TALON",26);title.style.unityFontStyleAndWeight=FontStyle.Bold;title.style.marginRight=20;
            Label(header,"KN INTERFACE",12).style.color=new Color(.60f,.68f,.73f);
            connection=Label(header,"",12);connection.style.marginLeft=StyleKeyword.Auto;
            side=Panel(root,float.NaN,64,0,float.NaN);side.style.width=320;side.style.bottom=60;
            side.style.paddingTop=18;side.style.paddingLeft=20;side.style.paddingRight=20;
            var scroll=new ScrollView(ScrollViewMode.Vertical);scroll.style.flexGrow=1;side.Add(scroll);controlsArea=scroll;
            scroll.verticalScroller.style.width=7;scroll.verticalScroller.style.backgroundColor=new Color(.07f,.10f,.13f);
            var thumb=scroll.verticalScroller.Q<VisualElement>(className:"unity-base-slider__dragger");
            if(thumb!=null)thumb.style.backgroundColor=new Color(.26f,.38f,.40f);
            foreach(var arrow in scroll.verticalScroller.Query<RepeatButton>().ToList())arrow.style.display=DisplayStyle.None;
            level=Label(scroll,"",12);level.style.color=new Color(.47f,.76f,.68f);
            status=Label(scroll,"Na ziemi",23);status.style.marginTop=12;
            source=Label(scroll,"",12);source.style.marginTop=4;source.style.marginBottom=12;source.style.color=new Color(.65f,.72f,.77f);
            challenge=new VisualElement();challenge.style.backgroundColor=new Color(.075f,.12f,.14f);challenge.style.paddingLeft=12;challenge.style.paddingRight=12;
            challenge.style.paddingTop=12;challenge.style.paddingBottom=12;challenge.style.marginBottom=10;scroll.Add(challenge);
            challengeStats=Label(challenge,"",15);challengeStats.style.whiteSpace=WhiteSpace.Normal;
            hint=Label(challenge,"",12);hint.style.whiteSpace=WhiteSpace.Normal;hint.style.marginTop=12;hint.style.color=new Color(.70f,.83f,.78f);
            eegPanel=new VisualElement();scroll.Add(eegPanel);
            eegStatus=Label(eegPanel,"",12);eegStatus.style.whiteSpace=WhiteSpace.Normal;
            eegConnect=Button(eegPanel,"Połącz BA MAXI 009","eeg_connect");
            eegMode=Button(eegPanel,"Sterowanie: EEG","eeg_mode");eegMode.style.fontSize=12;
            trialWindow=Label(eegPanel,"",12);
            var durationRow=new VisualElement();durationRow.style.flexDirection=FlexDirection.Row;eegPanel.Add(durationRow);
            trialLess=Button(durationRow,"− 0,5 s","trial_less");trialMore=Button(durationRow,"+ 0,5 s","trial_more");
            trialLess.style.flexGrow=trialMore.style.flexGrow=1;
            cancelTrial=Button(eegPanel,"Anuluj próbę [ESC]","cancel_trial");
            var row=new VisualElement();row.style.flexDirection=FlexDirection.Row;scroll.Add(row);
            start=Button(row,"Start  [T]","takeoff");land=Button(row,"Ląduj  [L]","land");start.style.flexGrow=land.style.flexGrow=1;
            retry=Button(scroll,"Nowa próba","retry");
            bci=Button(scroll,"","bci");stimuli=Button(scroll,"Bodźce SSVEP","stimuli");
            camera=Button(scroll,"","camera");quality=Button(scroll,"","quality");
            Button(scroll,"Wybierz poziom  [ESC]","menu");Button(scroll,"Diagnostyka  [F1]","diagnostics");
            Button(scroll,"Zdjęcie  [P]","photo");
            help=Label(scroll,"RUCH   Strzałki · W/S wysokość · A/D obrót\nTEST BCI   1 góra · 2 dół · 3 przód · 4 obrót",11);
            help.style.marginTop=12;help.style.whiteSpace=WhiteSpace.Normal;help.style.color=new Color(.53f,.62f,.67f);
            emergency=Button(side,"Wyłącz silniki  [SPACJA]","emergency");emergency.style.backgroundColor=new Color(.65f,.16f,.22f);emergency.style.flexShrink=0;
            var bottom=Panel(root,0,float.NaN,0,60);bottom.style.bottom=0;
            telemetry=Label(bottom,"",13);note=Label(bottom,"",11);note.style.color=new Color(.61f,.69f,.72f);
            diagnostics=Panel(root,20,84,float.NaN,110);diagnostics.style.width=420;diagnostics.style.borderTopLeftRadius=8;diagnostics.style.borderBottomRightRadius=8;
            debug=Label(diagnostics,"",12);debug.style.whiteSpace=WhiteSpace.Normal;
            choiceOverlay=new VisualElement();root.Add(choiceOverlay);choiceOverlay.pickingMode=PickingMode.Ignore;
            choiceOverlay.style.position=Position.Absolute;choiceOverlay.style.left=0;choiceOverlay.style.right=320;choiceOverlay.style.top=64;choiceOverlay.style.bottom=60;
            for(int i=0;i<4;i++)
            {
                string action=new[]{"choose_up","choose_down","choose_left","choose_right"}[i];
                var square=Button(choiceOverlay,FacadeSession.Name(directions[i])+"\n1 metr",action);
                square.style.position=Position.Absolute;square.style.width=130;square.style.height=130;
                square.style.marginTop=square.style.marginBottom=square.style.marginLeft=square.style.marginRight=0;
                square.style.fontSize=21;square.style.unityTextAlign=TextAnchor.MiddleCenter;
                square.style.borderTopWidth=square.style.borderBottomWidth=square.style.borderLeftWidth=square.style.borderRightWidth=4;
                directionButtons[i]=square;
            }
            choiceClock=Label(choiceOverlay,"",19);choiceClock.pickingMode=PickingMode.Ignore;
            choiceClock.style.position=Position.Absolute;choiceClock.style.width=260;choiceClock.style.unityTextAlign=TextAnchor.MiddleCenter;
            choiceClock.style.whiteSpace=WhiteSpace.Normal;choiceClock.style.backgroundColor=new Color(.025f,.055f,.07f,.9f);
            choiceClock.style.paddingTop=12;choiceClock.style.paddingBottom=12;

            menu=Panel(root,0,64,320,float.NaN);menu.style.bottom=60;menu.style.backgroundColor=new Color(.025f,.045f,.065f,.92f);
            menu.style.justifyContent=Justify.Center;menu.style.alignItems=Align.Center;
            Label(menu,"Wybierz poziom",34).style.unityFontStyleAndWeight=FontStyle.Bold;
            menuSubtitle=Label(menu,"",14);menuSubtitle.style.marginTop=12;menuSubtitle.style.marginBottom=28;
            var cards=new VisualElement();cards.style.flexDirection=FlexDirection.Row;cards.style.flexWrap=Wrap.Wrap;cards.style.justifyContent=Justify.Center;menu.Add(cards);
            Card(cards,"01","Swobodny lot","Poznaj park i naucz się sterowania.\nBez limitu czasu i punktacji.\nPad, klawiatura lub BCI.","Lataj swobodnie","level_free");
            Card(cards,"02","Wejście na dach","Góra, dół, lewo i prawo.\nSterowanie wzrokiem EEG · ruch o 1 metr.\nOmijaj przeszkody na elewacji.","Wejdź na dach","level_facade");
            continueButton=Button(menu,"Kontynuuj obecny poziom","menu");continueButton.style.width=260;continueButton.style.marginTop=20;
            var quit=Button(menu,"Zamknij grę","quit");quit.style.width=260;
        }
        void Card(VisualElement parent,string number,string title,string description,string text,string action)
        {
            var card=new VisualElement();card.style.width=270;card.style.minHeight=250;card.style.marginLeft=8;card.style.marginRight=8;card.style.marginBottom=12;
            card.style.paddingLeft=22;card.style.paddingRight=22;card.style.paddingTop=22;card.style.paddingBottom=16;
            card.style.backgroundColor=new Color(.075f,.13f,.16f);parent.Add(card);
            Label(card,number,14).style.color=new Color(.40f,.78f,.65f);
            Label(card,title,23).style.marginTop=10;
            var body=Label(card,description,13);body.style.whiteSpace=WhiteSpace.Normal;body.style.marginTop=14;body.style.marginBottom=20;body.style.flexGrow=1;
            Button(card,text,action).style.backgroundColor=new Color(.12f,.39f,.32f);
        }
        static VisualElement Panel(VisualElement parent,float left,float top,float right,float height)
        {
            var el=new VisualElement();el.style.position=Position.Absolute;
            if(!float.IsNaN(left))el.style.left=left;if(!float.IsNaN(top))el.style.top=top;if(!float.IsNaN(right))el.style.right=right;if(!float.IsNaN(height))el.style.height=height;
            el.style.backgroundColor=new Color(.045f,.065f,.09f,1);el.style.paddingLeft=20;el.style.paddingRight=20;el.style.paddingTop=7;el.style.paddingBottom=7;parent.Add(el);return el;
        }
        static Label Label(VisualElement parent,string text,int size)
        {var label=new Label(text);label.style.fontSize=size;parent.Add(label);return label;}
        Button Button(VisualElement parent,string text,string action)
        {
            var b=new Button(()=>app.Act(action)){text=text,name=action};parent.Add(b);
            b.style.height=36;b.style.marginTop=3;b.style.marginBottom=3;b.style.paddingLeft=10;b.style.paddingRight=10;b.style.flexShrink=0;
            b.style.backgroundColor=new Color(.10f,.14f,.18f);b.style.color=new Color(.91f,.94f,.97f);b.style.unityTextAlign=TextAnchor.MiddleLeft;
            b.style.borderTopWidth=b.style.borderBottomWidth=b.style.borderLeftWidth=b.style.borderRightWidth=0;
            b.style.borderTopLeftRadius=b.style.borderTopRightRadius=b.style.borderBottomLeftRadius=b.style.borderBottomRightRadius=6;
            return b;
        }
        public void Refresh()
        {
            var f=app.Flight;var c=app.Controls;var facade=app.Facade;
            menu.style.display=app.MenuOpen?DisplayStyle.Flex:DisplayStyle.None;controlsArea.SetEnabled(!app.MenuOpen);
            continueButton.style.display=app.HasSelectedLevel?DisplayStyle.Flex:DisplayStyle.None;
            menuSubtitle.text=app.HasSelectedLevel?"Zmiana poziomu rozpoczyna lot od nowa.":"Swobodny lot lub zadanie przy elewacji budynku";
            level.text=app.LevelName;source.text=app.IsChallenge?"Sterowanie: "+(facade.EegMode?"EEG / FBCCA":"test kliknięciami"):"Sterowanie: "+c.Source;
            connection.text=app.IsChallenge?$"{app.Fps:0} FPS   ·   Ruch co 1 metr":$"{app.Fps:0} FPS   ·   {app.Bci?.Status??"Podgląd"}";
            eegPanel.style.display=app.IsChallenge?DisplayStyle.Flex:DisplayStyle.None;
            challenge.style.display=app.IsChallenge?DisplayStyle.Flex:DisplayStyle.None;
            retry.style.display=app.IsChallenge?DisplayStyle.Flex:DisplayStyle.None;retry.text="Od nowa";
            if(app.IsChallenge)
            {
                status.text=FacadeTitle(facade);int seconds=Mathf.FloorToInt(facade.Elapsed);
                challengeStats.text=$"Wysokość {f.Position.y:0.0} / {FacadeSession.GoalHeight:0.0} m\nRuchy {facade.Moves} · Blokady {facade.Blocked}\nCzas {seconds/60:00}:{seconds%60:00} · bez limitu";
                hint.text=facade.Message;
                start.text=facade.Phase==FacadePhase.Paused?"Wznów [T]":facade.Phase==FacadePhase.Completed||facade.Phase==FacadePhase.Aborted?"Od nowa [T]":"Start [T]";
                start.SetEnabled(!facade.IsTrial&&facade.Phase!=FacadePhase.Moving&&(!facade.EegMode||app.Eeg.Connected));
                eegStatus.text=app.Eeg.Status+"\n"+app.Eeg.LastDecision;
#if UNITY_WEBGL && !UNITY_EDITOR
                eegConnect.text=app.Eeg.Connecting?"Łączenie…":app.Eeg.Connected?"Odłącz próbę EEG":"Użyj EEG z Interface";
#else
                eegConnect.text=app.Eeg.Connecting?"Łączenie…":app.Eeg.Connected?"Rozłącz BA MAXI 009":"Połącz BA MAXI 009";
#endif
                eegConnect.SetEnabled(!app.Eeg.Connecting);
                eegMode.text=facade.EegMode?"EEG → przełącz na test kliknięć":"TEST kliknięć → przełącz na EEG";
                eegMode.SetEnabled(!facade.IsTrial&&facade.Phase!=FacadePhase.Moving);
                trialWindow.text=$"Okno EEG: {facade.TrialDuration:0.0} s · odliczanie 2 s";
                trialLess.SetEnabled(!facade.IsTrial&&facade.TrialDuration>4);trialMore.SetEnabled(!facade.IsTrial&&facade.TrialDuration<10);
                cancelTrial.SetEnabled(facade.IsTrial);
                land.text="Pauza [L]";land.SetEnabled(facade.IsTrial||facade.Phase==FacadePhase.Moving);
                help.text=facade.EegMode?"Połącz czepek → Start → skup wzrok na jednym kwadracie.\nKażdy ruch wymaga nowej próby. ESC anuluje próbę.":"TEST BEZ EEG: Start → kliknij kwadrat → poczekaj 4 s.";
            }
            else
            {
                status.text=f.Touching?"Kontakt z przeszkodą":f.State;
                start.text="Start [T]";land.text="Ląduj [L]";start.SetEnabled(!f.Flying&&f.Position.y<=.05f);land.SetEnabled(f.Flying);
                help.text="RUCH   Strzałki · W/S wysokość · A/D obrót\nTEST BCI   1 góra · 2 dół · 3 przód · 4 obrót";
            }
            bci.style.display=stimuli.style.display=camera.style.display=app.IsChallenge?DisplayStyle.None:DisplayStyle.Flex;
            bci.text="BCI: "+(c.Armed?"włączone":"wyłączone")+" [B]";bci.style.backgroundColor=c.Armed?new Color(.12f,.45f,.36f):new Color(.10f,.14f,.18f);
            camera.text="Kamera: "+(app.Fpv?"FPV":"pościg")+" [V]";quality.text="Jakość: "+app.QualityName+" [F2]";
            emergency.text=app.IsChallenge?"Przerwij zadanie [SPACJA]":"Wyłącz silniki [SPACJA]";
            telemetry.text=app.IsChallenge?"Cel: linia dachu · Stała odległość od elewacji · Ruch tylko góra / dół / lewo / prawo":
                $"Wysokość {f.Position.y:0.0} m    ·    Prędkość {new Vector2(f.Velocity.x,f.Velocity.z).magnitude:0.0} m/s    ·    Swobodny lot";
            note.text=app.IsChallenge?facade.Message:app.Note;diagnostics.style.display=app.Diagnostics&&!app.MenuOpen?DisplayStyle.Flex:DisplayStyle.None;
            debug.text=$"Pad: {app.PadName}\nPozycja: {f.Position}\nOstatnie BCI: {c.Last}\nUDP przyjęte: {app.Bci?.Accepted??0} · pominięte: {app.Bci?.Rejected??0}";
            choiceOverlay.style.display=app.IsChallenge&&!app.MenuOpen&&(facade.ShowSquares||facade.Phase==FacadePhase.Countdown||facade.Phase==FacadePhase.Preparing||facade.Phase==FacadePhase.Classifying)?DisplayStyle.Flex:DisplayStyle.None;
            if(app.IsChallenge)
            {
                float w=Screen.width-320,h=Screen.height-124;
                Vector2[] positions={new Vector2(w/2-65,18),new Vector2(w/2-65,h-148),new Vector2(18,h/2-65),new Vector2(w-148,h/2-65)};
                for(int i=0;i<4;i++)
                {
                    var button=directionButtons[i];bool selected=facade.Selected==directions[i];
                    button.style.display=facade.ShowSquares?DisplayStyle.Flex:DisplayStyle.None;
                    button.pickingMode=facade.EegMode?PickingMode.Ignore:PickingMode.Position;
                    float hz=new[]{10.25f,14.75f,13.75f,14.25f}[i];
                    button.text=FacadeSession.Name(directions[i])+"\n"+(facade.EegMode?$"{hz:0.00} Hz":"1 metr");
                    float luminance=facade.EegMode?(Mathf.Floor((1+Mathf.Sin(2*Mathf.PI*hz*(facade.TrialDuration-facade.Remaining)))*115+25)/255f):.96f;
                    button.style.left=positions[i].x;button.style.top=positions[i].y;
                    button.style.backgroundColor=facade.EegMode?new Color(luminance,luminance,luminance):selected?new Color(.60f,.94f,.76f):new Color(.96f,.97f,.96f);
                    button.style.color=facade.EegMode&&luminance<.5f?Color.white:new Color(.035f,.08f,.065f);
                    Color border=selected?new Color(.12f,.73f,.43f):new Color(.52f,.60f,.59f);
                    button.style.borderTopColor=button.style.borderBottomColor=button.style.borderLeftColor=button.style.borderRightColor=border;
                }
                choiceClock.style.left=w/2-130;choiceClock.style.top=h/2-42;
                choiceClock.text=facade.Phase==FacadePhase.Countdown?$"Skup wzrok na kierunku\n{Mathf.CeilToInt(facade.Remaining)}":
                    facade.Phase==FacadePhase.Preparing?"Rozpoczynanie zapisu EEG…":
                    facade.Phase==FacadePhase.Classifying?"Analiza EEG · FBCCA…":
                    $"{facade.Remaining:0.0} s\n"+(facade.EegMode?"Patrz na jeden kwadrat":facade.Selected==MoveDirection.None?"Kliknij kierunek":"Wybrano: "+FacadeSession.Name(facade.Selected));
            }
        }
        static string FacadeTitle(FacadeSession facade)
        {
            switch(facade.Phase)
            {
                case FacadePhase.Countdown:return "Przygotuj się";
                case FacadePhase.Preparing:return "Zapis EEG";
                case FacadePhase.Classifying:return "Analiza EEG";
                case FacadePhase.Selecting:return "Wybierz kierunek";
                case FacadePhase.Moving:return "Ruch o 1 metr";
                case FacadePhase.Paused:return "Zadanie wstrzymane";
                case FacadePhase.Completed:return "Dach osiągnięty!";
                case FacadePhase.Aborted:return "Zadanie przerwane";
                default:return "Wejście na dach";
            }
        }
        public void Dispose(){if(owner)Object.DestroyImmediate(owner);if(settings)Object.DestroyImmediate(settings);}
    }
}
