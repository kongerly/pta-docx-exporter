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

Write-Host "Installing Python dependencies..."
& $PythonExe -m pip install -r (Join-Path $ProjectRoot "requirements.txt")

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

if (-not $SkipRuntimeCopy -and $resolvedNodeExe -and $resolvedNodeModulesDir) {
    Write-Host "Copying Node runtime for Playwright bridge..."
    New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null
    Copy-Item $resolvedNodeExe (Join-Path $RuntimeRoot "node.exe") -Force
    Copy-Item $resolvedNodeModulesDir (Join-Path $RuntimeRoot "node_modules") -Recurse -Force
} else {
    if ($SkipRuntimeCopy) {
        Write-Host "Skipping Node runtime copy because -SkipRuntimeCopy was provided."
    } else {
        Write-Warning "Skipping Node runtime copy because node.exe or node_modules could not be located."
        Write-Warning "The packaged app can still be built, but users will need PTA_NODE_EXE and PTA_NODE_MODULES unless you rebuild with a bundled runtime."
    }
}

Write-Host "Building onedir executable..."
Push-Location $ProjectRoot
try {
    & $PythonExe -m PyInstaller (Join-Path $PSScriptRoot "pta_docx_exporter.spec")
}
finally {
    Pop-Location
}
