# 交付物/03-代码\测试\运行测试.ps1 —— 一键跑本目录的单元测试（离线、只读产品代码）
#
# 本文件**必须带 UTF-8 BOM**：PowerShell 5.1 对无 BOM 的 UTF-8 按 ANSI 解析，
# 中文注释会被解析坏（同 `交付物/10-部署\启动.ps1` 的历史教训）。
#
# 两步都跑，缺一不可：
#   ① 全量：`python -m pytest 交付物/03-代码\测试 -q`（一次进程里加载检索／问答／后端三套同日名模块）
#   ② 逐文件：每个测试文件单独起一个进程——这是对"四个同名 config.py 串味"的实测防线：
#      分开跑与一起跑的读数必须一致。

$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'          # 中文输出在 GBK 控制台会乱码（不是失败）

$testDir = Split-Path -Parent $MyInvocation.MyCommand.Path          # …\交付物/03-代码\测试
$root = Split-Path -Parent (Split-Path -Parent $testDir)            # 工作区根
$files = @('test_0_module_isolation.py', 'test_a_five_step_contract.py',
           'test_b_retrieval_metrics.py', 'test_c_answer_assembly.py',
           'test_d_backend_errors.py')

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
Write-Host '全部通过（6 次运行的退出码均为 0）'
exit 0
