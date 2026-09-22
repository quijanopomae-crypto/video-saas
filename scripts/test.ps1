$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

Push-Location $Root
try { python -m pytest -q tests } finally { Pop-Location }

$Api = Join-Path $Root "apps\api"
$Venv = Join-Path $Api ".venv"
if (-not (Test-Path $Venv)) { python -m venv $Venv }
$Python = Join-Path $Venv "Scripts\python.exe"
& $Python -m pip install --disable-pip-version-check -r (Join-Path $Api "requirements.txt") -c (Join-Path $Api "requirements.lock.txt")
Push-Location $Api
try { & $Python -m pytest -q tests } finally { Pop-Location }

$Web = Join-Path $Root "apps\web"
Push-Location $Web
try {
  npm ci --no-audit --no-fund
  npm test
  npm run typecheck
  npm run build
} finally { Pop-Location }

Write-Host "Todas las validaciones locales terminaron."
