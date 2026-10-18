using UnityEngine;

namespace Talon
{
    public enum FacadePhase { Ready, Countdown, Preparing, Selecting, Classifying, Moving, Waiting, Paused, Completed, Aborted }
    public enum MoveDirection { None, Up, Down, Left, Right }

    // Both input modes share collisions and the exact one-metre animation.
    // EEG decisions are accepted only after capture, never as continuous velocity.
    public sealed class FacadeSession
    {
        public const float CountdownDuration=2;
        public bool EegMode {get;set;}
        public float TrialDuration {get;set;}=4;
        public bool IsTrial=>Phase==FacadePhase.Countdown||Phase==FacadePhase.Preparing||Phase==FacadePhase.Selecting||Phase==FacadePhase.Classifying;
        public const float ChoiceDuration=4, MoveDuration=1.1f, GoalHeight=13.2f;
        public const float MinX=-5, MaxX=5, MinHeight=1.2f, Radius=.28f;
        public static readonly Rect[] Obstacles={
            new Rect(-5.5f,4.0f,7,.4f),new Rect(-1.5f,7.0f,7,.4f),new Rect(-5.5f,10.0f,6,.4f)};
        public FacadePhase Phase {get;private set;}=FacadePhase.Ready;
        public Vector3 Position {get;private set;}=new Vector3(0,MinHeight,0);
        public Vector3 Velocity {get;private set;}
        public MoveDirection Selected {get;private set;}
        public float Remaining {get;private set;}
        public float Elapsed {get;private set;}
        public int Moves {get;private set;}
        public int Blocked {get;private set;}
        public string Message {get;private set;}="Kliknij Start, a następnie wybierz jeden z czterech kwadratów.";
        public bool ShowSquares=>Phase==FacadePhase.Selecting;
        Vector3 from,to;
        float moveElapsed;
        FacadePhase pausedPhase;

        public void Reset()
        {
            Phase=FacadePhase.Ready;Position=new Vector3(0,MinHeight,0);Velocity=Vector3.zero;
            Selected=MoveDirection.None;Remaining=Elapsed=moveElapsed=0;Moves=Blocked=0;
            Message=EegMode?"Połącz czepek EEG, kliknij Start i patrz na jeden z czterech kwadratów.":"Kliknij Start, a następnie wybierz jeden z czterech kwadratów.";
        }
        public bool StartChoice()
        {
            if(Phase!=FacadePhase.Ready&&Phase!=FacadePhase.Waiting)return false;
            Phase=EegMode?FacadePhase.Countdown:FacadePhase.Selecting;Remaining=EegMode?CountdownDuration:ChoiceDuration;Selected=MoveDirection.None;Velocity=Vector3.zero;
            Message=EegMode?"Skup wzrok na wybranym kierunku. Za chwilę rozpocznie się próba EEG.":"Masz 4 sekundy na kliknięcie kierunku. Ruch nastąpi po zniknięciu kwadratów.";return true;
        }
        public bool Choose(MoveDirection direction)
        {
            if(EegMode||!ShowSquares||direction==MoveDirection.None)return false;
            Selected=direction;Message="Wybrano: "+Name(direction)+". Poczekaj na koniec 4 sekund.";return true;
        }
        public void Pause()
        {
            if(!IsTrial&&Phase!=FacadePhase.Moving)return;
            pausedPhase=Phase;Phase=FacadePhase.Paused;Velocity=Vector3.zero;Message="Zadanie wstrzymane.";
        }
        public void Resume()
        {
            if(Phase!=FacadePhase.Paused)return;
            if(pausedPhase!=FacadePhase.Moving)
            {Phase=FacadePhase.Waiting;StartChoice();}
            else {Phase=FacadePhase.Moving;Message="Dokończenie ruchu o 1 metr.";}
        }
        public void Abort()
        {Phase=FacadePhase.Aborted;Selected=MoveDirection.None;Velocity=Vector3.zero;Message="Zadanie przerwane. Kliknij Od nowa, aby wrócić na start.";}
        public void Tick(float dt)
        {
            if(dt<=0||Phase==FacadePhase.Ready||Phase==FacadePhase.Paused||Phase==FacadePhase.Completed||Phase==FacadePhase.Aborted)return;
            Elapsed+=dt;Velocity=Vector3.zero;
            if(Phase==FacadePhase.Countdown)
            {
                Remaining=Mathf.Max(0,Remaining-dt);
                if(Remaining<=.0001f){Phase=FacadePhase.Preparing;Message="Rozpoczynanie zapisu EEG…";}
                return;
            }
            if(Phase==FacadePhase.Selecting)
            {
                float used=Mathf.Min(dt,Remaining);Remaining=Mathf.Max(0,Remaining-used);dt-=used;
                if(Remaining>.0001f)return;
                Remaining=0;
                if(EegMode){Phase=FacadePhase.Classifying;Message="Analiza EEG · FBCCA…";return;}
                CommitChoice();
            }
            if(Phase!=FacadePhase.Moving)return;
            Vector3 previous=Position;moveElapsed=Mathf.Min(MoveDuration,moveElapsed+dt);
            float t=moveElapsed/MoveDuration;Position=Vector3.LerpUnclamped(from,to,t*t*(3-2*t));
            if(dt>0)Velocity=(Position-previous)/dt;
            if(moveElapsed>=MoveDuration)
            {
                Position=to;Velocity=Vector3.zero;Moves++;
                Phase=Position.y>=GoalHeight-.001f?FacadePhase.Completed:FacadePhase.Waiting;
                Message=Phase==FacadePhase.Completed?"Dach osiągnięty! Zadanie ukończone.":"Ruch wykonany. Kliknij Start, aby wybrać kolejny kierunek.";
            }
        }
        public bool BeginStimulating()
        {
            if(!EegMode||Phase!=FacadePhase.Preparing)return false;
            Phase=FacadePhase.Selecting;Remaining=TrialDuration;
            Message="Patrz na jeden kwadrat. EEG wybierze kierunek ruchu.";return true;
        }
        public bool ApplyEegDecision(MoveDirection direction)
        {
            if(!EegMode||Phase!=FacadePhase.Classifying||direction==MoveDirection.None)return false;
            Selected=direction;CommitChoice();return true;
        }
        public void TrialFailed(string error)
        {
            if(!IsTrial)return;
            Phase=FacadePhase.Waiting;Selected=MoveDirection.None;Remaining=0;Velocity=Vector3.zero;
            Message="Bez ruchu: "+error;
        }
        public void CancelTrial()
        {if(IsTrial)TrialFailed("próba anulowana.");}
        void CommitChoice()
        {
            if(Selected==MoveDirection.None){Phase=FacadePhase.Waiting;Message="Nie wybrano kierunku — dron pozostaje w miejscu.";return;}
            Vector3 offset=Selected==MoveDirection.Up?Vector3.up:Selected==MoveDirection.Down?Vector3.down:Selected==MoveDirection.Left?Vector3.left:Vector3.right;
            from=Position;to=from+offset;
            if(!CanMove(from,to))
            {Blocked++;Phase=FacadePhase.Waiting;Message="Ruch zablokowany przez przeszkodę lub granicę. Wybierz inny kierunek.";return;}
            moveElapsed=0;Phase=FacadePhase.Moving;Message="Ruch: "+Name(Selected)+" · 1 metr";
        }
        public static bool CanMove(Vector3 start,Vector3 target)
        {
            if(target.x<MinX-.001f||target.x>MaxX+.001f||target.y<MinHeight-.001f||target.y>GoalHeight+.001f)return false;
            // Swept rectangle test: thin obstacles cannot be skipped by a 1 m step.
            float loX=Mathf.Min(start.x,target.x)-Radius,hiX=Mathf.Max(start.x,target.x)+Radius;
            float loY=Mathf.Min(start.y,target.y)-Radius,hiY=Mathf.Max(start.y,target.y)+Radius;
            foreach(var obstacle in Obstacles)
                if(hiX>obstacle.xMin&&loX<obstacle.xMax&&hiY>obstacle.yMin&&loY<obstacle.yMax)return false;
            return true;
        }
        public static string Name(MoveDirection direction)
        {
            switch(direction){case MoveDirection.Up:return "GÓRA";case MoveDirection.Down:return "DÓŁ";case MoveDirection.Left:return "LEWO";case MoveDirection.Right:return "PRAWO";default:return "brak";}
        }
    }
}
