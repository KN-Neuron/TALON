# TALON · Unity URP

The native Unity simulator for KN Interface. Unity owns the scene, UI, cameras
and rendering; Python remains available for EEG/BCI and the existing physical
drone backends. The Unity scene currently drives the **simulator**, not a real
aircraft. No real-drone commands are sent by this player.

## Project and working copy

- Source: `unity/TalonURP` in this repository.
- Editor: Unity **6000.6.3f1**, URP **17.6.0**, Input System **1.19.0**.
- Windows working copy: `C:\Users\egrac\TALON-Unity`.
- Scenes: `Assets/TalonGenerated/FreeFlight.unity` and
  `Assets/TalonGenerated/FacadeAscent.unity`; enter Play to generate the campus.
- Windows player: `C:\Users\egrac\TALON-Unity\Builds\Windows\TALON.exe`.

Unity rejected the WSL network filesystem, so `tools/Unity.ps1` copies only this
project to a marked Windows directory before invoking the Editor. It refuses
to reuse an existing directory without `.talon-managed`. It never enumerates,
modifies or closes other Unity projects. Library and builds stay in that working
copy; source GUIDs, generated assets and project settings return to this repo.

Use the repository as the source of truth for C# changes. The next invocation
copies repository assets to Windows; edits made only in the Windows working
copy should be copied back before running the script again.

From this repository in WSL:

```bash
powershell.exe -NoProfile -ExecutionPolicy Bypass -File \
  "$(wslpath -w "$PWD/unity/tools/Unity.ps1")" -Task Validate
```

Available tasks:

| Task | Purpose |
| --- | --- |
| `Import` | Resolve dependencies and compile scripts |
| `Validate` | Configure URP and run free-flight/UDP and facade selection/movement/collision checks |
| `Build` | Validate, then build the Windows player |
| `Smoke` | Exercise both levels, direction Button, timing, animation and UDP isolation |
| `Preview` | Render a campus image using the Editor |
| `Open` | Open only the TALON working project in the Editor |
| `Run` | Launch the built Windows simulator with WSL BCI reception |
| `Close` | Request a graceful close of only this project's built player |

Close this project's Editor before importing or building it. The script does
not close an Editor on your behalf. Do not run multiple tasks concurrently.

## Two levels

The game starts with a level selection menu. **Escape** opens/closes that menu;
changing the level resets flight and BCI arming. Each level has a separate scene
configuration. The menu switches the active environment immediately.

**01 / Swobodny lot:** the existing campus with pad, keyboard or BCI control.
No score or time limit; gates remain available for practice.

**02 / Wejście na dach:** a straight-on facade. The drone maintains a fixed depth
and moves only up/down/left/right. Reach the roof line at 13.2 m while avoiding
three projecting ledges. There is no time limit.

The default control mode uses **BrainAccess MAXI 009**, directly from TALON.
Interface includes an embedded WebGL edition of both TALON levels. That edition
uses Interface's existing device connection and classifier; connect the cap in
Interface's Device page and select **Użyj EEG z Interface** in the game. Its
standalone Windows installer bundles the games and native EEG helpers. The
Docker edition supports Simulation EEG and device-free click testing.

The native TALON player documented below also remains available independently.
It manages its own acquisition. When using that separate player, disconnect the
cap in Interface before connecting it in TALON so only one application owns it.

Set up the project-specific Windows Python environment once:

```powershell
# Run from this repository (Windows or its WSL UNC path).
.\unity\tools\Setup-EEG.ps1
```

This uses installed Python 3.13 and creates only `TALON-Unity/.eeg-venv`.
The game launches its own Python subprocess using `eeg-launcher.txt`; no EEG
network port or WSL Bluetooth access is needed. `Unity.ps1` syncs the EEG source.
Re-run setup after moving the Windows workspace or changing dependencies.

1. Turn on the cap and Windows Bluetooth. Choose **Połącz BA MAXI 009**.
2. Once connected, click **Start**. A **two-second countdown** precedes recording.
3. Four squares modulate their brightness for **four seconds** by default.
   Look at one direction; clicking the squares does not select an EEG command.
4. The squares disappear, then FBCCA classifies the captured EEG. One decision
   triggers one smooth **1 metre** movement (about 1.1 seconds).
5. Click **Start** again for the next movement. Obstacles and boundaries block
   the complete step. There is no automatic repetition.

The channel order is **POz, PO3, PO4, Oz, O1, O2** (MAXI 009 source indices
27, 26, 28, 30, 29, 31). Other montages/channel counts are rejected.
Direction frequencies match Miner: **up 10.25, left 13.75, right 14.25,
down 14.75 Hz**. Brightness follows `(1 + sin(2*pi*f*t))*115 + 25`.
The window is adjustable from **4 to 10 seconds**, in **0.5 s** steps.
FBCCA preserves Miner's DC removal, five Chebyshev filter-bank subbands, five
harmonics, sklearn CCA, and weighted squared correlations. It needs fs > 200 Hz.
Acquisition and classifier source attribution is in `eeg/NOTICE.md`.

Missing/flat/invalid EEG, too few samples (3 s allowance), process failure or a
lost connection produce no new movement. Cancelling, pausing, changing levels,
resetting or aborting invalidates pending results. **Escape** cancels an active
trial; otherwise it opens the menu. Resuming a paused trial starts a fresh
countdown/capture; a paused movement finishes the original one-metre endpoint.
**Space** aborts the exercise. Reaching the roof ends it; **Od nowa** resets it.

The explicit **test kliknięć** control mode retains the original four-second
click selection, without needing a cap. It does not fabricate EEG. The
`--talon-eeg-simulate` process flag is reserved for explicit smoke tests;
connection errors never fall back to synthetic data.

Stimulus timing uses unscaled render time and display vsync. Actual flicker
accuracy still needs validation on the target display; successful synthetic
classification is not a measurement of real-user gaze accuracy.

Use **Rozłącz BA MAXI 009** to release the device before opening Interface.

Run decoder/acquisition tests with `.venv/bin/python -m unittest discover -s eeg`.
`Unity.ps1 -Task Build` validates the flight and EEG state models; `-Task Smoke`
uses a clearly labelled synthetic six-channel source through the actual Python
subprocess and FBCCA, without connecting to a real cap.

## Controls (free flight)

- **T / L**: take off / land. **Space**: cut motors.
- **Arrows**: strafe and forward/back. **W/S**: climb/descend. **A/D**: yaw.
- **V**: chase camera / FPV. **B**: arm/disarm BCI.
- **1–4**: simulated BCI up/down/forward/right turn.
- **Escape**: level menu.
- **F1**: diagnostics. **F2**: low/balanced/high rendering. **P**: screenshot.
- PS4: left stick moves, right stick climbs/yaws; triangle/cross/circle/square
  take off/land/cut motors/photo; L1 toggles BCI. Other pads use equivalent buttons.
- Moving the pad or keyboard cancels BCI pulses and keeps manual priority for
  1.5 seconds. Pulses expire after 1 second. Disconnecting a pad disarms BCI and lands.

The free-flight model runs at 60 Hz independently of frame rendering. It preserves
velocity control, altitude hold, forgiving gate collisions and the eight-gate
course from `sim.py`. This is a training model, not calibrated aerodynamics.

## Python BCI and WSL

Unity accepts the original `{"cmd":"forward"}` packets on UDP **9001**.
Valid commands: `up`, `down`, `forward`, `rotate_right`, `stop`.
These BCI controls apply to **level 01 only**. BCI must be armed in the panel. Unity replies with `{"accepted":true/false}`
for parseable packets; `--check` verifies that acknowledgement. `stop` is
accepted even while disarmed, making it useful for a routing check. Malformed datagrams are dropped; processing is
bounded per frame. Port conflicts appear in the panel without silently disabling
all other controls. Close the old Python control panel before using the same port.

Local reception binds loopback by default. For a decoder in WSL NAT, launch the
player with `--bci-remote` (or `Start-TALON.cmd`); this explicitly binds all network
interfaces. Windows Firewall can require approval for the application. No firewall
rules are created by the project. The Editor opened by the helper also gets this flag.

```bash
# In WSL NAT, after arming BCI in Unity:
.venv/bin/python unity_bci.py stop --host windows --check  # verify Unity acknowledgement
.venv/bin/python unity_bci.py forward --host windows
.venv/bin/python ssvep.py --host windows
```

`--host windows` uses the default WSL gateway. With mirrored networking use
`--host 127.0.0.1`, or supply the Windows host IP explicitly. UDP delivery across
WSL/Windows depends on networking/firewall configuration; the panel's accepted
packet counter makes reception observable.

The **Bodźce SSVEP** button launches this repo's Python stimulus window through
the per-project launcher created by the helper. Stimulus timing must be validated
separately on the intended monitor. It is not inferred from simulator FPS.

## Rendering and scope

URP Lit materials, generated repeatable textures, alpha-clipped canopy cards,
native static batching, directional soft shadows, procedural sky, ACES grading,
MSAA and SMAA. The scene is rendered directly to the window; frame pixels are not
copied to Python. Tree trunks, buildings and gate frames block flight. Benches,
planters and lamps are decorative. All art is generated locally.

The Python application remains runnable. This migration does not replace its
Tello/MAVLink backends or claim to validate real flight, EEG decoding or research
stimulus accuracy. Physical-pad behavior requires a connected controller.

## Embedded Interface build

Run `unity/tools/Unity.ps1 -Task WebGL` to produce `Builds/WebGL` in the managed
Windows workspace. It includes both levels, disables compression and threads,
and uses a JavaScript bridge instead of subprocesses and UDP in the Web player.
The original Windows player keeps its native transport and EEG implementation.

In the Interface repository, copy the generated output with:

```powershell
python .\unity-patch\prepare_webgl_build.py `
  "$env:USERPROFILE\TALON-Unity\Builds\WebGL" `
  .\public\talon --product-name TALON
```

Interface's `build-standalone.ps1` packages both games and its three EEG helpers.
`docker compose up --build -d` serves both games with simulated devices and the
HTTP classifier. The embedded free-flight level retains keyboard/pad and BCI
test keys; rooftop training uses the shared EEG stream and FBCCA. External Python
stimulus launchers, UDP, and filesystem screenshots are native-player features.
Use the system screenshot tool for captures from the embedded edition.
