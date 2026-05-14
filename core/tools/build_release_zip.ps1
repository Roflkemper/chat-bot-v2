param(
    [Parameter(Mandatory = $true)][string]$ProjectRoot,
    [Parameter(Mandatory = $true)][string]$ZipPath,
    [Parameter(Mandatory = $true)][string]$ProjectName,
    [string]$ExcludeFile = ".releaseignore"
)

$ErrorActionPreference = 'Stop'

$root = (Resolve-Path $ProjectRoot).Path
$zipParent = Split-Path -Parent $ZipPath
if (-not (Test-Path $zipParent)) {
    New-Item -ItemType Directory -Force -Path $zipParent | Out-Null
}
if (Test-Path $ZipPath) {
    Remove-Item $ZipPath -Force
}

$patterns = @()
$excludePath = Join-Path $root $ExcludeFile
if (Test-Path $excludePath) {
    $patterns = Get-Content $excludePath |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ -ne '' }
}

function Should-Exclude {
    param([string]$RelativePath)

    $rel = $RelativePath.Replace('/', '\').TrimStart('\\')
    foreach ($pattern in $patterns) {
        $p = $pattern.Replace('/', '\').Trim()
        if (-not $p) { continue }

        if ($rel -like $p) { return $true }
        if ($rel -like ($p + '\*')) { return $true }

        $leaf = Split-Path $rel -Leaf
        if ($leaf -like $p) { return $true }
    }
    return $false
}

$tmp = Join-Path $env:TEMP ('release_' + [guid]::NewGuid().ToString())
$stage = Join-Path $tmp $ProjectName
New-Item -ItemType Directory -Force -Path $stage | Out-Null

try {
    $items = Get-ChildItem -LiteralPath $root -Force
    foreach ($item in $items) {
        $rel = $item.Name
        if (Should-Exclude -RelativePath $rel) { continue }

        $dest = Join-Path $stage $rel
        if ($item.PSIsContainer) {
            Copy-Item -LiteralPath $item.FullName -Destination $dest -Recurse -Force -Exclude @('__pycache__', '*.pyc', '*.pyo', '*.log')
        }
        else {
            $destDir = Split-Path -Parent $dest
            if (-not (Test-Path $destDir)) {
                New-Item -ItemType Directory -Force -Path $destDir | Out-Null
            }
            Copy-Item -LiteralPath $item.FullName -Destination $dest -Force
        }
    }

    Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $ZipPath -Force
}
finally {
    if (Test-Path $tmp) {
        Remove-Item $tmp -Recurse -Force
    }
}

Write-Host "[OK] Release ZIP built: $ZipPath"
