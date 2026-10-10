# 交付物/03-代码/前端/运行前端测试.ps1 —— 一键跑前端（Vue）单元测试（离线）
#
# 本文件**必须带 UTF-8 BOM**：PowerShell 5.1 对无 BOM 的 UTF-8 按 ANSI 解析，
# 中文注释会被解析坏（同 `交付物/03-代码\测试\运行测试.ps1` 与 `启动.ps1` 的历史教训）。
#
# 环境（2026-10-10 实测）：
#   * Node v22.22.2（项目本机实测版本；node 在 PATH 或用 $env:FRONTEND_NODE 覆盖）
#   * vitest 3.2.7 ＋ jsdom（已登记进 `前端/package.json` 的 devDependencies）
#   * 测试**完全离线**：`fetch` 一律用替身（见 `测试/api.test.js` 的 stubFetch）
#
# 跑法：
#   powershell -File 交付物/03-代码/前端/运行前端测试.ps1
# 等价于：
#   cd 交付物/03-代码/前端 ; npx vitest run

$ErrorActionPreference = 'Stop'

$feDir = Split-Path -Parent $MyInvocation.MyCommand.Path          # …\交付物/03-代码/前端
Push-Location $feDir
$failed = 0
try {
    if (-not (Test-Path (Join-Path $feDir 'node_modules'))) {
        Write-Host '未找到 node_modules —— 先执行：npm install（本机首次）'
        exit 2
    }
    Write-Host '== 前端单测：vitest run =='
    npx vitest run
    if ($LASTEXITCODE -ne 0) { $failed++ }
}
finally {
    Pop-Location
}

Write-Host ''
if ($failed -gt 0) {
    Write-Host '存在失败：vitest 非零退出'
    exit 1
}
Write-Host '全部通过（vitest 退出码为 0）'
exit 0
