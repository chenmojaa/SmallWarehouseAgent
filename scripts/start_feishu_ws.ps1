$ErrorActionPreference = "Stop"
$logDir = "D:\one_agent\logs"
New-Item -Path $logDir -ItemType Directory -Force | Out-Null
$logFile = Join-Path $logDir "feishu_ws.log"
$errFile = Join-Path $logDir "feishu_ws.err"
$pidFile = Join-Path $logDir "feishu_ws.pid"
Remove-Item -Force $logFile, $errFile -ErrorAction SilentlyContinue
$ps = Start-Process -FilePath "python" `
    -ArgumentList @("-u", "D:\one_agent\scripts\feishu_ws.py") `
    -RedirectStandardOutput $logFile `
    -RedirectStandardError $errFile `
    -PassThru `
    -WindowStyle Hidden
Set-Content -Path $pidFile -Value $ps.Id
Write-Host ("Started PID {0}" -f $ps.Id)
