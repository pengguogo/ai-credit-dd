<#
离线依赖打包（Windows PowerShell）：在有网的 Windows 机器上执行，产物提交进仓库，评委克隆后不联网即可启动。
《通用提交材料说明》1.1(1)：依赖必须离线内置，评测环境禁止联网下载。

产出（都入库）：
  vendor/python/python-<版本>-win-amd64.zip   内置 Python 解释器（python.org 官方 NuGet 包），评委机没有合适的 Python 时由 start.ps1 解压使用
  vendor/wheels/win_amd64-py<X.Y>/            每个 Python 版本一套后端依赖 wheel（含传递依赖）
  ocft-starter/dist/                          前端构建产物，由后端在 http://127.0.0.1:8000 直接提供，运行时不需要 Node.js

用法：
  powershell -ExecutionPolicy Bypass -File .\pack-offline.ps1
      为 3.11 / 3.12 / 3.13 / 3.14 各下载一套 wheel，打包内置 Python，并构建前端
  -PythonVersions 3.12,3.14   只处理指定的 Python 小版本
  -IndexUrl 指定镜像，如 https://pypi.tuna.tsinghua.edu.cn/simple
  -SkipFrontend 不构建前端
#>
param(
    [string[]]$PythonVersions = @("3.11", "3.12", "3.13", "3.14"),
    [string]$IndexUrl = "",
    [switch]$SkipFrontend
)
# 不用 "Stop"：Windows PowerShell 5.1 会把 pip / npm 写到 stderr 的提示当成致命错误；原生命令一律看 $LASTEXITCODE
$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"
$Root = $PSScriptRoot
$Backend = Join-Path $Root "ocft-backend"
$Frontend = Join-Path $Root "ocft-starter"
$Vendor = Join-Path $Root "vendor"
$Cache = Join-Path $env:TEMP "ocft-pack-offline"

# @why 每个小版本固定一个官方补丁版本：wheel 按小版本区分，补丁版本只影响下载用的解释器与内置包
$PatchVersions = @{ "3.11" = "3.11.9"; "3.12" = "3.12.10"; "3.13" = "3.13.17"; "3.14" = "3.14.9" }
# 内置给评委机兜底的解释器版本：与开发实测版本同一小版本
$BundledMinor = "3.14"

function Get-NugetPython([string]$minor) {
    # 下载并解压 python.org 发布到 NuGet 的官方 Windows x64 构建（免安装、自带 pip 与 venv）
    $full = $PatchVersions[$minor]
    if (-not $full) { Write-Host "不支持的 Python 版本 $minor（可选：$($PatchVersions.Keys -join ', ')）" -ForegroundColor Red; exit 1 }
    New-Item -ItemType Directory -Force $Cache | Out-Null
    $zip = Join-Path $Cache "python-$full.zip"
    $dir = Join-Path $Cache $full
    if (-not (Test-Path $zip)) {
        Write-Host "==> 下载 Python $full（NuGet 官方包）"
        Invoke-WebRequest "https://api.nuget.org/v3-flatcontainer/python/$full/python.$full.nupkg" -OutFile $zip -UseBasicParsing
    }
    if (-not (Test-Path (Join-Path $dir "tools\python.exe"))) {
        if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [System.IO.Compression.ZipFile]::ExtractToDirectory($zip, $dir)
    }
    return @{ Full = $full; Zip = $zip; Exe = (Join-Path $dir "tools\python.exe") }
}

# @why powershell -File 传入的 "3.12,3.13" 是单个字符串，这里统一拆开
$PythonVersions = @($PythonVersions | ForEach-Object { $_ -split "," } | ForEach-Object { $_.Trim() } | Where-Object { $_ })
foreach ($minor in $PythonVersions) {
    $py = Get-NugetPython $minor
    $target = Join-Path $Vendor "wheels\win_amd64-py$minor"
    if (Test-Path $target) { Remove-Item -Recurse -Force $target }
    New-Item -ItemType Directory -Force $target | Out-Null
    # @why 用目标版本的真实解释器下载，而不是 --python-version 交叉下载：
    #      pip 按执行下载的解释器求值环境标记，交叉下载会漏掉只在某些版本需要的依赖
    # @why 只收 wheel（--only-binary）：离线环境没有编译工具链，源码包装不上
    $pipArgs = @("-m", "pip", "download", "-q", "--disable-pip-version-check", "--only-binary=:all:",
        "-r", (Join-Path $Backend "requirements.txt"), "-d", $target)
    if ($IndexUrl) { $pipArgs += @("-i", $IndexUrl) }
    Write-Host "==> 下载 Python $minor 的 wheel 到 $target"
    & $py.Exe @pipArgs
    if ($LASTEXITCODE -ne 0) { Write-Host "wheel 下载失败（网络不稳可加 -IndexUrl 换镜像）" -ForegroundColor Red; exit 1 }
    Write-Host "✅ $((Get-ChildItem $target -Filter *.whl).Count) 个 wheel"
}

# 内置解释器：只保留一个版本的压缩包，旧版本删除
$bundled = Get-NugetPython $BundledMinor
$pyDir = Join-Path $Vendor "python"
New-Item -ItemType Directory -Force $pyDir | Out-Null
Get-ChildItem $pyDir -Filter "python-*.zip" | Remove-Item -Force
Copy-Item $bundled.Zip (Join-Path $pyDir "python-$($bundled.Full)-win-amd64.zip")
Write-Host "✅ 内置 Python $($bundled.Full)：$pyDir"

if (-not $SkipFrontend) {
    Write-Host "==> 构建前端 ocft-starter/dist"
    Push-Location $Frontend
    try {
        if (-not (Test-Path "node_modules")) { & npm ci --no-fund --no-audit }
        & npm run build
    } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { Write-Host "前端构建失败" -ForegroundColor Red; exit 1 }
    Write-Host "✅ 前端已构建：$Frontend\dist"
}

Write-Host ""
Write-Host "下一步：提交 vendor/ 与 ocft-starter/dist/；评委机启动：双击 start.bat，或 powershell -ExecutionPolicy Bypass -File .\start.ps1 -Offline"
