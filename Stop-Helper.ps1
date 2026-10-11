$ErrorActionPreference = 'Stop'
$expected = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '.venv\Scripts\python.exe'))
foreach ($process in @(Get-CimInstance Win32_Process -Filter "Name='python.exe'")) {
    if ($process.ExecutablePath -and $process.ExecutablePath.Equals($expected, [StringComparison]::OrdinalIgnoreCase) -and $process.CommandLine -match '(?:helper[\\/]server\.py|helper[\\/]server\.py\")') {
        Stop-Process -Id $process.ProcessId -ErrorAction Stop
        Write-Host "Stopped this installation's helper."
    }
}
