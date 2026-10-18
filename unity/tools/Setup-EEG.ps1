param([string]$Workspace=(Join-Path $env:USERPROFILE 'TALON-Unity'))
$ErrorActionPreference='Stop'
if(-not(Test-Path (Join-Path $Workspace '.talon-managed'))) { throw 'Najpierw utwórz kopię TALON przez Unity.ps1 -Task Build.' }
$source=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\eeg'))
$destination=Join-Path $Workspace 'EEG'
New-Item -ItemType Directory -Force -Path $destination | Out-Null
& robocopy $source $destination '*.py' '*.txt' '*.md' /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
if($LASTEXITCODE -gt 7) { throw 'Nie udało się skopiować kodu EEG.' }
$venv=Join-Path $Workspace '.eeg-venv'
$python=Join-Path $venv 'Scripts\python.exe'
if(-not(Test-Path $python)) {
    & py -3.13 -m venv $venv
    if($LASTEXITCODE -ne 0) { throw 'Nie udało się utworzyć środowiska Python 3.13.' }
}
& $python -m pip install -r (Join-Path $destination 'requirements.txt')
if($LASTEXITCODE -ne 0) { throw 'Instalacja zależności EEG nie powiodła się.' }
& $python -c 'from brainaccess import core; import numpy, scipy, sklearn; print(1)'
if($LASTEXITCODE -ne 0) { throw 'Nie można załadować SDK BrainAccess.' }
$config=@($python,(Join-Path $destination 'talon_eeg.py'))
Set-Content -LiteralPath (Join-Path $Workspace 'eeg-launcher.txt') -Value $config -Encoding UTF8
$player=Join-Path $Workspace 'Builds\Windows'
if(Test-Path $player) { Set-Content -LiteralPath (Join-Path $player 'eeg-launcher.txt') -Value $config -Encoding UTF8 }
Write-Output 'TALON EEG gotowe. W grze wybierz Wejście na dach i Połącz BA MAXI 009.'
