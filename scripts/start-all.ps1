# start-all.ps1 -- boot backend + vite, apply tunnel port-forward, tail logs.
# Run from a normal PowerShell (the portproxy step needs admin: a separate copy in scripts\start-all-admin.ps1).

$ErrorActionPreference = 'SilentlyContinue'
Set-Location D:\one_agent

Write-Host '== Stop any stale processes on 5174 / 8001 ==' -Foreground Cyan
Get-NetTCPConnection -LocalPort 5174 -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Force -Id $_.OwningProcess -ErrorAction SilentlyContinue }
Get-NetTCPConnection -LocalPort 8001 -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Force -Id $_.OwningProcess -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 1

Write-Host '== Boot backend (FastAPI on 0.0.0.0:8001) ==' -Foreground Cyan
Start-Process -FilePath 'D:\one_agent\backend\.venv\Scripts\python.exe' `
  -ArgumentList '-m','uvicorn','app.main:app','--host','0.0.0.0','--port','8001' `
  -WorkingDirectory 'D:\one_agent\backend' `
  -RedirectStandardOutput 'D:\one_agent\backend\uvicorn.out.log' `
  -RedirectStandardError  'D:\one_agent\backend\uvicorn.err.log' `
  -WindowStyle Hidden

Write-Host '== Boot frontend (Vite on 0.0.0.0:5174) ==' -Foreground Cyan
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

Write-Host '== Apply port-forward (must run as Administrator the first time) ==' -Foreground Cyan
& 'D:\one_agent\scripts\add-portproxy.ps1'

Write-Host ''
Write-Host 'External URL: http://11gv92qt74799.vicp.fun/' -Foreground Green
Write-Host 'Internal     : 10.0.0.110:28 -> 5174 (vite) -> /api/* -> 8001 (backend)' -Foreground Green
