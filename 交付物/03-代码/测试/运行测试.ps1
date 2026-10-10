# 交付物/03-代码\测试\运行测试.ps1 —— 一键跑本目录的单元测试（离线、只读产品代码）
#
# 本文件**必须带 UTF-8 BOM**：PowerShell 5.1 对无 BOM 的 UTF-8 按 ANSI 解析，
# 中文注释会被解析坏（同 `交付物/10-部署\启动.ps1` 的历史教训）。
#
# 两步都跑，缺一不可：
#   ① 全量：`python -m pytest 交付物/03-代码\测试 -q`（一次进程里加载五套组件：检索／问答／
#      后端／数据准备／抽取与图谱——它们各有一份同名 `config.py`）
#   ② 逐文件：每个测试文件单独起一个进程——这是对"五个同名 config.py 串味"的实测防线：
#      分开跑与一起跑的读数必须一致。
#
# 前端（Vue）单测**不在本脚本**：它由 `交付物/03-代码\前端\` 的 vitest 跑（见 test G 组）。
# 一键跑本脚本后，另有 `前端\` 下 `npm test`（或 `运行前端测试.ps1`）。

$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'          # 中文输出在 GBK 控制台会乱码（不是失败）

$testDir = Split-Path -Parent $MyInvocation.MyCommand.Path          # …\交付物/03-代码\测试
# 上溯 3 层到**仓库根**（2026-10-10 修复：目录重组后本文件在 `<仓库>\交付物\03-代码\测试\`，
# 原 2 层会把 $root 算成 `<仓库>\交付物`，Push-Location 后 `交付物/03-代码\测试` 变成
# `交付物\交付物\…`、pytest 找不到路径；与 `启动.ps1` 的修复同型）。
$root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $testDir))   # 仓库根
$files = @('test_0_module_isolation.py', 'test_a_five_step_contract.py',
           'test_b_retrieval_metrics.py', 'test_c_answer_assembly.py',
           'test_d_backend_errors.py', 'test_e_data_prep.py',
           'test_f_extract_graph.py')

Push-Location $root
$failed = 0
try {
    Write-Host '== ① 全量：python -m pytest 交付物/03-代码\测试 -q =='
    python -m pytest '交付物/03-代码\测试' -q
    if ($LASTEXITCODE -ne 0) { $failed++ }

    Write-Host ''
    Write-Host '== ② 逐文件（分开跑也必须全过）=='
    foreach ($f in $files) {
        Write-Host ("-- " + $f)
        python -m pytest (Join-Path '交付物/03-代码\测试' $f) -q
        if ($LASTEXITCODE -ne 0) { $failed++ }
    }
}
finally {
    Pop-Location
}

Write-Host ''
if ($failed -gt 0) {
    Write-Host ("存在失败：{0} 次运行非零退出" -f $failed)
    exit 1
}
Write-Host ("全部通过（{0} 次运行的退出码均为 0）" -f ($files.Count + 1))
exit 0
