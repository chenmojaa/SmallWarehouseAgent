# backup.ps1 -- snapshot data/ to D:\backups\hd\<timestamp>\. Keeps last 14 copies.
# Run as a Windows scheduled task (e.g. daily 03:00) for automated protection.
#
# Usage (manual):
#   powershell -ExecutionPolicy Bypass -File D:\one_agent\scripts\backup.ps1
# Usage (with custom root):
#   powershell -ExecutionPolicy Bypass -File D:\one_agent\scripts\backup.ps1 -BackupRoot E:\backups -KeepLast 30

param(
  [string]$BackupRoot = 'D:\backups\hd',
  [int]$KeepLast = 14,
  [string]$DataDir = 'D:\one_agent\data',
  [string]$ChromaDir = 'D:\one_agent\data\chroma'
)

$ErrorActionPreference = 'Stop'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$dest = Join-Path $BackupRoot $stamp
New-Item -ItemType Directory -Force -Path $dest | Out-Null

Write-Host "[backup] $DataDir -> $dest" -Foreground Cyan

# SQLite first: VACUUM INTO a clean snapshot to avoid WAL inconsistency.
$db = Join-Path $DataDir 'notes.db'
if (Test-Path $db) {
  $vac = Join-Path $dest 'notes.db'
  Write-Host '[backup] sqlite VACUUM INTO ...' -Foreground Cyan
  & 'D:\one_agent\backend\.venv\Scripts\python.exe' -c "import sqlite3, shutil; c=sqlite3.connect(r'$db'); c.execute('VACUUM INTO ?', (r'$vac',)); c.close(); print('  ok', '$vac')"
}

# Notes markdown cache
$notesSrc = Join-Path $DataDir 'notes'
if (Test-Path $notesSrc) {
  $notesDest = Join-Path $dest 'notes'
  robocopy $notesSrc $notesDest /MIR /NFL /NDL /NJH /NJS /NP /R:1 /W:1 | Out-Null
}

# Chroma: copy only when uvicorn is NOT running to avoid sqlite write conflict.
$port = Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue
if ($port -and (Test-Path $ChromaDir)) {
  Write-Host '[backup] WARN: backend listening on 8001, skipping Chroma copy (avoid lock). Stop backend first.' -Foreground Yellow
} elseif (Test-Path $ChromaDir) {
  $chromaDest = Join-Path $dest 'chroma'
  robocopy $ChromaDir $chromaDest /MIR /NFL /NDL /NJH /NJS /NP /R:1 /W:1 | Out-Null
  Write-Host '[backup] chroma copied' -Foreground Cyan
}

# Prune old backups
$existing = Get-ChildItem -Directory -Path $BackupRoot -ErrorAction SilentlyContinue |
  Sort-Object Name -Descending
if ($existing.Count -gt $KeepLast) {
  $toRemove = $existing | Select-Object -Skip $KeepLast
  foreach ($d in $toRemove) {
    Write-Host "[backup] prune $($d.Name)" -Foreground DarkGray
    Remove-Item -Recurse -Force $d.FullName
  }
}

Write-Host "[backup] done -> $dest" -Foreground Green