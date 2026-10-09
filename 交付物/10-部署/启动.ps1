<#
.SYNOPSIS
    第 9 阶段（前后端系统集成）一键启动脚本。

.DESCRIPTION
    依据《24-第9阶段任务书（前后端系统集成）》第4.4节 与第八节 H 组验收（H1）。
    依次做四件事，每步打印实测结果，最后打印健康检查：

      ① MySQL    —— 检查服务与 3306，并用后端配置连一次库（六张表行数）
      ② Neo4j    —— WSL2 内启动 Docker Engine ＋ 容器 ashare-neo4j，等 bolt 7687 就绪
      ③ 后端     —— 8000 端口起 uvicorn（已占用则复用，不重复起）
      ④ 前端     —— 5173 端口起 Vite dev server（已占用则复用）

    已知环境限制（如实登记，见 交付物/10-部署\README.md）：
      · 本机**未安装 Docker Desktop**（需要管理员权限），Docker 只以 **WSL2 内的 Engine** 形态可用；
      · WSL2 发行版会在**最后一次 wsl 调用结束后约 10～15 秒**挂起，挂起后 bolt 7687 由可达转为
        连接被拒；容器 `ashare-neo4j` 会被**优雅停止**再由 `unless-stopped` 拉起（2026-10-04 实测：
        `docker inspect` 的 `RestartCount=0` 且 `FinishedAt` 非空、日志为
        `Neo4j Server shutdown initiated by request`）。本脚本**默认不保活**——需要长跑时加
        `-KeepAlive`（见 .PARAMETER），或按 `交付物/10-部署\README.md` §三.3 另开一个 WSL 会话常驻；
      · WSL 服务偶发进入 `Wsl/Service/E_UNEXPECTED`，此时先 `wsl --shutdown` 再重跑本脚本；
        若 `wsl --shutdown` 自身挂死（实测过一次），只能由管理员会话或重启机器恢复。

.PARAMETER NoFrontend
    只起 MySQL／Neo4j／后端，不起前端。

.PARAMETER KeepAlive
    额外起一个**常驻 WSL 会话**（`wsl -d Ubuntu -u root -- sleep 7200`）顶住 VM 空闲挂起，**默认关**。
    不开它时，Neo4j 会在最后一次 wsl 调用结束后约 10～15 秒变得不可达（见上面第 2 条环境限制）；
    由本开关起的进程可用 `-Stop` 停掉。

.PARAMETER Stop
    停掉本脚本起的前端与后端进程，以及 `-KeepAlive` 起的保活会话（Neo4j 容器保持运行）。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File 交付物/10-部署\启动.ps1
#>
[CmdletBinding()]
param(
    [switch]$NoFrontend,
    [switch]$KeepAlive,
    [switch]$Stop
)

$ErrorActionPreference = "Continue"

# **控制台编码自设（不要依赖调用方的代码页）**：本脚本要读子进程输出并做中文比对
# （例如 `python 交付物/03-代码\后端\db.py` 打印的「六张表行数」）。后端脚本自身会把 stdout 切到 UTF-8，
# 而 Windows PowerShell 5.1 默认按 **系统 ANSI（本机 gb2312）** 解码原生命令输出 —— 两者不一致时
# 中文比对会落空，出现「六张表可读=False」这类**假失败**（第 9 阶段门禁 H1 行实测抓到过：
# 同一份脚本在 UTF-8 控制台下通过、在 gb2312 控制台下失败）。故在此显式把控制台输出编码设为 UTF-8。
try {
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
    $OutputEncoding = New-Object System.Text.UTF8Encoding($false)
} catch {
    Write-Host "[ !! ] 控制台编码设置失败（继续执行，中文比对可能不准）：$($_.Exception.Message)"
}

# **把 wsl.exe 的输出编码也在此处就定下来**：`WSL_UTF8` 原先只在下面的 Invoke-Wsl() 函数里设，而 ② 那行
# `wsl.exe -l -v` 自诊断在该函数被调用**之前**就跑了 —— 此时 wsl.exe 吐 UTF-16LE、被 PS 5.1 按 UTF-8
# 解码成乱码，正则匹配不到发行版行。故提前到此处，与上面的控制台编码一起定死。
$env:WSL_UTF8 = 1

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Distro = "Ubuntu"
$Container = "ashare-neo4j"
$BackendPort = 8000
$FrontendPort = 5173
$LogDir = Join-Path $Root "交付物/05-系统实现/前后端系统集成\_工作底稿"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Say($msg, $ok) {
    $tag = if ($ok -eq $null) { "····" } elseif ($ok) { " OK " } else { " !! " }
    Write-Host ("[{0}] {1}" -f $tag, $msg)
}
function Port($p) { (Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | Measure-Object).Count }
function Keepers() {
    # 本脚本 -KeepAlive 起的常驻 WSL 会话（命令行形如 wsl.exe -d Ubuntu -u root -- sleep 7200）
    @(Get-CimInstance Win32_Process -Filter "Name='wsl.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match 'sleep\s+7200' })
}
function Invoke-Wsl([string]$cmd, [int]$timeoutSec = 120) {
    # WSL 调用一律包在作业里并设超时：实测 WSL 偶发无响应，裸调会挂住整个脚本。
    # **函数名刻意不叫 Wsl**：PowerShell 的函数名大小写不敏感，一旦叫 `Wsl`，脚本里所有裸写的
    # `wsl ...` 都会被劫持成对这个函数的调用（2026-10-04 实测踩到，详见 ② 处 `wsl.exe -l -v` 的注释）。
    # 作业内是独立进程、`wsl` 本就指向 wsl.exe，但这里仍显式写 `wsl.exe` 以免再被误读。
    $env:WSL_UTF8 = 1
    $job = Start-Job -ScriptBlock { param($d, $c) wsl.exe -d $d -u root -- bash -lc $c 2>&1 } -ArgumentList $Distro, $cmd
    $done = Wait-Job $job -Timeout $timeoutSec
    $out = if ($done) { Receive-Job $job } else { "WSL 无响应（>$timeoutSec s）" }
    Remove-Job $job -Force -ErrorAction SilentlyContinue
    return ($out | Out-String).Trim()
}

if ($Stop) {
    Say "停止后端与前端进程" $null
    foreach ($p in @($BackendPort, $FrontendPort)) {
        Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique |
            ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
    }
    Start-Sleep -Seconds 2
    $kp = Keepers
    foreach ($k in $kp) { Stop-Process -Id $k.ProcessId -Force -ErrorAction SilentlyContinue }
    Say ("保活会话已停：{0} 个" -f $kp.Count) $true
    Say ("后端 {0} 监听数={1}；前端 {2} 监听数={3}" -f $BackendPort, (Port $BackendPort), $FrontendPort, (Port $FrontendPort)) `
        ((Port $BackendPort) -eq 0 -and (Port $FrontendPort) -eq 0)
    return
}

Write-Host ("=" * 78)
Write-Host "第 9 阶段一键启动（工作区：$Root）"
Write-Host ("=" * 78)

# ---------- ① MySQL ----------
Write-Host "`n① MySQL"
$svc = Get-Service -Name "MySQL*" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($svc) {
    Say ("服务 {0} 状态={1}；3306 监听数={2}" -f $svc.Name, $svc.Status, (Port 3306)) ($svc.Status -eq "Running")
} else {
    Say "未找到 MySQL 服务（请确认已安装并启动）" $false
}
$dbOut = & python (Join-Path $Root "交付物/03-代码\后端\db.py") 2>&1 | Out-String
$dbOut.Trim().Split("`n") | Select-Object -Last 4 | ForEach-Object { Write-Host "      $($_.Trim())" }
Say ("六张表可读={0}" -f ($dbOut -match "六张表行数")) ($dbOut -match "六张表行数")

# ---------- ② Neo4j（WSL2 内的 Docker Engine） ----------
Write-Host "`n② Neo4j（WSL2 ＋ Docker Engine）"
# **必须写 wsl.exe，不能裸写 wsl**：本脚本上面定义了 `function Invoke-Wsl`，而 PowerShell 的函数名
# **大小写不敏感** —— 在本文件的历史版本里那个函数就叫 `Wsl`，于是裸写 `wsl -l -v` 会被解析成对
# **本脚本那个函数**的调用（实参 `-l`／`-v`），根本碰不到 wsl.exe。2026-10-04 用落盘取证抓到实证：
# 它返回的是作业里 `bash -lc` 少参数的报错「bash: -c: option requires an argument」，
# 正则自然匹配不到发行版行 —— 也就是说这行自诊断**从来没有打印对过**。
$wslLines = @((wsl.exe -l -v 2>&1 | Out-String) -split "`r?`n" | Where-Object { $_ -match "\*\s+$Distro" })
if ($wslLines.Count -gt 0) { $wslState = $wslLines[0].Trim() }
else { $wslState = "（未从 wsl -l -v 解析到 $Distro 行，本步改按容器实况判定）" }
Say "WSL 发行版：$wslState" $null
$r = Invoke-Wsl "systemctl start docker 2>/dev/null; docker start $Container 2>&1 | tail -1; docker ps --filter name=$Container --format '{{.Names}} {{.Status}}'"
Say ("容器：{0}" -f ($r -replace "`r?`n", " / ")) ($r -match "Up")
$bolt = $false
for ($i = 1; $i -le 20; $i++) {
    Start-Sleep -Seconds 3
    $t = Test-NetConnection -ComputerName 127.0.0.1 -Port 7687 -InformationLevel Quiet -WarningAction SilentlyContinue
    if ($t) { $bolt = $true; break }
}
Say ("bolt 7687 可达={0}（等待 {1} 轮）" -f $bolt, $i) $bolt

if ($KeepAlive) {
    $kp = Keepers
    if ($kp.Count -gt 0) {
        Say ("保活会话已存在（pid {0}），不重复起" -f $kp[0].ProcessId) $true
    } else {
        try {
            $p = Start-Process -FilePath "wsl.exe" -ArgumentList @("-d", $Distro, "-u", "root", "--", "sleep", "7200") `
                -WindowStyle Hidden -PassThru
            Start-Sleep -Seconds 3
            Say ("已起保活会话 pid={0}（sleep 7200 ≈ 2 小时；用 -Stop 停）" -f $p.Id) (-not $p.HasExited)
        } catch {
            Say ("保活会话未起成：{0}" -f $_.Exception.Message) $null
        }
    }
} else {
    Say "未启用保活（-KeepAlive 可开）；WSL 空闲约 10～15 秒后挂起，Neo4j 将不可达（见 交付物/10-部署\README.md §三.3）" $null
}

# ---------- ③ 后端 ----------
Write-Host "`n③ 后端（8000）"
if ((Port $BackendPort) -gt 0) {
    Say "8000 已在监听，复用现有进程（不重复起）" $true
} else {
    Start-Process -FilePath "python" -ArgumentList "交付物/03-代码\后端\run.py" -WorkingDirectory $Root -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $LogDir "后端启动_stdout.log") `
        -RedirectStandardError (Join-Path $LogDir "后端启动_stderr.log")
    for ($i = 1; $i -le 20; $i++) { Start-Sleep -Seconds 1; if ((Port $BackendPort) -gt 0) { break } }
    Say ("后端已起（等待 {0} s）" -f $i) ((Port $BackendPort) -gt 0)
}

# ---------- ④ 前端 ----------
if (-not $NoFrontend) {
    Write-Host "`n④ 前端（5173）"
    if ((Port $FrontendPort) -gt 0) {
        Say "5173 已在监听，复用现有进程" $true
    } elseif (Test-Path (Join-Path $Root "交付物/03-代码\前端\node_modules")) {
        Start-Process -FilePath "cmd.exe" -ArgumentList "/c npm run dev" -WorkingDirectory (Join-Path $Root "交付物/03-代码\前端") `
            -WindowStyle Hidden -RedirectStandardOutput (Join-Path $LogDir "前端启动_stdout.log") `
            -RedirectStandardError (Join-Path $LogDir "前端启动_stderr.log")
        for ($i = 1; $i -le 30; $i++) { Start-Sleep -Seconds 1; if ((Port $FrontendPort) -gt 0) { break } }
        Say ("前端已起（等待 {0} s）" -f $i) ((Port $FrontendPort) -gt 0)
    } else {
        Say "交付物/03-代码\前端\node_modules 不存在，先执行：cd 交付物/03-代码\前端; npm install" $false
    }
}

# ---------- 健康检查 ----------
Write-Host "`n⑤ 健康检查"
try {
    $h = Invoke-RestMethod -Uri "http://127.0.0.1:$BackendPort/api/health" -TimeoutSec 30
    Say ("status={0} mysql={1} neo4j={2} vector_index={3} model_config={4}" -f `
        $h.status, $h.mysql.ok, $h.neo4j.ok, $h.vector_index.ok, $h.model_config.ok) ($h.status -eq "ok")
} catch {
    Say "健康检查失败：$($_.Exception.Message)" $false
}

Write-Host "`n入口："
Write-Host ("  后端 API  http://127.0.0.1:{0}/api/health" -f $BackendPort)
if (-not $NoFrontend) { Write-Host ("  前端页面  http://127.0.0.1:{0}/" -f $FrontendPort) }
Write-Host "  图谱浏览  http://127.0.0.1:7474/（Neo4j Browser）"
Write-Host "`n提示：WSL2 发行版会在**最后一次 wsl 调用结束后约 10～15 秒**挂起；长期运行请加 -KeepAlive，或保持一个 WSL 会话常驻（见 交付物/10-部署\README.md 的保活一节）。"
