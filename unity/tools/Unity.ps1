param(
    [ValidateSet('Import','Validate','Build','WebGL','Open','Preview','Smoke','Run','Close')][string]$Task = 'Open',
    [string]$Editor = 'C:\Program Files\Unity\Hub\Editor\6000.6.3f1\Editor\Unity.exe',
    [string]$Workspace = (Join-Path $env:USERPROFILE 'TALON-Unity'),
    [string]$Distro = 'Ubuntu-24.04',
    [string]$LinuxSource = '/home/kacper/github/TALON'
)
$ErrorActionPreference = 'Stop'
$source = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\TalonURP'))
if (-not (Test-Path $Editor)) { throw "Unity Editor not found: $Editor" }
# Unity refuses a network/WSL project filesystem. Only this marked TALON mirror
# is managed; never reuse or touch an existing unrelated Unity project.
$marker = Join-Path $Workspace '.talon-managed'
if ((Test-Path $Workspace) -and -not (Test-Path $marker)) { throw "Refusing unmarked workspace: $Workspace" }
New-Item -ItemType Directory -Force -Path $Workspace | Out-Null
Set-Content -LiteralPath $marker -Value 'TALON Unity working copy'
foreach ($folder in @('Assets','Packages','ProjectSettings')) {
    & robocopy (Join-Path $source $folder) (Join-Path $Workspace $folder) /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -gt 7) { throw "Copy failed: $folder" }
}
if ($Task -eq 'Close') {
    $expected=[IO.Path]::GetFullPath((Join-Path $Workspace 'Builds\Windows\TALON.exe'))
    Get-Process -Name 'TALON' -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $expected } | ForEach-Object {
        if (-not $_.CloseMainWindow()) { throw 'TALON did not accept a close request.' }
        if (-not $_.WaitForExit(10000)) { throw 'Close the TALON game window before rebuilding.' }
    }
    exit 0
}
# An explicit per-project SSVEP launcher. No other Python project is invoked.
$launcher=Join-Path $Workspace 'Run-SSVEP.cmd'
Set-Content -LiteralPath $launcher -Encoding ASCII -Value @('@echo off',('wsl.exe --distribution "'+$Distro+'" --cd "'+$LinuxSource+'" -- .venv/bin/python ssvep.py --host windows'))
Set-Content -LiteralPath (Join-Path $Workspace 'bci-launcher.txt') -Value $launcher
$playerFolder=Join-Path $Workspace 'Builds\Windows'
if(Test-Path $playerFolder) {
    Set-Content -LiteralPath (Join-Path $playerFolder 'bci-launcher.txt') -Value $launcher
    Set-Content -LiteralPath (Join-Path $playerFolder 'Start-TALON.cmd') -Encoding ASCII -Value @('@echo off','cd /d "%~dp0"','start "TALON" "%~dp0TALON.exe" --bci-remote')
}
# Keep TALON's own acquisition/classifier scripts beside its private Python venv.
$eegSource=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\eeg'))
$eegDestination=Join-Path $Workspace 'EEG'
New-Item -ItemType Directory -Force -Path $eegDestination | Out-Null
& robocopy $eegSource $eegDestination '*.py' '*.txt' '*.md' /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
if($LASTEXITCODE -gt 7) { throw 'Copy EEG source failed.' }
$eegConfig=Join-Path $Workspace 'eeg-launcher.txt'
if((Test-Path $eegConfig) -and (Test-Path $playerFolder)) {
    Copy-Item -LiteralPath $eegConfig -Destination (Join-Path $playerFolder 'eeg-launcher.txt')
}
$logs = Join-Path $source 'Logs' 
New-Item -ItemType Directory -Force -Path $logs | Out-Null
if ($Task -eq 'Run') {
    $player=Join-Path $Workspace 'Builds\Windows\TALON.exe'
    if (-not (Test-Path $player)) { throw 'Build TALON first.' }
    Write-Output "Starting TALON: $player"
    Start-Process -FilePath $player -ArgumentList @('--bci-remote','-logFile',('"'+(Join-Path $logs 'Player.log')+'"')) -Wait | Out-Null
    Write-Output "Started TALON: $player"
    exit 0
}
if ($Task -eq 'Smoke') {
    $eegPython=Join-Path $Workspace '.eeg-venv\Scripts\python.exe'
    if(-not(Test-Path $eegPython)) { throw 'Run Setup-EEG.ps1 before the EEG smoke test.' }
    & $eegPython -m unittest discover -s $eegDestination -p 'test_*.py'
    if($LASTEXITCODE -ne 0) { throw 'TALON EEG decoder tests failed.' }
    $player=Join-Path $Workspace 'Builds\Windows\TALON.exe'
    if (-not (Test-Path $player)) { throw 'Build TALON first.' }
    $run=Start-Process -FilePath $player -ArgumentList @('--talon-smoke','--talon-eeg-simulate','--bci-remote','-screen-width','1600','-screen-height','900','-screen-fullscreen','0','-logFile',('"'+(Join-Path $logs 'Player-smoke.log')+'"')) -Wait -PassThru
    if ($run.ExitCode -ne 0) { throw "TALON smoke failed: $($run.ExitCode)" }
    & robocopy (Join-Path $Workspace 'Builds\Windows\Captures') $logs '*.png' /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
    exit 0
}
$arguments = @('-projectPath',('"'+$Workspace+'"'),'--bci-remote')
if ($Task -eq 'Open') {
    Start-Process -FilePath $Editor -ArgumentList $arguments -Wait | Out-Null
    Write-Output "Opened TALON: $Workspace"
    exit 0
}
$arguments += @('-batchmode','-quit','-buildTarget',$(if($Task -eq 'WebGL'){'WebGL'}else{'StandaloneWindows64'}),'-logFile',('"'+(Join-Path $logs "$Task.log")+'"'))
if ($Task -eq 'Import') { $arguments += '-nographics' }
if ($Task -eq 'Validate') { $arguments += @('-nographics','-executeMethod','Talon.Editor.ProjectTools.Validate') }
if ($Task -eq 'Build') { $arguments += @('-executeMethod','Talon.Editor.ProjectTools.Build') }
if ($Task -eq 'WebGL') { $arguments += @('-executeMethod','Talon.Editor.ProjectTools.BuildWebGL') }
if ($Task -eq 'Preview') { $arguments += @('-executeMethod','Talon.Editor.ProjectTools.Preview') }
$process = Start-Process -FilePath $Editor -ArgumentList $arguments -Wait -PassThru
if ($process.ExitCode -ne 0) { throw "Unity $Task failed ($($process.ExitCode)). See $logs\$Task.log" }
# Preserve project-scoped configuration, GUIDs and generated scene assets.
& robocopy (Join-Path $Workspace 'ProjectSettings') (Join-Path $source 'ProjectSettings') /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
& robocopy (Join-Path $Workspace 'Assets') (Join-Path $source 'Assets') '*.meta' /S /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
if (Test-Path (Join-Path $Workspace 'Assets\TalonGenerated')) {
    & robocopy (Join-Path $Workspace 'Assets\TalonGenerated') (Join-Path $source 'Assets\TalonGenerated') /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
}
& robocopy (Join-Path $Workspace 'Packages') (Join-Path $source 'Packages') 'packages-lock.json' /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
& robocopy (Join-Path $Workspace 'Logs') $logs '*.png' /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
if((Test-Path $eegConfig) -and (Test-Path $playerFolder)) {
    Copy-Item -LiteralPath $eegConfig -Destination (Join-Path $playerFolder 'eeg-launcher.txt')
}
Write-Output "TALON $Task completed: $Workspace"
exit 0
