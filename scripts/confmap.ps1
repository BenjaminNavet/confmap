# Lanceur Windows : démarre le serveur s'il ne tourne pas, puis ouvre la page.
param([int]$Port = 8010)

$ProjectDir = Split-Path -Parent $PSScriptRoot
$Url = "http://localhost:$Port"
$LogDir = Join-Path $env:LOCALAPPDATA "confmap"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir "confmap.log"

function Test-Server {
    try { Invoke-WebRequest -Uri "$Url/" -UseBasicParsing -TimeoutSec 1 | Out-Null; return $true }
    catch { return $false }
}

if (-not (Test-Server)) {
    Start-Process -FilePath "uv" -ArgumentList "run", "confmap", "serve", "--port", $Port `
        -WorkingDirectory $ProjectDir -WindowStyle Hidden `
        -RedirectStandardOutput $Log -RedirectStandardError "$Log.err"
    for ($i = 0; $i -lt 240; $i++) {
        if (Test-Server) { break }
        Start-Sleep -Milliseconds 500
    }
}
if (-not $env:CONFMAP_NO_OPEN) { Start-Process $Url }
