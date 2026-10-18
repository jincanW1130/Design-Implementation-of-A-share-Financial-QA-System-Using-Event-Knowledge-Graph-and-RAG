# 工具\备份.ps1 —— 第 4 轮（11.2）备份入口（PowerShell 包装，逻辑在同目录 备份.py）
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File 工具\备份.ps1
#   powershell -ExecutionPolicy Bypass -File 工具\备份.ps1 -DryRun
#   powershell -ExecutionPolicy Bypass -File 工具\备份.ps1 -Out D:\ashare-backup
#
# 产物默认落在 交付物\10-部署\备份\<时间戳>\（已 gitignore），并自动做一次
# 「临时库导入回验」后删除临时库；正式库 ashare_qa 全程只读。

param(
    [switch]$DryRun,
    [string]$Out = ""
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

& $python.Source @arguments
exit $LASTEXITCODE
