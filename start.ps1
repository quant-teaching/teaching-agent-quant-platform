# 一键启动（Windows）：安装依赖 → 构建前端（已构建则跳过，-Build 强制重建）→ 启动后端（同时托管前端页面）
# 用法：双击 start.bat；或在 PowerShell 中运行 .\start.ps1 [-Build] [-NoBrowser]
param(
    [switch]$Build,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Continue"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$env:PYTHONUTF8 = "1"  # 让 Python 读写文件、输出日志都用 UTF-8，避免中文 Windows 默认 GBK 造成乱码

function Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Fail($msg) { Write-Host $msg -ForegroundColor Red; exit 1 }

Push-Location -LiteralPath $PSScriptRoot
try {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Fail ("未找到 uv。请在 PowerShell 中运行下面的命令安装，然后重新打开窗口再启动：`n" +
              '  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"')
    }

    $hostAddr = if ($env:HOST) { $env:HOST } else { "127.0.0.1" }
    $port = if ($env:PORT) { $env:PORT } else { "8000" }
    $browseHost = if ($hostAddr -eq "0.0.0.0") { "127.0.0.1" } else { $hostAddr }
    $url = "http://${browseHost}:$port"

    if ((Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) -and
        (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)) {
        Fail "端口 $port 已被占用：平台可能已经在运行（直接打开 $url），或用 `$env:PORT=8001 换一个端口。"
    }

    Step "安装后端依赖"
    Push-Location backend
    uv sync --quiet
    $code = $LASTEXITCODE
    Pop-Location
    if ($code -ne 0) { Fail "后端依赖安装失败，请检查网络后重试" }

    if ($Build -or -not (Test-Path "frontend\dist\index.html")) {
        if (-not (Get-Command pnpm -ErrorAction SilentlyContinue)) {
            Fail "未找到 pnpm。请先安装 Node.js 20+（https://nodejs.org），再运行：npm i -g pnpm"
        }
        Step "构建前端"
        Push-Location frontend
        pnpm install --silent
        if ($LASTEXITCODE -eq 0) { pnpm build }
        $code = $LASTEXITCODE
        Pop-Location
        if ($code -ne 0) { Fail "前端构建失败" }
    }

    if (-not $NoBrowser) {
        # 服务就绪后自动打开浏览器
        $null = Start-Job -ArgumentList $url -ScriptBlock {
            param($u)
            for ($i = 0; $i -lt 90; $i++) {
                Start-Sleep -Seconds 1
                try {
                    Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "$u/api/health" | Out-Null
                    Start-Process $u
                    return
                } catch { }
            }
        }
    }

    Step "启动服务：$url（按 Ctrl+C 停止）"
    Push-Location backend
    uv run python -m uvicorn api.main:app --host $hostAddr --port $port
    $code = $LASTEXITCODE
    Pop-Location
    exit $code
}
finally {
    Get-Job | Remove-Job -Force -ErrorAction SilentlyContinue
    Pop-Location
}
