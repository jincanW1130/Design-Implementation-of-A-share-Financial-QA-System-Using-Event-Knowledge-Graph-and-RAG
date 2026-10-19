# 工具\备份.ps1 —— 第 4 轮（11.2）备份入口（PowerShell 包装，逻辑在同目录 备份.py）
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File 工具\备份.ps1
#   powershell -ExecutionPolicy Bypass -File 工具\备份.ps1 -DryRun
#   powershell -ExecutionPolicy Bypass -File 工具\备份.ps1 -Out D:\ashare-backup
#   powershell -ExecutionPolicy Bypass -File 工具\备份.ps1 -Keep 7
#
# 产物默认落在 交付物\10-部署\备份\<时间戳>\（已 gitignore）。写文件前先探测
# CREATE/DROP DATABASE 权限：有则做「临时库导入回验」后删除临时库；DML-only 时
# 自动跳过回验（manifest verified=false）并仍以 exit 0 结束。正式库全程只读。
# 严格校验请直接运行 备份.py --require-verify（无 DDL 权限时 exit 1）。
# -Keep（默认 3）：只保留最近 N 份备份目录，更旧的由 备份.py 按安全边界清理。

param(
    [switch]$DryRun,
    [string]$Out = "",
    [int]$Keep = 3
)

$ErrorActionPreference = "Stop"
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
} catch {
    # 老版本 PowerShell 忽略即可
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "[FAIL] 找不到 python，请先加入 PATH。" -ForegroundColor Red
    exit 1
}

$script = Join-Path $PSScriptRoot "备份.py"
$arguments = @($script)
if ($DryRun) { $arguments += "--dry-run" }
if ($Out -ne "") { $arguments += @("--out", $Out) }
$arguments += @("--keep", "$Keep")

& $python.Source @arguments
exit $LASTEXITCODE
