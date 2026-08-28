# start-all.ps1 -- boot backend + vite, tail logs. Local-only (no public tunnel).
# Run from a normal PowerShell.

$ErrorActionPreference = 'SilentlyContinue'
Set-Location D:\one_agent

Write-Host '== Stop any stale processes on 5174 / 8001 ==' -Foreground Cyan
Get-NetTCPConnection -LocalPort 5174 -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Force -Id $_.OwningProcess -ErrorAction SilentlyContinue }
Get-NetTCPConnection -LocalPort 8001 -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Force -Id $_.OwningProcess -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 1

Write-Host '== Boot backend (FastAPI on 127.0.0.1:8001) ==' -Foreground Cyan
Start-Process -FilePath 'D:\one_agent\backend\.venv\Scripts\python.exe' `
  -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8001' `
  -WorkingDirectory 'D:\one_agent\backend' `
  -RedirectStandardOutput 'D:\one_agent\backend\uvicorn.out.log' `
  -RedirectStandardError  'D:\one_agent\backend\uvicorn.err.log' `
  -WindowStyle Hidden

Write-Host '== Wait for backend ==' -Foreground Cyan
$backendReady = $false
for ($i = 0; $i -lt 30; $i++) {
  try {
    $response = Invoke-WebRequest 'http://127.0.0.1:8001/api/health' -UseBasicParsing -TimeoutSec 1
    if ($response.StatusCode -eq 200) { $backendReady = $true; break }
  } catch { Start-Sleep -Seconds 1 }
}
if (-not $backendReady) { Write-Host 'Backend failed to start; see backend\uvicorn.err.log' -Foreground Red }

Write-Host '== Boot frontend (Vite on 127.0.0.1:5174) ==' -Foreground Cyan
Start-Process -FilePath 'cmd.exe' `
  -ArgumentList '/c','npm run dev' `
  -WorkingDirectory 'D:\one_agent\frontend' `
  -RedirectStandardOutput 'D:\one_agent\frontend\vite.out.log' `
  -RedirectStandardError  'D:\one_agent\frontend\vite.err.log' `
  -WindowStyle Hidden

Start-Sleep -Seconds 4

Write-Host '== Probe ==' -Foreground Cyan
try  { (Invoke-WebRequest 'http://127.0.0.1:8001/api/health' -UseBasicParsing -TimeoutSec 3).StatusCode | Out-Host } catch { Write-Host 'backend NOT up yet' }
try  { (Invoke-WebRequest 'http://127.0.0.1:5174/'         -UseBasicParsing -TimeoutSec 3).StatusCode | Out-Host } catch { Write-Host 'vite    NOT up yet' }

Write-Host ''
Write-Host 'Local URL: http://127.0.0.1:5174' -Foreground Green
Write-Host 'Backend  : http://127.0.0.1:8001/api/health' -Foreground Green
