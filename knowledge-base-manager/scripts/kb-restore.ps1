#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Bundle,
    [Parameter(Mandatory)][string]$Destination,
    [ValidateSet('Portable', 'Relink')][string]$Mode = 'Portable',
    [string]$ProjectRootMap,
    [switch]$Execute
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'kb-backup-common.ps1')
$staging = $null

function Write-RestoreResult {
    param([int]$Code, [string]$Status, [string]$Message, $Data=$null)
    [pscustomobject][ordered]@{status=$Status; message=$Message; execute=[bool]$Execute; data=$Data} | ConvertTo-Json -Depth 12
    exit $Code
}

function Test-RestorePortablePath {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path) -or [IO.Path]::IsPathRooted($Path)) { return $false }
    $parts = $Path.Replace('\', '/').Split('/')
    return -not (@($parts | Where-Object { $_ -eq '' -or $_ -eq '.' -or $_ -eq '..' }).Count -gt 0)
}

function Get-ByteArraySha256 {
    param([Parameter(Mandatory)][byte[]]$Bytes)
    $hasher = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($hasher.ComputeHash($Bytes))).Replace('-', '').ToLowerInvariant() }
    finally { $hasher.Dispose() }
}

try {
    if ($Mode -eq 'Relink') { throw 'BLOCKER: Relink restore is not implemented in v1; Portable mode is the supported production path.' }
    if (-not (Test-Path -LiteralPath $Bundle -PathType Container)) { throw "FATAL: bundle directory does not exist: $Bundle" }
    Assert-KbNoRedirectingReparsePoint -Path $Bundle -Label 'portable bundle' | Out-Null
    $bundleFull = Get-KbFullPath (Resolve-Path -LiteralPath $Bundle).Path
    Get-KbSafeTreeFiles -Root $bundleFull -Label 'portable bundle' | Out-Null

    $destinationFull = Get-KbFullPath $Destination
    Assert-KbNoRedirectingReparsePoint -Path $destinationFull -Label 'restore destination' | Out-Null
    if (Test-KbPathInside $destinationFull $bundleFull) { throw 'BLOCKER: restore destination must not be inside the bundle' }
    if (Test-Path -LiteralPath $destinationFull) { throw 'BLOCKER: restore destination must not already exist; restore never overwrites' }

    # Pin the exact manifest that the verifier examines. A later manifest or
    # source-file change is detected before publication.
    $manifestPath = Join-Path $bundleFull 'backup-manifest.json'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw 'BLOCKER: backup manifest is missing' }
    $manifestBytes = [IO.File]::ReadAllBytes($manifestPath)
    $manifestHash = Get-ByteArraySha256 $manifestBytes
    try { $metadata = [Text.UTF8Encoding]::new($false, $true).GetString($manifestBytes) | ConvertFrom-Json }
    catch { throw "BLOCKER: backup manifest JSON is invalid: $($_.Exception.Message)" }

    $verify = & (Join-Path $PSScriptRoot 'kb-verify-backup.ps1') -Bundle $bundleFull
    if ($LASTEXITCODE -ne 0) { throw "BLOCKER: bundle verification failed: $($verify -join ' ')" }
    if ((Get-KbSha256 $manifestPath) -ne $manifestHash) { throw 'BLOCKER: backup manifest changed during verification' }

    $seen = @{}
    $records = [Collections.Generic.List[object]]::new()
    foreach ($file in @($metadata.files)) {
        $kind = [string]$file.kind
        $relative = ([string]$file.portable_path).Replace('\', '/')
        if ($kind -notin @('kb_manifest', 'content', 'external') -or -not (Test-RestorePortablePath $relative)) {
            throw "BLOCKER: unsupported or unsafe restore record: $kind -> $relative"
        }
        $kindMatches = ($kind -eq 'kb_manifest' -and $relative -eq 'kb.yaml') -or
            ($kind -eq 'content' -and $relative.StartsWith('content/', [StringComparison]::OrdinalIgnoreCase)) -or
            ($kind -eq 'external' -and $relative.StartsWith('external/', [StringComparison]::OrdinalIgnoreCase))
        if (-not $kindMatches -or $seen.ContainsKey($relative)) { throw "BLOCKER: duplicate or mismatched restore record: $kind -> $relative" }
        $seen[$relative] = $true
        $expectedHash = ([string]$file.sha256).ToLowerInvariant()
        if ($expectedHash -notmatch '^[0-9a-f]{64}$') { throw "BLOCKER: invalid expected hash for restore record: $relative" }
        $source = Get-KbFullPath (Join-Path $bundleFull $relative.Replace('/', '\'))
        if (-not (Test-KbPathInside $source $bundleFull) -or -not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "BLOCKER: restore source is missing or escaping: $relative" }
        $records.Add([pscustomobject][ordered]@{ kind=$kind; portable_path=$relative; source=$source; sha256=$expectedHash })
    }
    if (-not $seen.ContainsKey('kb.yaml')) { throw 'BLOCKER: restore manifest does not contain kb.yaml' }
    if ($metadata.schema -ne 'portable-kb-backup-manifest' -or $metadata.schema_version -ne 1 -or -not $metadata.completeness.complete) {
        throw 'BLOCKER: pinned restore manifest is not a complete supported backup'
    }

    # Independently bind the pinned manifest to the complete current restore
    # set. This remains decisive even if an untrusted process races the earlier
    # whole-bundle verifier.
    $actualRestoreFiles = @{}
    foreach ($file in Get-KbSafeTreeFiles -Root $bundleFull -Label 'portable bundle') {
        $relative = Get-KbRelativePath $bundleFull $file.FullName
        if ($relative -eq 'kb.yaml' -or
            $relative.StartsWith('content/', [StringComparison]::OrdinalIgnoreCase) -or
            $relative.StartsWith('external/', [StringComparison]::OrdinalIgnoreCase)) {
            $actualRestoreFiles[$relative] = $true
        }
    }
    foreach ($relative in $actualRestoreFiles.Keys) {
        if (-not $seen.ContainsKey($relative)) { throw "BLOCKER: pinned manifest omits restore file: $relative" }
    }
    foreach ($relative in $seen.Keys) {
        if (-not $actualRestoreFiles.ContainsKey($relative)) { throw "BLOCKER: pinned manifest restore file is missing: $relative" }
    }
    foreach ($record in $records) {
        if ((Get-KbSha256 $record.source) -ne $record.sha256) { throw "BLOCKER: pinned manifest hash mismatch: $($record.portable_path)" }
    }
    if ((Get-KbSha256 $manifestPath) -ne $manifestHash) { throw 'BLOCKER: backup manifest changed while binding restore files' }

    $plan = [pscustomobject]@{
        bundle=$bundleFull
        destination=$destinationFull
        mode=$Mode
        source_members=@('kb.yaml','content','external')
        file_count=$records.Count
        manifest_sha256=$manifestHash
    }
    if (-not $Execute) { Write-RestoreResult 0 'plan' 'Verification succeeded. Re-run with -Execute to restore into this non-existent destination.' $plan }

    if (Test-Path -LiteralPath $destinationFull) { throw 'BLOCKER: restore destination appeared after planning; restore never overwrites' }
    $parent = Split-Path -Parent $destinationFull
    Assert-KbNoRedirectingReparsePoint -Path $parent -Label 'restore destination parent' | Out-Null
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    Assert-KbNoRedirectingReparsePoint -Path $parent -Label 'restore destination parent' | Out-Null
    $staging = Join-Path $parent ('.restore-incomplete-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $staging -ErrorAction Stop | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $staging 'content') -ErrorAction Stop | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $staging 'external') -ErrorAction Stop | Out-Null
    Assert-KbNoRedirectingReparsePoint -Path $staging -Label 'restore staging directory' | Out-Null

    foreach ($record in $records) {
        Assert-KbNoRedirectingReparsePoint -Path $record.source -Label 'restore source' | Out-Null
        if ((Get-KbSha256 $record.source) -ne $record.sha256) { throw "FATAL: restore source changed before copy: $($record.portable_path)" }
        $target = Get-KbFullPath (Join-Path $staging $record.portable_path.Replace('/', '\'))
        if (-not (Test-KbPathInside $target $staging)) { throw "FATAL: restore target escaped staging: $($record.portable_path)" }
        $targetParent = Split-Path -Parent $target
        New-Item -ItemType Directory -Path $targetParent -Force | Out-Null
        Assert-KbNoRedirectingReparsePoint -Path $targetParent -Label 'restore staging path' | Out-Null
        [IO.File]::Copy($record.source, $target, $false)
        if ((Get-KbSha256 $record.source) -ne $record.sha256) { throw "FATAL: restore source changed during copy: $($record.portable_path)" }
        if ((Get-KbSha256 $target) -ne $record.sha256) { throw "FATAL: restored file hash differs: $($record.portable_path)" }
    }

    $audit = & (Join-Path $PSScriptRoot 'kb-audit.ps1') -Root $staging -Format Json
    if ($LASTEXITCODE -ne 0) { throw "FATAL: restored knowledge base did not pass audit: $($audit -join ' ')" }
    foreach ($record in $records) {
        $target = Get-KbFullPath (Join-Path $staging $record.portable_path.Replace('/', '\'))
        if ((Get-KbSha256 $record.source) -ne $record.sha256 -or (Get-KbSha256 $target) -ne $record.sha256) {
            throw "FATAL: restore source or staging changed before publication: $($record.portable_path)"
        }
    }
    if ((Get-KbSha256 $manifestPath) -ne $manifestHash) { throw 'FATAL: backup manifest changed before publication' }
    Get-KbSafeTreeFiles -Root $staging -Label 'restore staging tree' | Out-Null
    Assert-KbNoRedirectingReparsePoint -Path $parent -Label 'restore destination parent' | Out-Null
    if (Test-Path -LiteralPath $destinationFull) { throw 'BLOCKER: restore destination appeared before publication; restore never overwrites' }
    [IO.Directory]::Move($staging, $destinationFull)
    Write-RestoreResult 0 'restored' 'Portable restore completed atomically and passed hash and knowledge-base audit checks.' $plan
}
catch {
    $code = if ($_.Exception.Message.StartsWith('FATAL:')) { 3 } else { 2 }
    $data = if ($null -ne $staging -and (Test-Path -LiteralPath $staging)) { [pscustomobject]@{ incomplete_restore=$staging } } else { $null }
    Write-RestoreResult $code 'blocked' $_.Exception.Message $data
}
