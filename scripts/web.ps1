$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Web = Join-Path $Root "apps\web"
Push-Location $Web
try {
  if (-not (Test-Path "node_modules")) { npm install --no-audit --no-fund }
  npm run dev
} finally { Pop-Location }
