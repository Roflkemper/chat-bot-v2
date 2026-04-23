param(
    [Parameter(Mandatory = $true)][string]$ZipPath,
    [int]$MinSizeBytes = 1024,
    [int]$MinEntries = 5
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $ZipPath)) {
    throw 'ZIP not found'
}

$item = Get-Item -LiteralPath $ZipPath
$size = $item.Length
if ($size -le $MinSizeBytes) {
    throw 'ZIP too small'
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
try {
    if ($zip.Entries.Count -lt $MinEntries) {
        throw 'ZIP has too few entries'
    }
}
finally {
    $zip.Dispose()
}

Write-Host ("[OK] ZIP verified. Size: {0} bytes" -f $size)
