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

    已知环境限制（如实登记，见 部署\README.md）：
      · 本机**未安装 Docker Desktop**（需要管理员权限），Docker 只以 **WSL2 内的 Engine** 形态可用；
      · WSL2 发行版会**空闲挂起**，挂起后 Neo4j 不可达——故本脚本在启动后**保留一个 WSL 保活进程**；
      · WSL 服务偶发进入 `Wsl/Service/E_UNEXPECTED`，此时先 `wsl --shutdown` 再重跑本脚本。

.PARAMETER NoFrontend
    只起 MySQL／Neo4j／后端，不起前端。

.PARAMETER Stop
    停掉本脚本起的前端与后端进程（Neo4j 容器保持运行）。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File 部署\启动.ps1
#>
[CmdletBinding()]
param(
    [switch]$NoFrontend,
    [switch]$Stop
)

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Distro = "Ubuntu"
$Container = "ashare-neo4j"
$BackendPort = 8000
$FrontendPort = 5173
$LogDir = Join-Path $Root "阶段09-前后端系统集成\_工作底稿"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Say($msg, $ok) {
    $tag = if ($ok -eq $null) { "····" } elseif ($ok) { " OK " } else { " !! " }
    Write-Host ("[{0}] {1}" -f $tag, $msg)
}
function Port($p) { (Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | Measure-Object).Count }
function Wsl([string]$cmd, [int]$timeoutSec = 120) {
    # WSL 调用一律包在作业里并设超时：实测 WSL 偶发无响应，裸调会挂住整个脚本。
    $env:WSL_UTF8 = 1
    $job = Start-Job -ScriptBlock { param($d, $c) wsl -d $d -u root -- bash -lc $c 2>&1 } -ArgumentList $Distro, $cmd
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
$dbOut = & python (Join-Path $Root "代码\后端\db.py") 2>&1 | Out-String
$dbOut.Trim().Split("`n") | Select-Object -Last 4 | ForEach-Object { Write-Host "      $($_.Trim())" }
Say ("六张表可读={0}" -f ($dbOut -match "六张表行数")) ($dbOut -match "六张表行数")

# ---------- ② Neo4j（WSL2 内的 Docker Engine） ----------
Write-Host "`n② Neo4j（WSL2 ＋ Docker Engine）"
$wslState = ((wsl -l -v 2>&1 | Out-String) -split "`n" | Where-Object { $_ -match "\*\s+$Distro" })
Say "WSL 发行版：$($wslState.Trim())" $null
$r = Wsl "systemctl start docker 2>/dev/null; docker start $Container 2>&1 | tail -1; docker ps --filter name=$Container --format '{{.Names}} {{.Status}}'"
Say ("容器：{0}" -f ($r -replace "`r?`n", " / ")) ($r -match "Up")
$bolt = $false
for ($i = 1; $i -le 20; $i++) {
    Start-Sleep -Seconds 3
    $t = Test-NetConnection -ComputerName 127.0.0.1 -Port 7687 -InformationLevel Quiet -WarningAction SilentlyContinue
    if ($t) { $bolt = $true; break }
}
Say ("bolt 7687 可达={0}（等待 {1} 轮）" -f $bolt, $i) $bolt

# ---------- ③ 后端 ----------
Write-Host "`n③ 后端（8000）"
if ((Port $BackendPort) -gt 0) {
    Say "8000 已在监听，复用现有进程（不重复起）" $true
} else {
    Start-Process -FilePath "python" -ArgumentList "代码\后端\run.py" -WorkingDirectory $Root -WindowStyle Hidden `
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
    } elseif (Test-Path (Join-Path $Root "代码\前端\node_modules")) {
        Start-Process -FilePath "cmd.exe" -ArgumentList "/c npm run dev" -WorkingDirectory (Join-Path $Root "代码\前端") `
            -WindowStyle Hidden -RedirectStandardOutput (Join-Path $LogDir "前端启动_stdout.log") `
            -RedirectStandardError (Join-Path $LogDir "前端启动_stderr.log")
        for ($i = 1; $i -le 30; $i++) { Start-Sleep -Seconds 1; if ((Port $FrontendPort) -gt 0) { break } }
        Say ("前端已起（等待 {0} s）" -f $i) ((Port $FrontendPort) -gt 0)
    } else {
        Say "代码\前端\node_modules 不存在，先执行：cd 代码\前端; npm install" $false
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
Write-Host "`n提示：WSL2 发行版会空闲挂起；如需长期运行，请保持一个 WSL 会话（见 部署\README.md 的保活一节）。"
