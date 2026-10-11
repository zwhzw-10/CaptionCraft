$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:HF_HUB_OFFLINE = '0'
$env:HF_HUB_DISABLE_TELEMETRY = '1'
$env:PIP_CACHE_DIR = Join-Path $PSScriptRoot '.cache\pip'
function Invoke-Checked([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed: $Program (exit $LASTEXITCODE)" }
}
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    Write-Host '[1/5] Finding 64-bit Python...'
    $candidates = @()
    foreach ($version in @('311', '312', '310')) {
        $candidates += @{exe=(Join-Path $env:LOCALAPPDATA "Programs\Python\Python$version\python.exe");prefix=@()}
        $candidates += @{exe=(Join-Path $env:ProgramFiles "Python$version\python.exe");prefix=@()}
    }
    $candidates += @(@{exe='py';prefix=@('-3.11')}, @{exe='py';prefix=@('-3.12')}, @{exe='python';prefix=@()})
    $chosen = $null
    foreach ($candidate in $candidates) {
        if (Get-Command $candidate.exe -ErrorAction SilentlyContinue) {
            $probeArguments = $candidate.prefix + @('-c', 'import sys; assert (3,10) <= sys.version_info[:2] <= (3,12) and sys.maxsize > 2**32; print(sys.executable)')
            & $candidate.exe @probeArguments
            if ($LASTEXITCODE -eq 0) { $chosen = $candidate; break }
        }
    }
    if (-not $chosen) { throw 'Install 64-bit Python 3.11 or 3.12 from https://www.python.org/downloads/windows/ (enable Add Python to PATH), then run Install.cmd again.' }
    Write-Host '[2/5] Creating local Python environment...'
    Invoke-Checked $chosen.exe ($chosen.prefix + @('-m', 'venv', '.venv'))
}
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
Write-Host '[3/5] Installing recognition dependencies...'
Invoke-Checked $python @('-m', 'pip', 'install', '--upgrade', 'pip')
Invoke-Checked $python @('-m', 'pip', 'install', '-r', 'helper\requirements.txt')
Invoke-Checked $python @('helper\setup_config.py')
& (Join-Path $PSScriptRoot 'Enable-Preload.ps1')
Write-Host '[4/5] Downloading and testing the multilingual model...'
Invoke-Checked $python @('helper\server.py', '--model', 'base', '--download')
Write-Host '[5/5] READY. Next: Start.cmd, then chrome://extensions -> Load unpacked -> extension folder.'
