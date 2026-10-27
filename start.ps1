<#
一键启动（Windows PowerShell）：依赖检查 → 虚拟环境与依赖 → .env 前置提示 → 起后端(uvicorn) + 前端(vite)
→ 打印地址与就绪状态 → Ctrl-C 或关闭窗口时清理全部子进程。
不清表、不重灌样本（建表与幂等种子由后端启动自行完成）。

用法：
  powershell -ExecutionPolicy Bypass -File .\start.ps1
  powershell -ExecutionPolicy Bypass -File .\start.ps1 -Reinstall
    -Reinstall  按 requirements.txt 与 package-lock 重装前后端依赖后再启动
    默认只在缺少虚拟环境、依赖或 node_modules 时安装
  powershell -ExecutionPolicy Bypass -File .\start.ps1 -Offline
    -Offline    离线交付模式：只从 vendor/wheels 安装 Python 依赖（--no-index，不联网），不需要 Node.js；
                页面由后端直接提供。没有 node_modules 时（如评委刚克隆）自动进入该模式
    -Dev        强制开发模式（联网安装依赖、Vite 热更新），即使没有 node_modules
  评委机：双击 start.bat 即可（等价于本脚本的离线模式）

Python 选择：已有可用的 ocft-backend\.venv 就复用；否则
  离线模式：始终用仓库内置的 vendor\python\python-*.zip（首次解压到 vendor\python\runtime），
            不依赖评委机装没装 Python、装的是哪个版本（评测环境不指定 Python / Node 版本）
  开发模式：系统 Python 3.11–3.14，没有时同样退回内置 Python
#>
param(
    [switch]$Reinstall,
    [switch]$Offline,
    [switch]$Dev
)
# @why 不用 "Stop"：Windows PowerShell 5.1 会把原生命令（python / pip / npm）写到 stderr 的内容
#      当成致命错误，全新环境首次运行时依赖探测必然失败并打印 Traceback，脚本会直接中断。
#      原生命令一律看 $LASTEXITCODE；PowerShell 命令需要中断时显式加 -ErrorAction Stop
$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"   # Invoke-WebRequest 等的进度条在 PowerShell 5.1 下很慢
$Root = $PSScriptRoot
$Backend = Join-Path $Root "ocft-backend"
$Frontend = Join-Path $Root "ocft-starter"
$Wheels = Join-Path $Root "vendor\wheels"
$BundledDir = Join-Path $Root "vendor\python"
$BundledExe = Join-Path $BundledDir "runtime\tools\python.exe"
$Dist = Join-Path $Frontend "dist\index.html"
$BackendUrl = "http://127.0.0.1:8000"
$env:PYTHONIOENCODING = "utf-8"
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"

function Need($cmd, $hint) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Host "缺少 $cmd：$hint" -ForegroundColor Red
        exit 1
    }
}

function Get-PyMinor($exe) {
    # @why 系统里的 python 可能是微软商店的占位程序（运行即报错、无输出），按输出判断而不是只看是否存在
    $out = (& $exe -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null)
    if ($LASTEXITCODE -ne 0 -or -not $out) { return $null }
    return "$out".Trim()
}

function Test-Supported($minor, $needWheels) {
    if (-not $minor) { return $false }
    if ([version]$minor -lt [version]"3.11" -or [version]$minor -gt [version]"3.14") { return $false }
    if ($needWheels) { return (Test-Path (Join-Path $Wheels "win_amd64-py$minor")) }
    return $true
}

# --- 模式：显式 -Offline；或没有 node_modules 且离线包齐全（评委刚克隆）时自动离线 ---
$packaged = (Test-Path $Wheels) -and (Test-Path $Dist)
if (-not $Offline -and -not $Dev -and $packaged -and -not (Test-Path (Join-Path $Frontend "node_modules"))) {
    $Offline = $true
    Write-Host "==> 未发现 ocft-starter\node_modules，使用离线模式（不联网安装，页面由后端提供；开发请加 -Dev）"
}
$FrontendUrl = if ($Offline) { $BackendUrl } else { "http://127.0.0.1:5173" }
if ($Offline) {
    if (-not (Test-Path $Wheels)) { Write-Host "离线模式缺少 vendor\wheels：请先在有网机器上执行 pack-offline.ps1" -ForegroundColor Red; exit 1 }
    if (-not (Test-Path $Dist)) { Write-Host "离线模式缺少前端构建产物 ocft-starter\dist：请先执行 pack-offline.ps1" -ForegroundColor Red; exit 1 }
} else {
    Need "npm" "请安装 Node.js 18+（https://nodejs.org/）"
}

# --- 后端：虚拟环境（已有可用的就复用；否则离线用内置 Python、开发优先系统 Python 来创建） ---
$Py = Join-Path $Backend ".venv\Scripts\python.exe"
if ((Test-Path $Py) -and -not (Get-PyMinor $Py)) {
    # 虚拟环境指向的解释器已不存在（例如换了机器或卸载了 Python），重建
    Write-Host "==> 现有 ocft-backend\.venv 不可用，重新创建" -ForegroundColor Yellow
    Remove-Item -Recurse -Force (Join-Path $Backend ".venv")
}
if ($Offline -and (Test-Path $Py) -and -not (Test-Supported (Get-PyMinor $Py) $true)) {
    # 离线包里没有这个 Python 版本的 wheel（例如别人用 3.10 / 32 位 Python 建过 .venv），改用内置 Python 重建
    Write-Host "==> 现有 ocft-backend\.venv 的 Python 版本没有对应的离线 wheel，改用内置 Python 重建" -ForegroundColor Yellow
    Remove-Item -Recurse -Force (Join-Path $Backend ".venv")
}
if (-not (Test-Path $Py)) {
    $basePy = $null
    if (-not $Offline) {
        $sys = Get-Command python -ErrorAction SilentlyContinue
        if ($sys -and (Test-Supported (Get-PyMinor $sys.Source) $false)) { $basePy = $sys.Source }
    }
    if (-not $basePy) {
        $zip = Get-ChildItem $BundledDir -Filter "python-*.zip" -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not (Test-Path $BundledExe) -and $zip) {
            Write-Host "==> 解压内置 Python（$($zip.Name)，不使用也不需要系统 Python）"
            $runtime = Join-Path $BundledDir "runtime"
            $staging = Join-Path $BundledDir "runtime.partial"
            foreach ($d in $runtime, $staging) { if (Test-Path $d) { Remove-Item -Recurse -Force $d } }
            # @why 不用 Expand-Archive：Windows PowerShell 5.1 下它逐文件刷新进度条，解压几千个文件要数分钟
            # @why 先解压到临时目录再改名：中途被关掉时不会留下"有 python.exe 但不完整"的目录
            Add-Type -AssemblyName System.IO.Compression.FileSystem
            [System.IO.Compression.ZipFile]::ExtractToDirectory($zip.FullName, $staging)
            Rename-Item $staging "runtime"
        }
        if (Test-Path $BundledExe) { $basePy = $BundledExe }
    }
    if (-not $basePy) {
        Write-Host "缺少可用的 Python：请安装 Python 3.11–3.14 并加入 PATH，或执行 pack-offline.ps1 生成内置 Python" -ForegroundColor Red
        exit 1
    }
    Write-Host "==> 创建 Python 虚拟环境 ocft-backend\.venv（基于 $basePy）"
    & $basePy -m venv (Join-Path $Backend ".venv")
    if ($LASTEXITCODE -ne 0) { Write-Host "创建虚拟环境失败" -ForegroundColor Red; exit 1 }
}
$pyVersion = Get-PyMinor $Py
if (-not (Test-Supported $pyVersion $false)) {
    Write-Host "虚拟环境的 Python 版本 $pyVersion 不受支持（需要 3.11–3.14）：删除 ocft-backend\.venv 后重试" -ForegroundColor Red
    exit 1
}
# 新增依赖时把包名加进这里，否则拉新代码后不会自动安装
& $Py -c "import fastapi, uvicorn, sqlalchemy, pydantic_settings, openai, cryptography, sqlglot, socksio, langgraph, openpyxl, redis, yaml" 2>$null | Out-Null
$depsMissing = $LASTEXITCODE -ne 0
if ($Reinstall -or $depsMissing) {
    if ($Reinstall) { Write-Host "==> 重装后端依赖" } else { Write-Host "==> 安装后端依赖" }
    if ($Offline) {
        # @why --no-index：完全不访问网络；只用与虚拟环境 Python 小版本对应的那套 wheel
        $wheelDir = Join-Path $Wheels "win_amd64-py$pyVersion"
        if (-not (Test-Path $wheelDir)) {
            Write-Host "离线包中没有 Python $pyVersion 的 wheel（$wheelDir）：删除 ocft-backend\.venv 后重试，会改用内置 Python" -ForegroundColor Red
            exit 1
        }
        & $Py -m pip install -q --no-index --find-links $wheelDir -r (Join-Path $Backend "requirements.txt")
    } else {
        & $Py -m pip install -q --upgrade pip
        & $Py -m pip install -q -r (Join-Path $Backend "requirements.txt")
    }
    if ($LASTEXITCODE -ne 0) { Write-Host "后端依赖安装失败" -ForegroundColor Red; exit 1 }
}

# 本地启动 ≠ 模型离线运行：真实模型仍需网络与凭据（如实提示，不静默放行）
if (-not (Test-Path (Join-Path $Backend ".env"))) {
    Write-Host "⚠️  未发现 ocft-backend\.env：LLM 未配置，模型能力不可用（/api/health/ready 将返回 503）" -ForegroundColor Yellow
    Write-Host "    可执行: Copy-Item ocft-backend\.env.example ocft-backend\.env  然后填入 LLM_API_KEY（支持 enc: 密文）"
}

# --- 前端：Node 依赖（离线模式由后端提供构建产物，跳过） ---
if (-not $Offline -and ($Reinstall -or -not (Test-Path (Join-Path $Frontend "node_modules")))) {
    if ($Reinstall) { Write-Host "==> 重装前端依赖" } else { Write-Host "==> 安装前端依赖（首次较慢）" }
    Push-Location $Frontend
    try { & npm install --no-fund --no-audit } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { Write-Host "前端依赖安装失败" -ForegroundColor Red; exit 1 }
}

# --- 端口占用检查 ---
$ports = if ($Offline) { @(8000) } else { @(8000, 5173) }
foreach ($port in $ports) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        Write-Host "端口 $port 已被占用，请先关闭占用进程后重试" -ForegroundColor Red
        exit 1
    }
}

# --- 启动子进程 ---
Write-Host "==> 启动后端 $BackendUrl"
$backendProc = Start-Process -FilePath $Py -WorkingDirectory $Backend -PassThru -NoNewWindow `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"
$frontendProc = $null
if (-not $Offline) {
    Write-Host "==> 启动前端 $FrontendUrl"
    $npmCmd = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
    if (-not $npmCmd) { $npmCmd = (Get-Command npm).Source }
    $frontendProc = Start-Process -FilePath $npmCmd -WorkingDirectory $Frontend -PassThru -NoNewWindow `
        -ArgumentList "run", "dev", "--", "--host", "127.0.0.1", "--port", "5173", "--strictPort"
}

function Stop-All {
    Write-Host ""
    Write-Host "==> 停止全部服务…"
    foreach ($p in $backendProc, $frontendProc) {
        if ($p -and -not $p.HasExited) {
            # /T 结束整个进程树（npm → node → vite）
            & taskkill /PID $p.Id /T /F 2>$null | Out-Null
        }
    }
}

try {
    # 等待后端起来（最多 60s），随后如实打印就绪状态（503 也打印，不装健康）
    for ($i = 0; $i -lt 60; $i++) {
        if ($backendProc.HasExited) { throw "后端进程已退出（退出码 $($backendProc.ExitCode)），请查看上方日志" }
        try {
            Invoke-WebRequest -Uri "$BackendUrl/api/health/live" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop | Out-Null
            break
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    Write-Host ""
    Write-Host "==== 后端就绪状态 ===="
    try {
        $body = Invoke-RestMethod -Uri "$BackendUrl/api/health/ready" -TimeoutSec 5 -ErrorAction Stop
        Write-Host ($body | ConvertTo-Json -Depth 5 -Compress)
    } catch {
        $detail = $_.ErrorDetails.Message
        if ($detail) { Write-Host $detail -ForegroundColor Yellow } else { Write-Host "无法获取就绪状态：$($_.Exception.Message)" -ForegroundColor Yellow }
    }
    Write-Host ""
    Write-Host "✅ 后端 API 文档: $BackendUrl/docs"
    Write-Host "✅ 前端页面:     $FrontendUrl"
    Write-Host "按 Ctrl-C 停止全部服务"
    while (-not $backendProc.HasExited -and -not ($frontendProc -and $frontendProc.HasExited)) {
        Start-Sleep -Seconds 1
    }
    if ($backendProc.HasExited) { Write-Host "后端进程已退出" -ForegroundColor Yellow }
    if ($frontendProc -and $frontendProc.HasExited) { Write-Host "前端进程已退出" -ForegroundColor Yellow }
} finally {
    Stop-All
}
