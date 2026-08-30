#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Root,
    [Parameter(Mandatory)][string]$Destination,
    [ValidateSet('ReferenceComplete', 'ProjectSnapshot')][string]$Mode = 'ReferenceComplete',
    [string[]]$IgnoreLegacyPath = @(),
    [switch]$Execute,
    [string]$ConfirmedPlanDigest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'kb-backup-common.ps1')
$staging = $null
$reconfirmPlan = $null
$reconfirmSummary = @()

function Write-BackupResult {
    param([int]$Code, [string]$Status, [string]$Message, $Data = $null)
    [pscustomobject][ordered]@{ status = $Status; message = $Message; execute = [bool]$Execute; data = $Data } | ConvertTo-Json -Depth 24
    exit $Code
}

function Get-PlanData {
    param([Parameter(Mandatory)]$Plan, [string[]]$ChangeSummary = @(), [string]$IncompleteBundle = $null)
    $data = [ordered]@{ plan = $Plan; change_summary = @($ChangeSummary) }
    if (-not [string]::IsNullOrWhiteSpace($IncompleteBundle)) { $data.incomplete_bundle = $IncompleteBundle }
    return [pscustomobject]$data
}

function Stop-Reconfirm {
    param([Parameter(Mandatory)]$ExpectedPlan, [Parameter(Mandatory)]$ActualPlan)
    $script:reconfirmPlan = $ActualPlan
    $script:reconfirmSummary = Get-KbPlanChangeSummary -Expected $ExpectedPlan -Actual $ActualPlan
    throw 'RECONFIRM: the source snapshot changed; obtain confirmation for the newly listed plan.'
}

function Assert-ConfirmedPlanCurrent {
    param([Parameter(Mandatory)]$ExpectedPlan, [Parameter(Mandatory)][string]$KbRoot, [Parameter(Mandatory)][string]$Destination, [Parameter(Mandatory)][string]$Mode, [string[]]$IgnoreLegacyPath)
    $actual = Get-KbBackupPlan -KbRoot $KbRoot -Destination $Destination -Mode $Mode -IgnoreLegacyPath $IgnoreLegacyPath
    if ($actual.plan_digest -cne $ExpectedPlan.plan_digest) { Stop-Reconfirm -ExpectedPlan $ExpectedPlan -ActualPlan $actual }
    return $actual
}

function Assert-RecordCurrent {
    param([Parameter(Mandatory)]$Record)
    if (-not (Test-KbSnapshotRecord $Record)) {
        $script:reconfirmSummary = @("source changed during copy: $($Record.kind) $($Record.source_path)")
        throw 'RECONFIRM: a source file changed during copy.'
    }
}

try {
    if ($Mode -eq 'ProjectSnapshot') { throw 'BLOCKER: ProjectSnapshot is deliberately deferred in v1; use ReferenceComplete.' }
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) { throw "FATAL: knowledge-base root does not exist: $Root" }
    $kbRoot = Get-KbFullPath (Resolve-Path -LiteralPath $Root).Path
    $plan = Get-KbBackupPlan -KbRoot $kbRoot -Destination $Destination -Mode $Mode -IgnoreLegacyPath $IgnoreLegacyPath
    if (Test-Path -LiteralPath $plan.bundle) { throw "BLOCKER: bundle already exists and will not be overwritten: $($plan.bundle)" }
    if (-not $Execute) {
        Write-BackupResult 0 'plan' 'Read-only plan succeeded. Display every listed source path, obtain explicit confirmation, then pass this exact plan_digest with -Execute -ConfirmedPlanDigest.' (Get-PlanData $plan)
    }
    if ([string]::IsNullOrWhiteSpace($ConfirmedPlanDigest)) {
        Write-BackupResult 2 'confirmation_required' 'Execution requires a post-plan confirmation. Re-run with the exact plan_digest returned by the current full plan.' (Get-PlanData $plan)
    }
    if ($ConfirmedPlanDigest -cne $plan.plan_digest) {
        Write-BackupResult 2 'reconfirm_required' 'The supplied plan digest does not match the current full plan. Review the new list and confirm it again.' (Get-PlanData $plan @('supplied plan_digest does not match the current plan; the prior snapshot is not available to compare'))
    }

    # This is the last pre-write gate. No destination or staging directory exists before it.
    $confirmedPlan = Assert-ConfirmedPlanCurrent -ExpectedPlan $plan -KbRoot $kbRoot -Destination $Destination -Mode $Mode -IgnoreLegacyPath $IgnoreLegacyPath
    if (Test-Path -LiteralPath $confirmedPlan.bundle) { throw "BLOCKER: bundle already exists and will not be overwritten: $($confirmedPlan.bundle)" }
    $references = Get-KbBackupReferences -Manifest (Read-KbManifest $kbRoot) -KbRoot $kbRoot -IgnoreLegacyPath $IgnoreLegacyPath

    $backupId = [guid]::NewGuid().ToString()
    Assert-KbNoRedirectingReparsePoint -Path $confirmedPlan.destination -Label 'backup destination' | Out-Null
    New-Item -ItemType Directory -Path $confirmedPlan.destination -Force | Out-Null
    Assert-KbNoRedirectingReparsePoint -Path $confirmedPlan.destination -Label 'backup destination' | Out-Null
    $staging = Join-Path $confirmedPlan.destination ('.incomplete-' + $backupId)
    New-Item -ItemType Directory -Path $staging -ErrorAction Stop | Out-Null
    Assert-KbNoRedirectingReparsePoint -Path $staging -Label 'backup staging directory' | Out-Null
    $bundle = $staging
    $bundleContent = Join-Path $bundle 'content'
    New-Item -ItemType Directory -Path $bundleContent -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $bundle 'external\\projects') -Force | Out-Null

    $fileRecords = [Collections.Generic.List[object]]::new()
    $manifestRecord = @($confirmedPlan.files | Where-Object kind -eq 'kb_manifest')
    if ($manifestRecord.Count -ne 1) { throw 'FATAL: confirmed plan has no unique kb.yaml record' }
    Assert-RecordCurrent $manifestRecord[0]
    Add-KbPortableManifestField -SourceManifest $manifestRecord[0].source_path -DestinationManifest (Join-Path $bundle 'kb.yaml')
    Assert-RecordCurrent $manifestRecord[0]
    $fileRecords.Add([pscustomobject][ordered]@{ kind='kb_manifest'; source_path=$manifestRecord[0].source_path; portable_path='kb.yaml'; size_bytes=$manifestRecord[0].size_bytes; mtime_utc=$manifestRecord[0].mtime_utc; source_sha256=$manifestRecord[0].sha256; sha256=Get-KbSha256 (Join-Path $bundle 'kb.yaml'); copy_status='copied' })

    foreach ($record in @($confirmedPlan.files | Where-Object kind -eq 'content')) {
        Assert-RecordCurrent $record
        $copied = Join-Path $bundle $record.portable_path.Replace('/', '\\')
        if (-not (Test-KbPathInside $copied $bundle)) { throw "FATAL: content portable path escaped bundle: $($record.portable_path)" }
        New-Item -ItemType Directory -Path (Split-Path -Parent $copied) -Force | Out-Null
        Assert-KbNoRedirectingReparsePoint -Path (Split-Path -Parent $copied) -Label 'backup staging path' | Out-Null
        [IO.File]::Copy($record.source_path, $copied, $false)
        Assert-RecordCurrent $record
        if ((Get-KbSha256 $copied) -ne $record.sha256) { throw "FATAL: copied content hash differs: $($record.source_path)" }
        $fileRecords.Add([pscustomobject][ordered]@{ kind='content'; source_path=$record.source_path; portable_path=$record.portable_path; size_bytes=$record.size_bytes; mtime_utc=$record.mtime_utc; source_sha256=$record.sha256; sha256=$record.sha256; copy_status='copied' })
    }
    foreach ($record in @($confirmedPlan.files | Where-Object kind -eq 'external')) {
        Assert-RecordCurrent $record
        $targetFull = Join-Path $bundle $record.portable_path.Replace('/', '\\')
        if (-not (Test-KbPathInside $targetFull $bundle)) { throw "FATAL: external portable path escaped bundle: $($record.portable_path)" }
        New-Item -ItemType Directory -Path (Split-Path -Parent $targetFull) -Force | Out-Null
        Assert-KbNoRedirectingReparsePoint -Path (Split-Path -Parent $targetFull) -Label 'backup staging path' | Out-Null
        [IO.File]::Copy($record.source_path, $targetFull, $false)
        Assert-RecordCurrent $record
        if ((Get-KbSha256 $targetFull) -ne $record.sha256) { throw "FATAL: copied external hash differs: $($record.source_path)" }
        $fileRecords.Add([pscustomobject][ordered]@{ kind='external'; source_path=$record.source_path; portable_path=$record.portable_path; size_bytes=$record.size_bytes; mtime_utc=$record.mtime_utc; source_sha256=$record.sha256; sha256=$record.sha256; copy_status='copied'; project_id=$record.project_id; project_relative_source=$record.project_relative_source })
    }

    # Only marked, copied Markdown source locators are rewritten; all other prose remains intact.
    foreach ($referrer in @($references.References | Group-Object Referrer)) {
        $copyPath = Join-Path $bundleContent $referrer.Name.Replace('/', '\\')
        $lines = [Collections.Generic.List[string]](Get-Content -LiteralPath $copyPath -Encoding UTF8)
        foreach ($lineGroup in @($referrer.Group | Group-Object Line)) {
            $index = [int]$lineGroup.Name - 1
            $original = $lineGroup.Group[0].OriginalLine
            if ($lines[$index] -cne $original) { throw "FATAL: copied Markdown changed after scan before rewrite: $($referrer.Name):$($index + 1)" }
            $working = $lines[$index]
            foreach ($reference in @($lineGroup.Group | Sort-Object LinkStart -Descending)) {
                $matchText = $working.Substring($reference.LinkStart, $reference.LinkLength)
                $targetStart = $matchText.IndexOf('(')
                $targetAt = $matchText.IndexOf($reference.OriginalTarget, $targetStart, [StringComparison]::Ordinal)
                if ($targetAt -lt 0) { throw "FATAL: registered Markdown link target no longer matches scan: $($referrer.Name):$($index + 1)" }
                $portableTarget = Join-Path $bundle ("external/projects/$($reference.ProjectId)/$($reference.Relative)".Replace('/', '\\'))
                $relativeTarget = [IO.Path]::GetRelativePath((Split-Path -Parent $copyPath), $portableTarget).Replace('\\', '/')
                $newMatch = $matchText.Substring(0, $targetAt) + $relativeTarget + $matchText.Substring($targetAt + $reference.OriginalTarget.Length)
                $working = $working.Substring(0, $reference.LinkStart) + $newMatch + $working.Substring($reference.LinkStart + $reference.LinkLength)
            }
            $lines[$index] = $working.Replace('<!-- kb-external-local -->', '<!-- kb-portable-source -->')
        }
        [IO.File]::WriteAllLines($copyPath, $lines, [Text.UTF8Encoding]::new($false))
    }
    foreach ($record in @($fileRecords | Where-Object kind -eq 'content')) { $record.sha256 = Get-KbSha256 (Join-Path $bundle $record.portable_path.Replace('/', '\\')) }

    $manifestObject = [pscustomobject][ordered]@{
        schema = 'portable-kb-backup-manifest'; schema_version = 1; backup_id = $backupId; created_utc = [DateTime]::UtcNow.ToString('o'); mode = $Mode; plan_digest = $confirmedPlan.plan_digest
        completeness = [pscustomobject]@{ complete=$true; blockers=@(); ignored_legacy_paths=@($confirmedPlan.ignored_legacy_paths) }
        source = [pscustomobject]@{ kb_root=$kbRoot; content_dir=$confirmedPlan.content_dir; kb_manifest='kb.yaml' }
        files = @($fileRecords); references = @($confirmedPlan.reference_mappings)
        totals = $confirmedPlan.totals
    }
    $report = @('# Portable knowledge-base backup', '', "- Backup ID: $backupId", "- Mode: $Mode", "- Confirmed plan digest: $($confirmedPlan.plan_digest)", '- Complete: true', "- Content files: $($manifestObject.totals.content_files)", "- External files: $($manifestObject.totals.external_files)", '', 'Restore with kb-restore.ps1 -Bundle <portable-kb> -Destination <new-root> -Execute. The destination must not already exist.') -join "`n"
    [IO.File]::WriteAllText((Join-Path $bundle 'backup-report.md'), $report + "`n", [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText((Join-Path $bundle 'README-RESTORE.md'), "# Restore`n`nThis bundle is self-contained. Verify it before restore, then restore only into a destination that does not already exist. The original paths in backup-manifest.json are provenance only. CHECKSUMS.sha256 detects accidental or untrusted modification only when the checksum file itself is trusted; it is not a digital signature.`n", [Text.UTF8Encoding]::new($false))
    $manifestObject | ConvertTo-Json -Depth 24 | Set-Content -LiteralPath (Join-Path $bundle 'backup-manifest.json') -Encoding UTF8 -NoNewline
    $checksumPath = Join-Path $bundle 'CHECKSUMS.sha256'
    $checksumFiles = @(Get-KbSafeTreeFiles -Root $bundle -Label 'backup staging tree' | Where-Object { -not $_.FullName.Equals($checksumPath, [StringComparison]::OrdinalIgnoreCase) } | Sort-Object FullName)
    $checksums = foreach ($file in $checksumFiles) { "$(Get-KbSha256 $file.FullName)  $(Get-KbRelativePath $bundle $file.FullName)" }
    [IO.File]::WriteAllLines($checksumPath, @($checksums), [Text.UTF8Encoding]::new($false))
    $verifyOutput = & (Join-Path $PSScriptRoot 'kb-verify-backup.ps1') -Bundle $bundle
    if ($LASTEXITCODE -ne 0) { throw "FATAL: staging verification failed: $($verifyOutput -join ' ')" }
    $auditOutput = & (Join-Path $PSScriptRoot 'kb-audit.ps1') -Root $bundle -Format Json
    if ($LASTEXITCODE -ne 0) { throw "FATAL: staging knowledge-base audit failed: $($auditOutput -join ' ')" }
    Assert-ConfirmedPlanCurrent -ExpectedPlan $confirmedPlan -KbRoot $kbRoot -Destination $Destination -Mode $Mode -IgnoreLegacyPath $IgnoreLegacyPath | Out-Null
    Get-KbSafeTreeFiles -Root $bundle -Label 'backup staging tree' | Out-Null
    Assert-KbNoRedirectingReparsePoint -Path $confirmedPlan.destination -Label 'backup destination' | Out-Null
    if (Test-Path -LiteralPath $confirmedPlan.bundle) { throw "BLOCKER: bundle appeared before publication and will not be overwritten: $($confirmedPlan.bundle)" }
    [IO.Directory]::Move($bundle, $confirmedPlan.bundle)
    Write-BackupResult 0 'created' 'Portable ReferenceComplete backup created from the confirmed plan and verified before publication.' (Get-PlanData $confirmedPlan)
}
catch {
    if ($_.Exception.Message.StartsWith('RECONFIRM:')) {
        if ($null -eq $reconfirmPlan) {
            try { $reconfirmPlan = Get-KbBackupPlan -KbRoot $kbRoot -Destination $Destination -Mode $Mode -IgnoreLegacyPath $IgnoreLegacyPath }
            catch { $reconfirmSummary = @($reconfirmSummary + "current plan could not be rebuilt: $($_.Exception.Message)") }
        }
        $data = if ($null -ne $reconfirmPlan) { Get-PlanData $reconfirmPlan $reconfirmSummary $staging } else { [pscustomobject]@{ plan=$null; change_summary=@($reconfirmSummary); incomplete_bundle=$staging } }
        Write-BackupResult 2 'reconfirm_required' 'The source snapshot changed. No portable-kb was published; review the current plan and confirm again.' $data
    }
    $code = if ($_.Exception.Message.StartsWith('FATAL:')) { 3 } else { 2 }
    $data = if ($null -ne $staging -and (Test-Path -LiteralPath $staging)) { [pscustomobject]@{ incomplete_bundle = $staging } } else { $null }
    Write-BackupResult $code 'blocked' $_.Exception.Message $data
}
