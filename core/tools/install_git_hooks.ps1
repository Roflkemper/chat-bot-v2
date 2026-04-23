param(
    [string]$ProjectRoot = (Resolve-Path ".").Path
)

$ErrorActionPreference = "Stop"

$gitExe = "C:\Program Files\Git\cmd\git.exe"
if (-not (Test-Path $gitExe)) {
    $gitExe = "C:\Program Files (x86)\Git\cmd\git.exe"
}
if (-not (Test-Path $gitExe)) {
    throw "Git not found. Install Git for Windows first."
}

$resolvedRoot = (Resolve-Path $ProjectRoot).Path
Set-Location $resolvedRoot

& $gitExe rev-parse --is-inside-work-tree *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Current folder is not a Git repository: $resolvedRoot"
}

$hooksPath = Join-Path $resolvedRoot ".githooks"
if (-not (Test-Path $hooksPath)) {
    throw ".githooks folder not found: $hooksPath"
}

& $gitExe config core.hooksPath .githooks
if ($LASTEXITCODE -ne 0) {
    throw "Failed to set core.hooksPath"
}

Write-Host "[OK] Git hooks path set: .githooks"
Write-Host "[OK] pre-commit and pre-push will now run Regression Shield automatically"
