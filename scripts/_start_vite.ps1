$env:VITE_ALLOWED_HOSTS = "11gv92qt74799.vicp.fun,10.0.0.110,localhost,127.0.0.1"
$env:VITE_API_TARGET = "http://127.0.0.1:8001"

$stdout = "D:\one_agent\frontend\vite.out.log"
$stderr = "D:\one_agent\frontend\vite.err.log"
"" | Set-Content $stdout
"" | Set-Content $stderr

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "D:\one_agent\frontend\node_modules\.bin\vite.cmd"
$psi.Arguments = "--port","5174","--strictPort"
$psi.WorkingDirectory = "D:\one_agent\frontend"
$psi.UseShellExecute = $false
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.WindowStyle = "Hidden"
$psi.CreateNoWindow = $true

$proc = [System.Diagnostics.Process]::Start($psi)
Write-Host "  vite PID=$($proc.Id) on port 5174"

Start-Job -ScriptBlock { param($p, $f) while (-not $p.HasExited) { $l = $p.StandardOutput.ReadLine(); if ($null -ne $l) { Add-Content -Path $f -Value $l } } } -ArgumentList $proc, $stdout | Out-Null
Start-Job -ScriptBlock { param($p, $f) while (-not $p.HasExited) { $l = $p.StandardError.ReadLine(); if ($null -ne $l) { Add-Content -Path $f -Value $l } } } -ArgumentList $proc, $stderr | Out-Null
