param(
    [string]$PythonExe = "python",
    [string]$NodeExe = "",
    [string]$NodeModulesDir = "",
    [switch]$SkipRuntimeCopy
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RuntimeRoot = Join-Path $ProjectRoot "runtime\node"
$CodexRuntimeRoot = Join-Path $HOME ".cache\codex-runtimes\codex-primary-runtime\dependencies\node"

function Get-AppMeta {
    $script = @'
import json
from app_meta import APP_DISPLAY_NAME, APP_VERSION
print(json.dumps({"display_name": APP_DISPLAY_NAME, "version": APP_VERSION}))
'@
    $raw = $script | & $PythonExe -
    return $raw | ConvertFrom-Json
}

function Resolve-FirstExistingPath {
    param(
        [object[]]$Candidates = @()
    )

    foreach ($candidate in @($Candidates)) {
        $candidateText = [string]$candidate
        if ([string]::IsNullOrWhiteSpace($candidateText)) {
            continue
        }
        if (Test-Path -LiteralPath $candidateText) {
            return (Resolve-Path -LiteralPath $candidateText).Path
        }
    }

    return ""
}

function Test-PlaywrightNodeModules {
    param(
        [string]$NodeModulesPath
    )

    if ([string]::IsNullOrWhiteSpace($NodeModulesPath)) {
        return $false
    }

    if (-not (Test-Path -LiteralPath $NodeModulesPath)) {
        return $false
    }

    if (Test-Path -LiteralPath (Join-Path $NodeModulesPath "playwright")) {
        return $true
    }

    $pnpmDir = Join-Path $NodeModulesPath ".pnpm"
    if (-not (Test-Path -LiteralPath $pnpmDir)) {
        return $false
    }

    $package = Get-ChildItem -LiteralPath $pnpmDir -Directory -Filter "playwright@*" -ErrorAction SilentlyContinue | Select-Object -First 1
    return $null -ne $package
}

function Assert-RequiredPath {
    param(
        [string]$PathText,
        [string]$Label
    )

    if (-not (Test-Path -LiteralPath $PathText)) {
        throw ("构建产物缺失：{0} -> {1}" -f $Label, $PathText)
    }

    Write-Host ("已验证产物：{0} -> {1}" -f $Label, $PathText)
}

Write-Host "正在安装 Python 依赖..."
& $PythonExe -m pip install -r (Join-Path $ProjectRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    throw "Python 依赖安装失败，退出码：$LASTEXITCODE"
}

$appMeta = Get-AppMeta
Write-Host "正在准备 Windows 便携版打包环境..."
Write-Host ("当前构建版本：{0} v{1}" -f $appMeta.display_name, $appMeta.version)

$resolvedNodeExe = Resolve-FirstExistingPath @(
    $NodeExe,
    $env:PTA_NODE_EXE,
    (Join-Path $CodexRuntimeRoot "bin\node.exe")
)
$resolvedNodeModulesDir = Resolve-FirstExistingPath @(
    $NodeModulesDir,
    $env:PTA_NODE_MODULES,
    (Join-Path $CodexRuntimeRoot "node_modules")
)
$hasPlaywright = Test-PlaywrightNodeModules $resolvedNodeModulesDir

if ($resolvedNodeExe) {
    Write-Host ("已检测到 node.exe：{0}" -f $resolvedNodeExe)
} else {
    Write-Warning "未检测到可用于打包的 node.exe。"
}

if ($resolvedNodeModulesDir) {
    Write-Host ("已检测到 node_modules：{0}" -f $resolvedNodeModulesDir)
} else {
    Write-Warning "未检测到可用于打包的 node_modules。"
}

if ($resolvedNodeModulesDir -and $hasPlaywright) {
    Write-Host "已检测到 Playwright 依赖。"
} elseif ($resolvedNodeModulesDir) {
    Write-Warning "未在 node_modules 中检测到 Playwright 依赖。"
}

if (-not $SkipRuntimeCopy -and $resolvedNodeExe -and $resolvedNodeModulesDir -and $hasPlaywright) {
    Write-Host "正在复制 Node 运行时和 Playwright 依赖..."
    New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null
    Copy-Item $resolvedNodeExe (Join-Path $RuntimeRoot "node.exe") -Force
    Copy-Item $resolvedNodeModulesDir (Join-Path $RuntimeRoot "node_modules") -Recurse -Force
} else {
    if ($SkipRuntimeCopy) {
        Write-Host "已启用最小打包模式：跳过运行时复制，仅执行 CI 构建验证。"
    } else {
        Write-Warning "本次仍会继续构建，但生成的是不带完整运行时的版本。"
        Write-Warning "如需完整便携版，请补齐 node.exe、node_modules 与 Playwright 依赖后重新构建。"
        Write-Warning "也可以通过 PTA_NODE_EXE 和 PTA_NODE_MODULES 指定本地运行时路径。"
    }
}

Write-Host "正在构建 Windows 便携版可执行目录..."
Push-Location $ProjectRoot
try {
    & $PythonExe -m PyInstaller -y (Join-Path $PSScriptRoot "pta_docx_exporter.spec")
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller 打包失败，退出码：$LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

$DistRoot = Join-Path $ProjectRoot "dist\PTADocxExporter"
$InternalRoot = Join-Path $DistRoot "_internal"

Write-Host "正在校验构建产物..."
Assert-RequiredPath (Join-Path $DistRoot "PTADocxExporter.exe") "便携版主程序"
Assert-RequiredPath (Join-Path $InternalRoot "pta\browser_service.js") "浏览器桥脚本"

if (-not $SkipRuntimeCopy) {
    Assert-RequiredPath (Join-Path $InternalRoot "runtime\node\node.exe") "便携版 Node 运行时"
    Assert-RequiredPath (Join-Path $InternalRoot "runtime\node\node_modules\playwright") "便携版 Playwright 依赖"
}

Write-Host "构建完成。"



