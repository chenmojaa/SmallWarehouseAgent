# install-service.ps1 -- install HD backend as a Windows service via NSSM.
# Use this ONLY when you want the backend to run unattended (auto-start on boot, restart on crash).
# Local dev use case: skip this; just run scripts\start-all.ps1.
#
# Prereq: NSSM installed (https://nssm.cc). Either on PATH or set $NssmPath below.
# Run as Administrator.

param(
  [string]$ServiceName = 'hd-backend',
  [string]$NssmPath = 'nssm',                       # or full path like 'C:\Tools\nssm\nssm.exe'
  [string]$PythonExe = 'D:\one_agent\backend\.venv\Scripts\python.exe',
  [string]$WorkingDir = 'D:\one_agent\backend',
  [string]$BindHost = '127.0.0.1',
  [int]$Port = 8001,
  [string]$ExtraEnv = ''                            # e.g. 'HD_ACCESS_TOKEN=xxx'
)

$ErrorActionPreference = 'Stop'

# Sanity: nssm available
$null = & $NssmPath 2>$null
if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 2) {
  throw "nssm not found at '$NssmPath'. Install from https://nssm.cc or set -NssmPath."
}

if (& $NssmPath status $ServiceName 2>$null) {
  Write-Host "[nssm] service '$ServiceName' already exists, removing first ..." -Foreground Yellow
  & $NssmPath stop $ServiceName 2>$null | Out-Null
  & $NssmName = & $NssmPath remove $ServiceName confirm 2>$null
}

$args = '-m uvicorn app.main:app --host ' + $BindHost + ' --port ' + $Port

Write-Host "[nssm] installing '$ServiceName' ..." -Foreground Cyan
& $NssmPath install $ServiceName $PythonExe $args
& $NssmPath set $ServiceName AppDirectory $WorkingDir
& $NssmPath set $ServiceName DisplayName 'HD Knowledge Base Backend'
& $NssmPath set $ServiceName Description  'FastAPI + LangGraph + Chroma. Local-only; pair with vite dev or nginx static.'
& $NssmPath set $ServiceName Start SERVICE_AUTO_START
& $NssmPath set $ServiceName AppStdout '$WorkingDir\uvicorn.out.log'
& $NssmPath set $ServiceName AppStderr '$WorkingDir\uvicorn.err.log'
& $NssmPath set $ServiceName AppRotateFiles 1
& $NssmPath set $ServiceName AppRotateBytes 10485760        # 10MB
& $NssmPath set $ServiceName AppRotateOnline 1
& $NssmPath set $ServiceName DelayBetweenRestarts 5000      # 5s restart throttle
& $NssmPath set $ServiceName AppExit Default Restart

if ($ExtraEnv) {
  $kv = $ExtraEnv -split ';'
  foreach ($pair in $kv) {
    if ($pair -match '^([^=]+)=(.*)$') {
      & $NssmPath set $ServiceName AppEnvironmentExtra "${$($Matches[1])}=$($Matches[2])"
    }
  }
}

& $NssmPath start $ServiceName
Write-Host ''
Write-Host "[nssm] service '$ServiceName' started." -Foreground Green
Write-Host 'Useful commands:'
Write-Host "  nssm status $ServiceName"
Write-Host "  nssm restart $ServiceName"
Write-Host "  nssm stop   $ServiceName"
Write-Host "  nssm remove $ServiceName confirm"
Write-Host "  sc delete   $ServiceName"