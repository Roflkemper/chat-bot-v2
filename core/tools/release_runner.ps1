$ErrorActionPreference = 'Stop'

function Write-Log {
    param([string]$Message)
    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $line = "[$ts] $Message"
    Write-Host $line
    Add-Content -Path $script:LogFile -Value $line -Encoding UTF8
}

function Ensure-Dir([string]$PathToCreate) {
    if (!(Test-Path $PathToCreate)) {
        New-Item -ItemType Directory -Force -Path $PathToCreate | Out-Null
    }
}

function Get-GitExe {
    $candidates = @(
        "C:\Program Files\Git\cmd\git.exe",
        "C:\Program Files (x86)\Git\cmd\git.exe",
        "git.exe"
    )
    foreach ($candidate in $candidates) {
        try {
            if ($candidate -eq "git.exe") {
                $null = & $candidate --version 2>$null
                if ($LASTEXITCODE -eq 0) { return $candidate }
            } elseif (Test-Path $candidate) {
                return $candidate
            }
        } catch {}
    }
    throw "Git not found."
}

function Invoke-Git {
    param([string[]]$CommandArgs)
    & $script:GitExe @CommandArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Git command failed: git $($CommandArgs -join ' ')"
    }
}

function Try-Invoke-Git {
    param([string[]]$CommandArgs)
    & $script:GitExe @CommandArgs
    return $LASTEXITCODE
}

function Get-VersionTag {
    $versionFile = Join-Path $script:ProjectRoot 'VERSION.txt'
    if (!(Test-Path $versionFile)) {
        $tag = "V" + (Get-Date -Format "yyyy.MM.dd.HHmmss")
        Set-Content -Path $versionFile -Value $tag -Encoding UTF8
        return $tag
    }
    $raw = (Get-Content $versionFile -Raw -Encoding UTF8).Trim()
    if ($raw -match '^V(\d+)\.(\d+)\.(\d+)$') {
        $major = [int]$Matches[1]
        $minor = [int]$Matches[2]
        $patch = [int]$Matches[3] + 1
        $next = "V{0}.{1}.{2}" -f $major, $minor, $patch
        Set-Content -Path $versionFile -Value $next -Encoding UTF8
        return $next
    }
    if ($raw) { return $raw }
    $tag = "V" + (Get-Date -Format "yyyy.MM.dd.HHmmss")
    Set-Content -Path $versionFile -Value $tag -Encoding UTF8
    return $tag
}

function Ensure-ManifestTemplates {
    $manifestDir = Join-Path $script:ProjectRoot 'manifest'
    Ensure-Dir $manifestDir

    $templates = @{
        'manifest_header.md' = @'
# PROJECT MANIFEST вЂ” С‡Р°С‚ Р±РѕС‚ РІРµСЂСЃРёСЏ 2

## РњРёСЃСЃРёСЏ РїСЂРѕРµРєС‚Р°
РЎРґРµР»Р°С‚СЊ С‚СЂРµР№РґРµСЂСЃРєРёР№ РёРЅСЃС‚СЂСѓРјРµРЅС‚ РґР»СЏ СЂСѓС‡РЅРѕР№ С‚РѕСЂРіРѕРІР»Рё Рё СЃРµС‚РѕС‡РЅС‹С… Р±РѕС‚РѕРІ, РєРѕС‚РѕСЂС‹Р№ РїРѕРЅРёРјР°РµС‚ СЂС‹РЅРѕРє, РґР°С‘С‚ С‡С‘С‚РєРёРµ РґРµР№СЃС‚РІРёСЏ Рё РїРѕРјРѕРіР°РµС‚ Р·Р°СЂР°Р±Р°С‚С‹РІР°С‚СЊ.

## РљР»СЋС‡РµРІРѕР№ С„РѕРєСѓСЃ
- Р»РёРєРІРёРґРЅРѕСЃС‚СЊ
- Р»РёРєРІРёРґР°С†РёРё
- СЂРµР°РєС†РёСЏ С†РµРЅС‹ РЅР° Р±Р»РѕРєРё
- fake move
- impulse / continuation
- grid logic
- trader-oriented output
'@;
        'project_rules.md' = @'
## РќРµРїСЂРёРєРѕСЃРЅРѕРІРµРЅРЅС‹Рµ РїСЂР°РІРёР»Р°
- РЅРµ РїРёСЃР°С‚СЊ РєРѕРґ РІ С‡Р°С‚ Р±РµР· РїСЂСЏРјРѕРіРѕ Р·Р°РїСЂРѕСЃР°
- РѕС‚РґР°РІР°С‚СЊ С‚РѕР»СЊРєРѕ РіРѕС‚РѕРІС‹Рµ ZIP-СЂРµС€РµРЅРёСЏ
- РїРµСЂРµРґ РІС‹РґР°С‡РµР№ РїСЂРѕРІРµСЂСЏС‚СЊ Р°СЂС…РёРІ РЅР° С†РµР»РѕСЃС‚РЅРѕСЃС‚СЊ, РЅРµРїСѓСЃС‚РѕС‚Сѓ Рё СЂР°Р±РѕС‚РѕСЃРїРѕСЃРѕР±РЅРѕСЃС‚СЊ
- СЂР°Р±РѕС‚Р°С‚СЊ РїРѕРІРµСЂС… РїРѕСЃР»РµРґРЅРµР№ Р°РєС‚СѓР°Р»СЊРЅРѕР№ РІРµСЂСЃРёРё РїСЂРѕРµРєС‚Р°
- РЅРµ Р»РѕРјР°С‚СЊ СѓР¶Рµ СЃРѕРіР»Р°СЃРѕРІР°РЅРЅС‹Рµ Р±Р»РѕРєРё
- РЅРµ РІРѕР·РІСЂР°С‰Р°С‚СЊ СЃС‚Р°СЂСѓСЋ legacy-Р»РѕРіРёРєСѓ
- Telegram-РІС‹РІРѕРґС‹ РґРѕР»Р¶РЅС‹ Р±С‹С‚СЊ РїРѕРЅСЏС‚РЅС‹РјРё, РЅР° СЂСѓСЃСЃРєРѕРј, Р±РµР· РјСѓСЃРѕСЂР°
'@;
        'current_status.md' = @'
## РўРµРєСѓС‰РёР№ СЃС‚Р°С‚СѓСЃ
РџРѕРґРґРµСЂР¶РёРІР°Р№ СЌС‚РѕС‚ Р±Р»РѕРє РєСЂР°С‚РєРёРј Рё Р°РєС‚СѓР°Р»СЊРЅС‹Рј. РћР±РЅРѕРІР»СЏР№ РµРіРѕ РїСЂРё РєР°Р¶РґРѕРј СЂРµР»РёР·Рµ.
'@;
        'roadmap.md' = @'
## РЎР»РµРґСѓСЋС‰РёР№ СЌС‚Р°Рї
РћРїРёС€Рё СЃР»РµРґСѓСЋС‰РёР№ РїР°РєРµС‚ СЂР°Р·СЂР°Р±РѕС‚РєРё Рё С†РµР»СЊ.
'@;
        'release_policy.md' = @'
## РџСЂР°РІРёР»Р° СЂРµР»РёР·РѕРІ
РљР°Р¶РґС‹Р№ СЂРµР»РёР· РѕР±СЏР·Р°РЅ РѕР±РЅРѕРІР»СЏС‚СЊ:
- VERSION.txt
- CHANGELOG.md
- PROJECT_MANIFEST.md
- NEXT_CHAT_PROMPT.txt

Р•СЃР»Рё PROJECT_MANIFEST.md РЅРµ РѕР±РЅРѕРІР»С‘РЅ вЂ” СЂРµР»РёР· СЃС‡РёС‚Р°РµС‚СЃСЏ РЅРµРїРѕР»РЅС‹Рј.
'@
    }

    foreach ($entry in $templates.GetEnumerator()) {
        $path = Join-Path $manifestDir $entry.Key
        if (!(Test-Path $path)) {
            Set-Content -Path $path -Value $entry.Value -Encoding UTF8
        }
    }
}

function Build-Manifest {
    Ensure-ManifestTemplates
    $parts = @(
        'manifest\manifest_header.md',
        'manifest\project_rules.md',
        'manifest\current_status.md',
        'manifest\roadmap.md',
        'manifest\release_policy.md'
    ) | ForEach-Object { Join-Path $script:ProjectRoot $_ }

    $out = Join-Path $script:ProjectRoot 'PROJECT_MANIFEST.md'
    $content = @()
    foreach ($part in $parts) {
        if (Test-Path $part) {
            $content += (Get-Content $part -Encoding UTF8)
            $content += ''
        }
    }
    Set-Content -Path $out -Value $content -Encoding UTF8
    Write-Log "PROJECT_MANIFEST.md updated"
}

function Ensure-TextFiles {
    $changelog = Join-Path $script:ProjectRoot 'CHANGELOG.md'
    if (!(Test-Path $changelog)) {
        Set-Content -Path $changelog -Value "# CHANGELOG`r`n" -Encoding UTF8
    }
    $nextPrompt = Join-Path $script:ProjectRoot 'NEXT_CHAT_PROMPT.txt'
    if (!(Test-Path $nextPrompt)) {
        Set-Content -Path $nextPrompt -Value "РџСЂРѕРґРѕР»Р¶Р°РµРј РїСЂРѕРµРєС‚ В«С‡Р°С‚ Р±РѕС‚ РІРµСЂСЃРёСЏ 2В». Р Р°Р±РѕС‚Р°Р№ СЃС‚СЂРѕРіРѕ РїРѕ PROJECT_MANIFEST.md. РћС‚РґР°РІР°Р№ С‚РѕР»СЊРєРѕ РіРѕС‚РѕРІС‹Рµ РїСЂРѕРІРµСЂРµРЅРЅС‹Рµ ZIP-СЂРµР»РёР·С‹." -Encoding UTF8
    }
    $gitignore = Join-Path $script:ProjectRoot '.gitignore'
    if (!(Test-Path $gitignore)) {
        Set-Content -Path $gitignore -Value "" -Encoding UTF8
    }
    $gitignoreRaw = Get-Content $gitignore -Raw -Encoding UTF8
    $need = @('releases/', '.venv/', '__pycache__/', '.pytest_cache/', '*.log', '.DS_Store', 'Thumbs.db')
    foreach ($line in $need) {
        if ($gitignoreRaw -notmatch [regex]::Escape($line)) {
            Add-Content -Path $gitignore -Value $line -Encoding UTF8
        }
    }
}

function Update-Changelog {
    param([string]$VersionTag)
    $path = Join-Path $script:ProjectRoot 'CHANGELOG.md'
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $entry = @"
## $VersionTag
- automated release build
- PROJECT_MANIFEST.md rebuilt
- ZIP package created and verified
- release timestamp: $stamp

"@
    $old = Get-Content $path -Raw -Encoding UTF8
    if ($old -notmatch [regex]::Escape("## $VersionTag")) {
        Set-Content -Path $path -Value ($old.TrimEnd() + "`r`n`r`n" + $entry) -Encoding UTF8
        Write-Log "CHANGELOG.md updated"
    }
}

function Ensure-ReleaseIgnore {
    $path = Join-Path $script:ProjectRoot '.releaseignore'
    if (!(Test-Path $path)) {
        @'
.git
.venv
__pycache__
.pytest_cache
releases
*.pyc
*.pyo
*.log
.DS_Store
Thumbs.db
'@ | Set-Content -Path $path -Encoding UTF8
    }
}

function Get-ReleaseItems {
    $excludeFile = Join-Path $script:ProjectRoot '.releaseignore'
    $patterns = @()
    if (Test-Path $excludeFile) {
        $patterns = Get-Content $excludeFile -Encoding UTF8 | Where-Object { $_ -and $_.Trim() -ne '' }
    }
    Get-ChildItem -Force -Recurse -Path $script:ProjectRoot | Where-Object {
        $rel = $_.FullName.Substring($script:ProjectRoot.Length).TrimStart('\')
        if (-not $rel) { return $false }
        foreach ($p in $patterns) {
            if ($rel -like $p -or $rel -like ($p + '\*')) { return $false }
        }
        return $true
    }
}

function Build-Zip {
    param([string]$VersionTag)
    $releasesDir = Join-Path $script:ProjectRoot 'releases'
    Ensure-Dir $releasesDir
    $zipName = "chat-bot-v2-$VersionTag.zip"
    $zipPath = Join-Path $releasesDir $zipName
    if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

    $tmp = Join-Path $env:TEMP ("release_" + [guid]::NewGuid().ToString())
    $stage = Join-Path $tmp 'chat-bot-v2'
    Ensure-Dir $stage

    foreach ($item in Get-ReleaseItems) {
        $rel = $item.FullName.Substring($script:ProjectRoot.Length).TrimStart('\')
        $dest = Join-Path $stage $rel
        if ($item.PSIsContainer) {
            Ensure-Dir $dest
        } else {
            Ensure-Dir (Split-Path $dest -Parent)
            Copy-Item $item.FullName $dest -Force
        }
    }

    Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $zipPath -Force
    Remove-Item $tmp -Recurse -Force

    Verify-Zip -ZipPath $zipPath
    return $zipPath
}

function Verify-Zip {
    param([string]$ZipPath)
    if (!(Test-Path $ZipPath)) { throw "ZIP not found: $ZipPath" }
    $size = (Get-Item $ZipPath).Length
    if ($size -le 1024) { throw "ZIP too small: $size bytes" }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $z = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
    try {
        if ($z.Entries.Count -lt 5) { throw "ZIP has too few entries: $($z.Entries.Count)" }
    } finally {
        $z.Dispose()
    }
    Write-Log "ZIP verified: $ZipPath ($size bytes)"
}

function Commit-And-Push {
    param([string]$VersionTag)
    Invoke-Git @('add','-A')

    & $script:GitExe diff --cached --quiet
    if ($LASTEXITCODE -ne 0) {
        Invoke-Git @('commit','-m',$VersionTag)
        Write-Log "Commit created: $VersionTag"
    } else {
        Write-Log "No staged changes to commit"
    }

    Invoke-Git @('fetch','origin')
    Write-Log "Fetch completed"
    Write-Log "Push mode: single-owner / force-with-lease / no rebase"
    Invoke-Git @('push','--force-with-lease','origin','main')
    Write-Log "GitHub updated with local state"
}

try {
    $script:ProjectRoot = (Get-Location).Path
    Ensure-Dir (Join-Path $script:ProjectRoot 'logs')
    $script:LogFile = Join-Path $script:ProjectRoot 'logs\release_automation.log'
    if (Test-Path $script:LogFile) { Remove-Item $script:LogFile -Force }
    New-Item -ItemType File -Path $script:LogFile -Force | Out-Null

    $script:GitExe = Get-GitExe
    Write-Log "Git detected: $script:GitExe"

    & $script:GitExe rev-parse --is-inside-work-tree *> $null
    if ($LASTEXITCODE -ne 0) { throw "Current folder is not a Git repository." }

    if (Test-Path (Join-Path $script:ProjectRoot '.git\rebase-merge')) {
        Write-Log "Unfinished rebase detected, aborting automatically"
        Try-Invoke-Git @('rebase','--abort') | Out-Null
    }
    if (Test-Path (Join-Path $script:ProjectRoot '.git\rebase-apply')) {
        Write-Log "Unfinished rebase apply detected, aborting automatically"
        Try-Invoke-Git @('rebase','--abort') | Out-Null
    }
    if (Test-Path (Join-Path $script:ProjectRoot '.git\MERGE_HEAD')) {
        Write-Log "Unfinished merge detected, aborting automatically"
        Try-Invoke-Git @('merge','--abort') | Out-Null
    }

    $versionTag = Get-VersionTag
    Write-Log "Version selected: $versionTag"

    Ensure-TextFiles
    Ensure-ReleaseIgnore
    Build-Manifest
    Update-Changelog -VersionTag $versionTag
    Commit-And-Push -VersionTag $versionTag
    $zip = Build-Zip -VersionTag $versionTag
    Write-Log "Release created: $zip"
    exit 0
}
catch {
    Write-Log ("FATAL: " + $_.Exception.Message)
    exit 1
}

