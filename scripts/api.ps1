$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Api = Join-Path $Root "apps\api"
$Venv = Join-Path $Api ".venv"
if (-not (Test-Path $Venv)) { python -m venv $Venv }
$Python = Join-Path $Venv "Scripts\python.exe"
& $Python -m pip install --disable-pip-version-check -r (Join-Path $Api "requirements.txt")
Push-Location $Api
try { & $Python -m uvicorn src.main:app --reload --host 127.0.0.1 --port 8000 }
finally { Pop-Location }
