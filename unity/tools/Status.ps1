$ErrorActionPreference='Stop'
Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'Unity.exe' -and $_.CommandLine -like '*TALON-Unity*' } | ForEach-Object {
    $taskProcess=Get-Process -Id $_.ProcessId
    [pscustomobject]@{Id=$_.ProcessId; CPU=$taskProcess.CPU; MemoryMB=[int]($taskProcess.WorkingSet64/1MB); Responding=$taskProcess.Responding; Title=$taskProcess.MainWindowTitle; Command=$_.CommandLine}
} | Format-List
