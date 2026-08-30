#Requires -Version 7.0
[CmdletBinding()]
param([Parameter(Mandatory)][string]$Bundle)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'kb-backup-common.ps1')

function Write-VerifyResult {
    param([int]$Code, [string]$Status, [string[]]$Issues)
    [pscustomobject][ordered]@{ status=$Status; bundle=$Bundle; errors=@($Issues).Count; issues=@($Issues) } | ConvertTo-Json -Depth 8
    exit $Code
}

function Test-SafePortablePath {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path) -or [IO.Path]::IsPathRooted($Path)) { return $false }
    $parts = $Path.Replace('\', '/').Split('/')
    return -not (@($parts | Where-Object { $_ -eq '' -or $_ -eq '.' -or $_ -eq '..' }).Count -gt 0)
}

try {
    if (-not (Test-Path -LiteralPath $Bundle -PathType Container)) { throw "FATAL: bundle directory does not exist: $Bundle" }
    Assert-KbNoRedirectingReparsePoint -Path $Bundle -Label 'portable bundle' | Out-Null
    $bundleFull = Get-KbFullPath (Resolve-Path -LiteralPath $Bundle).Path
    $bundleFiles = @(Get-KbSafeTreeFiles -Root $bundleFull -Label 'portable bundle')
    $issues = [Collections.Generic.List[string]]::new()

    foreach ($required in @('kb.yaml', 'content', 'external', 'backup-manifest.json', 'CHECKSUMS.sha256', 'backup-report.md', 'README-RESTORE.md')) {
        if (-not (Test-Path -LiteralPath (Join-Path $bundleFull $required))) { $issues.Add("missing required bundle member: $required") }
    }
    if ($issues.Count -gt 0) { Write-VerifyResult 2 'invalid' $issues }

    try { $metadata = Get-Content -LiteralPath (Join-Path $bundleFull 'backup-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json }
    catch { $issues.Add("manifest JSON invalid: $($_.Exception.Message)"); Write-VerifyResult 3 'fatal' $issues }
    if ($metadata.schema -ne 'portable-kb-backup-manifest' -or $metadata.schema_version -ne 1 -or -not $metadata.completeness.complete) {
        $issues.Add('manifest does not claim a complete supported backup')
    }

    $checksumRecords = @{}
    foreach ($line in Get-Content -LiteralPath (Join-Path $bundleFull 'CHECKSUMS.sha256') -Encoding UTF8) {
        if ($line -notmatch '^(?<hash>[0-9a-fA-F]{64})\s\s(?<path>.+)$') { $issues.Add("invalid checksum record: $line"); continue }
        $relative = $Matches.path.Replace('\', '/')
        if (-not (Test-SafePortablePath $relative)) { $issues.Add("unsafe checksum path: $relative"); continue }
        $target = Get-KbFullPath (Join-Path $bundleFull $relative.Replace('/', '\'))
        if (-not (Test-KbPathInside $target $bundleFull)) { $issues.Add("checksum path escapes bundle: $relative"); continue }
        if ($checksumRecords.ContainsKey($relative)) { $issues.Add("duplicate checksum record: $relative"); continue }
        $checksumRecords[$relative] = $Matches.hash.ToLowerInvariant()
        if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { $issues.Add("checksum file missing: $relative") }
        elseif ((Get-KbSha256 $target) -ne $checksumRecords[$relative]) { $issues.Add("checksum mismatch: $relative") }
    }
    $checksumPath = Join-Path $bundleFull 'CHECKSUMS.sha256'
    foreach ($file in $bundleFiles | Where-Object { -not $_.FullName.Equals($checksumPath, [StringComparison]::OrdinalIgnoreCase) }) {
        $relative = Get-KbRelativePath $bundleFull $file.FullName
        if (-not $checksumRecords.ContainsKey($relative)) { $issues.Add("checksum missing for bundle file: $relative") }
    }

    $manifestFiles = @{}
    $manifestExternal = @{}
    foreach ($file in @($metadata.files)) {
        $kind = [string]$file.kind
        $relative = ([string]$file.portable_path).Replace('\', '/')
        if ($kind -notin @('kb_manifest', 'content', 'external')) { $issues.Add("unsupported manifest file kind: $kind ($relative)"); continue }
        if (-not (Test-SafePortablePath $relative)) { $issues.Add("unsafe manifest portable path: $relative"); continue }
        $kindMatches = ($kind -eq 'kb_manifest' -and $relative -eq 'kb.yaml') -or
            ($kind -eq 'content' -and $relative.StartsWith('content/', [StringComparison]::OrdinalIgnoreCase)) -or
            ($kind -eq 'external' -and $relative.StartsWith('external/', [StringComparison]::OrdinalIgnoreCase))
        if (-not $kindMatches) { $issues.Add("manifest kind/path mismatch: $kind -> $relative"); continue }
        if ($manifestFiles.ContainsKey($relative)) { $issues.Add("duplicate manifest portable path: $relative"); continue }
        $manifestFiles[$relative] = $file
        if ($kind -eq 'external') { $manifestExternal[$relative] = $true }
        $target = Get-KbFullPath (Join-Path $bundleFull $relative.Replace('/', '\'))
        if (-not $checksumRecords.ContainsKey($relative)) { $issues.Add("manifest file lacks checksum: $relative") }
        if (-not (Test-KbPathInside $target $bundleFull) -or -not (Test-Path -LiteralPath $target -PathType Leaf)) { $issues.Add("manifest file missing or escaping: $relative"); continue }
        if ([string]$file.sha256 -notmatch '^[0-9a-fA-F]{64}$' -or (Get-KbSha256 $target) -ne ([string]$file.sha256).ToLowerInvariant()) {
            $issues.Add("manifest hash mismatch: $relative")
        }
    }

    foreach ($file in $bundleFiles) {
        $relative = Get-KbRelativePath $bundleFull $file.FullName
        $isRestoreMember = $relative -eq 'kb.yaml' -or
            $relative.StartsWith('content/', [StringComparison]::OrdinalIgnoreCase) -or
            $relative.StartsWith('external/', [StringComparison]::OrdinalIgnoreCase)
        if ($isRestoreMember -and -not $manifestFiles.ContainsKey($relative)) { $issues.Add("unmanifested restore file: $relative") }
    }

    foreach ($reference in @($metadata.references)) {
        $portablePath = ([string]$reference.portable_path).Replace('\', '/')
        if (-not $manifestExternal.ContainsKey($portablePath)) { $issues.Add("reference has no manifest external file: $portablePath") }
    }
    foreach ($external in $bundleFiles | Where-Object { (Get-KbRelativePath $bundleFull $_.FullName).StartsWith('external/', [StringComparison]::OrdinalIgnoreCase) }) {
        $relative = Get-KbRelativePath $bundleFull $external.FullName
        if (-not $manifestExternal.ContainsKey($relative)) { $issues.Add("unmanifested external file: $relative") }
    }

    foreach ($markdown in $bundleFiles | Where-Object {
        (Get-KbRelativePath $bundleFull $_.FullName).StartsWith('content/', [StringComparison]::OrdinalIgnoreCase) -and $_.Extension -ieq '.md'
    }) {
        foreach ($line in Get-Content -LiteralPath $markdown.FullName -Encoding UTF8) {
            foreach ($link in Get-KbLinksInLine $line) {
                $target = [string]$link.Target
                if ($target -match '^[A-Za-z][A-Za-z0-9+.-]*:' -or $target.StartsWith('#')) { continue }
                $pathPart = (($target -split '#', 2)[0] -split '\?', 2)[0]
                if ([string]::IsNullOrWhiteSpace($pathPart)) { continue }
                $resolved = Get-KbFullPath (Join-Path (Split-Path -Parent $markdown.FullName) ([uri]::UnescapeDataString($pathPart).Replace('/', '\')))
                $portable = $line -match '(?i)<!--\s*kb-portable-source\s*-->'
                $allowedRoot = if ($portable) { Join-Path $bundleFull 'external' } else { Join-Path $bundleFull 'content' }
                if (-not (Test-KbPathInside $resolved $allowedRoot)) { $issues.Add("portable link escapes its allowed root: $($markdown.Name) -> $target") }
                elseif (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) { $issues.Add("portable link missing: $($markdown.Name) -> $target") }
            }
        }
    }

    $audit = & (Join-Path $PSScriptRoot 'kb-audit.ps1') -Root $bundleFull -Format Json
    if ($LASTEXITCODE -ne 0) { $issues.Add("knowledge-base audit failed: $($audit -join ' ')") }
    if ($issues.Count -gt 0) { Write-VerifyResult 2 'invalid' $issues }
    Write-VerifyResult 0 'valid' @()
}
catch { Write-VerifyResult 3 'fatal' @($_.Exception.Message) }
