# start-all.ps1 -- boot backend + vite, tail logs. Supports 花生壳 HTTPS mapping.
# Run from a normal PowerShell.

$ErrorActionPreference = 'SilentlyContinue'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $RepoRoot 'backend'
$FrontendDir = Join-Path $RepoRoot 'frontend'

Set-Location $RepoRoot

Write-Host '== Stop any stale processes on 5174 / 5006 ==' -Foreground Cyan
Get-NetTCPConnection -LocalPort 5174 -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Force -Id $_.OwningProcess -ErrorAction SilentlyContinue }
Get-NetTCPConnection -LocalPort 5006 -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Force -Id $_.OwningProcess -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 1

Write-Host '== Boot backend (FastAPI on 0.0.0.0:5006) ==' -Foreground Cyan
Start-Process -FilePath (Join-Path $BackendDir '.venv\Scripts\python.exe') `
  -ArgumentList '-m','uvicorn','app.main:app','--host','0.0.0.0','--port','5006' `
  -WorkingDirectory $BackendDir `
  -RedirectStandardOutput (Join-Path $BackendDir 'uvicorn.out.log') `
  -RedirectStandardError  (Join-Path $BackendDir 'uvicorn.err.log') `
  -WindowStyle Hidden

Write-Host '== Wait for backend ==' -Foreground Cyan
$backendReady = $false
for ($i = 0; $i -lt 30; $i++) {
  try {
    $response = Invoke-WebRequest 'http://127.0.0.1:5006/api/health' -UseBasicParsing -TimeoutSec 1
    if ($response.StatusCode -eq 200) { $backendReady = $true; break }
  } catch { Start-Sleep -Seconds 1 }
}
if (-not $backendReady) { Write-Host 'Backend failed to start; see backend\uvicorn.err.log' -Foreground Red }

Write-Host '== Boot frontend (Vite on 127.0.0.1:5174) ==' -Foreground Cyan
Start-Process -FilePath 'cmd.exe' `
  -ArgumentList '/c','npm run dev' `
  -WorkingDirectory $FrontendDir `
  -RedirectStandardOutput (Join-Path $FrontendDir 'vite.out.log') `
  -RedirectStandardError  (Join-Path $FrontendDir 'vite.err.log') `
  -WindowStyle Hidden

Start-Sleep -Seconds 4

Write-Host '== Probe ==' -Foreground Cyan
try  { (Invoke-WebRequest 'http://127.0.0.1:5006/api/health' -UseBasicParsing -TimeoutSec 3).StatusCode | Out-Host } catch { Write-Host 'backend NOT up yet' }
try  { (Invoke-WebRequest 'http://127.0.0.1:5174/'         -UseBasicParsing -TimeoutSec 3).StatusCode | Out-Host } catch { Write-Host 'vite    NOT up yet' }

Write-Host ''
Write-Host 'Local URL: http://127.0.0.1:5174' -Foreground Green
Write-Host 'Backend  : http://127.0.0.1:5006/api/health' -Foreground Green
Write-Host '花生壳   : https://11gv92qt74799.vicp.fun' -Foreground Yellow
