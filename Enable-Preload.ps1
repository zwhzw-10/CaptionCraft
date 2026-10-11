$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run Install.cmd first.' }
$env:PIP_CACHE_DIR = Join-Path $PSScriptRoot '.cache\pip'
Write-Host 'Installing the public audio downloader...'
& $python -m pip install --upgrade 'yt-dlp[default]'
if ($LASTEXITCODE -ne 0) { throw 'Downloader installation failed.' }
$denoDir = Join-Path $PSScriptRoot 'tools\deno'
New-Item -ItemType Directory -Force -Path $denoDir | Out-Null
if (-not (Test-Path -LiteralPath (Join-Path $denoDir 'deno.exe'))) {
    Write-Host 'Downloading official Deno runtime...'
    $release = Invoke-RestMethod -Uri 'https://api.github.com/repos/denoland/deno/releases/latest' -Headers @{'User-Agent'='Local-English-Captions'}
    $asset = $release.assets | Where-Object { $_.name -eq 'deno-x86_64-pc-windows-msvc.zip' } | Select-Object -First 1
    if (-not $asset -or $asset.browser_download_url -notlike 'https://github.com/denoland/deno/releases/download/*') { throw 'Official Deno release asset unavailable.' }
    $zip = Join-Path $denoDir 'deno-download.zip'
    Invoke-WebRequest -UseBasicParsing -Uri $asset.browser_download_url -OutFile $zip
    if ($asset.digest -notmatch '^sha256:([0-9a-f]{64})$') { throw 'Official SHA256 digest missing; refusing to install unchecked runtime.' }
    $expected = $Matches[1]
    if ((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw 'Deno checksum mismatch.' }
    Expand-Archive -LiteralPath $zip -DestinationPath $denoDir -Force
    Remove-Item -LiteralPath $zip
}
& (Join-Path $denoDir 'deno.exe') --version
if ($LASTEXITCODE -ne 0) { throw 'Deno runtime failed.' }
Write-Host 'READY. Restart Start.cmd; choose Prepare captions in the extension.'
