# Run TALON in Unity

The Unity simulator source is in `unity/TalonURP`. It includes Free Flight
(Swobodny lot) and Facade Ascent (Wejście na dach). Docker and Interface are
not required for the native version. This player controls a simulated drone.
Generated players and Unity caches are excluded from Git; build locally below.

## 1. Windows prerequisites

1. Install Git and Unity Hub. Sign in and activate a suitable Unity license.
2. Install **Unity 6000.6.3f1**, including **Windows Build Support (IL2CPP)**.
   Install Visual Studio C++ build tools if Unity requests them.
3. For browser export, also install **WebGL Build Support**.
4. Python is optional for keyboard/click testing. Native BrainAccess EEG needs
   **64-bit Python 3.13**, including the Windows `py` launcher.

Unity resolves URP 17.6.0 and Input System 1.19.0 from the package configuration.
Initial package import and Python dependency installation require internet.

## 2. Clone and build

Open Windows PowerShell:

```powershell
git clone --branch talon-in-unity https://github.com/KN-Neuron/TALON.git
Set-Location TALON
powershell -NoProfile -ExecutionPolicy Bypass -File .\unity\tools\Unity.ps1 -Task Build
```

This copies the project to `%USERPROFILE%\TALON-Unity`, validates it and builds
`%USERPROFILE%\TALON-Unity\Builds\Windows\TALON.exe`. First import can take time.
The working directory must be new or contain the helper's `.talon-managed`
marker; an unrelated existing folder is refused.

If Unity is installed elsewhere, provide its executable on each Unity task:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\unity\tools\Unity.ps1 -Task Build -Editor 'D:\Unity\6000.6.3f1\Editor\Unity.exe'
```

Close the TALON Editor and game before rebuilding. Run tasks one at a time.

## 3. Run without a headset

```powershell
& "$env:USERPROFILE\TALON-Unity\Builds\Windows\TALON.exe"
```

- Choose **Swobodny lot**. **T** takes off, arrow keys move, **W/S** change
  height, **A/D** turn, **L** lands, **Space** cuts motors, **V** changes camera.
  Click inside the game if keyboard input does not respond.
- **Escape** opens the menu. For **Wejście na dach**, choose **test kliknięć**
  to test without a cap. Use **Start** for each trial and click a direction
  during its selection phase.
- Default EEG mode requires a headset; errors do not substitute synthetic EEG.

Python is not needed for keyboard/click testing. Direct executable launch uses
loopback BCI reception. The helper's `-Task Run` and generated
`Start-TALON.cmd` use `--bci-remote`, listening on all interfaces for optional
WSL commands; Windows Firewall may ask for permission.

## 4. Open in the Editor

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\unity\tools\Unity.ps1 -Task Open
```

Open `Assets/TalonGenerated/FreeFlight.unity` or
`Assets/TalonGenerated/FacadeAscent.unity`, then press Play. Environments are
created at runtime. Make C# changes in the repository's
`unity/TalonURP/Assets/Talon`. If editing the Windows working copy instead,
copy edits back before another helper invocation: the helper syncs repository
files into that copy. `-Task Open` does not copy edits back on exit.

## 5. Optional: BrainAccess EEG

After Build, run from the repository in Windows PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\unity\tools\Setup-EEG.ps1
& "$env:USERPROFILE\TALON-Unity\Builds\Windows\TALON.exe"
```

Setup creates `%USERPROFILE%\TALON-Unity\.eeg-venv` and installs
`eeg/requirements.txt`. Turn on Windows Bluetooth and the BrainAccess MAXI 009
cap; disconnect it from other applications. Choose **Wejście na dach** and
**Połącz BA MAXI 009**. Once connected, press **Start**. A two-second countdown
precedes a four-second recording, classification and one movement. Start a new
trial for each movement. Required montage and classifier details are documented
in [unity/README.md](unity/README.md).

## 6. Optional: repository in WSL

Unity uses a Windows-local working copy, created by the helper. From the TALON
repository in WSL:

```bash
powershell.exe -NoProfile -ExecutionPolicy Bypass -File \
  "$(wslpath -w "$PWD/unity/tools/Unity.ps1")" -Task Build \
  -Distro "$WSL_DISTRO_NAME" -LinuxSource "$PWD"
```

Pass your distro and repository path for subsequent tasks too. Defaults are the
original developer's `Ubuntu-24.04` and `/home/kacper/github/TALON`; these values
configure the optional Python SSVEP launcher. Native BrainAccess uses Windows
Python and Bluetooth, including when the source checkout is in WSL.

Only for the optional Python/SSVEP path, install WSL Python dependencies:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

## Validation and troubleshooting

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\unity\tools\Unity.ps1 -Task Validate
# Requires Setup-EEG.ps1 and a built player; uses synthetic EEG.
powershell -NoProfile -ExecutionPolicy Bypass -File .\unity\tools\Unity.ps1 -Task Smoke
```

- **Editor not found:** install the exact version or pass `-Editor`.
- **Unmarked workspace:** choose a new folder with `-Workspace`. Pass that same
  folder to every Unity task and Setup-EEG.ps1; adjust executable paths above.
- **Build failure:** inspect `unity/TalonURP/Logs/Build.log`. Close the working
  Editor/player and check installed Unity build modules.
- **Missing EEG environment:** install Python 3.13 and run Setup-EEG.ps1 after
  Build. Re-run setup after moving the workspace or changing dependencies.
- **Port 9001 busy:** close another TALON instance or the old Python UI.
- **Editor edits overwritten:** restore/copy changes into the repository before
  syncing the Windows working copy again.

See [the detailed Unity README](unity/README.md) for WebGL export, BCI protocol
and remaining controls. Physical headset behavior and stimulus timing require
separate validation on the intended hardware.
