# Бэкап файловой базы 1С (правило проекта: бэкап перед ЛЮБЫМ изменением на машине с 1С).
# Использование:
#   powershell -NoProfile -File backup-1c.ps1 -BasePath C:\1c\bases\erp_test
#   powershell -NoProfile -File backup-1c.ps1 -BasePath C:\1c\bases\erp_test -Force   # игнорировать открытые сессии 1С
# Восстановление: распаковать zip обратно в каталог базы (при закрытой 1С).
param(
    [Parameter(Mandatory = $true)][string]$BasePath,
    [string]$BackupRoot = 'C:\1c\backups',
    [int]$Keep = 14,
    [switch]$Force
)
$ErrorActionPreference = 'Stop'
$log = 'C:\1c\logs\backup.log'
function Write-Log([string]$msg) {
    $line = "{0} {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    $line | Tee-Object -FilePath $log -Append
}

if (-not (Test-Path $BasePath)) { Write-Log "ERROR: база не найдена: $BasePath"; exit 1 }

# Открытая сессия 1С = риск неконсистентной копии файловой базы
$running = Get-Process -Name '1cv8*' -ErrorAction SilentlyContinue
if ($running -and -not $Force) {
    Write-Log "ABORT: запущены процессы 1С ($(($running.ProcessName | Select-Object -Unique) -join ', ')) — закрой 1С или используй -Force"
    exit 2
}

New-Item -ItemType Directory -Force -Path $BackupRoot, (Split-Path $log) | Out-Null
$baseName = Split-Path $BasePath -Leaf
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$zip = Join-Path $BackupRoot "$($baseName)_$stamp.zip"

Write-Log "START: $BasePath -> $zip"
Compress-Archive -Path (Join-Path $BasePath '*') -DestinationPath $zip -CompressionLevel Optimal
$sizeMb = [math]::Round((Get-Item $zip).Length / 1MB, 1)
Write-Log "DONE: $zip ($sizeMb MB)"

# Ротация: держим последние $Keep копий этой базы
Get-ChildItem $BackupRoot -Filter "$($baseName)_*.zip" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip $Keep |
    ForEach-Object { Write-Log "ROTATE: удаляю $($_.Name)"; Remove-Item $_.FullName }
