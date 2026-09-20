$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$EnvPath = Join-Path $Root ".env"
if (-not (Test-Path $EnvPath)) {
  Copy-Item (Join-Path $Root ".env.example") $EnvPath
  Write-Host "Creado .env local desde .env.example (sin secretos reales)."
}
Push-Location $Root
try { docker compose up -d postgres } finally { Pop-Location }
$Shell = (Get-Process -Id $PID).Path
Start-Process -FilePath $Shell -ArgumentList "-NoExit","-File",(Join-Path $Root "scripts\api.ps1")
Start-Sleep -Seconds 2
Start-Process -FilePath $Shell -ArgumentList "-NoExit","-File",(Join-Path $Root "scripts\web.ps1")
Write-Host "PostgreSQL iniciado. API: http://127.0.0.1:8000  Web: http://127.0.0.1:3000"
