[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$scripts = Join-Path $projectRoot 'knowledge-base-manager\scripts'
$shell = (Get-Command pwsh -ErrorAction Stop).Source
$temp = Join-Path ([IO.Path]::GetTempPath()) ('kb-backup-tests-' + [guid]::NewGuid().ToString('N'))
. (Join-Path $scripts 'kb-backup-common.ps1')

function Assert-True([bool]$Condition, [string]$Message) { if (-not $Condition) { throw "Assertion failed: $Message" } }
function Write-Utf8([string]$Path, [string]$Text) { New-Item -ItemType Directory -Path (Split-Path -Parent $Path) -Force | Out-Null; [IO.File]::WriteAllText($Path, $Text, [Text.UTF8Encoding]::new($false)) }
function Invoke-Json([string]$Script, [string[]]$Arguments) { $out = & $shell -NoProfile -File $Script @Arguments; [pscustomobject]@{ ExitCode=$LASTEXITCODE; Data=(($out -join "`n") | ConvertFrom-Json); Raw=$out } }
function Get-BackupPlan([string]$Root, [string]$Destination) { return Invoke-Json $backup @('-Root',$Root,'-Destination',$Destination) }
function Invoke-ConfirmedBackup([string]$Root, [string]$Destination) {
    $planResult = Get-BackupPlan $Root $Destination
    Assert-True ($planResult.ExitCode -eq 0 -and $planResult.Data.status -eq 'plan') 'confirmed backup requires a valid read-only plan'
    return Invoke-Json $backup @('-Root',$Root,'-Destination',$Destination,'-Execute','-ConfirmedPlanDigest',$planResult.Data.data.plan.plan_digest)
}
function Update-Checksums([string]$Bundle) {
    $checksumPath = Join-Path $Bundle 'CHECKSUMS.sha256'
    $records = Get-ChildItem -LiteralPath $Bundle -Recurse -File | Where-Object { -not $_.FullName.Equals($checksumPath, [StringComparison]::OrdinalIgnoreCase) } | ForEach-Object {
        "$(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256 | Select-Object -ExpandProperty Hash)  $([IO.Path]::GetRelativePath($Bundle,$_.FullName).Replace('\','/'))"
    }
    [IO.File]::WriteAllLines((Join-Path $Bundle 'CHECKSUMS.sha256'), @($records), [Text.UTF8Encoding]::new($false))
}
function New-Fixture([string]$Name) {
    $root = Join-Path $temp "$Name\知识库 空格"
    $project = Join-Path $temp "$Name\项目 空格"
    Write-Utf8 (Join-Path $root 'kb.yaml') "schema_version: 1`ncontent_dir: content`nentrypoint: content/index.md`nunknown_field: preserve-me`n"
    Write-Utf8 (Join-Path $root 'content\index.md') "# KB`n`n- [来源](knowledge/来源 note.md)`n"
    Write-Utf8 (Join-Path $project '资料\证据 文件.txt') 'evidence unicode'
    $source = (Join-Path $project '资料\证据 文件.txt').Replace('\', '/')
    Write-Utf8 (Join-Path $root 'content\knowledge\来源 note.md') @"
---
id: kb-20260830-a1b2
type: source
status: draft
created: 2026-08-30
updated: 2026-08-30
---
# 来源 note

- Project: `Demo Project`; project-id: `demo-project`; project-relative source: `资料/证据 文件.txt`; provenance prose keeps $source unchanged; external local path (outside knowledge base; machine-specific) <!-- kb-external-local -->: [证据]($source); verified: 2026-08-30; version-state: unversioned.
- Project: `Demo Project`; project-id: `demo-project`; project-relative source: `资料/证据 文件.txt`; external local path (outside knowledge base; machine-specific) <!-- kb-external-local -->: [重复一]($source) and [重复二]($source); verified: 2026-08-30; version-state: unversioned.
"@
    return [pscustomobject]@{ Root=$root; Project=$project; Source=$source }
}

try {
    Assert-True ($PSVersionTable.PSVersion.Major -ge 7) 'backup tests must run under PowerShell 7+'
    foreach ($scriptFile in Get-ChildItem -LiteralPath $scripts -Filter '*.ps1') {
        Assert-True ((Get-Content -LiteralPath $scriptFile.FullName -TotalCount 1 -Encoding UTF8) -eq '#Requires -Version 7.0') "bundled script requires PowerShell 7+: $($scriptFile.Name)"
    }
    Assert-True ((Get-KbFullPath 'C:\') -eq 'C:\') 'drive root canonicalization must retain its separator'
    Assert-True (Test-KbPathInside 'C:\Windows' 'C:\') 'drive-root containment must work without a doubled separator'
    $fixture = New-Fixture 'main'
    $before = [IO.File]::ReadAllBytes((Join-Path $fixture.Root 'content\knowledge\来源 note.md'))
    $parent = Join-Path $temp 'backup parent'
    $backup = Join-Path $scripts 'kb-backup.ps1'
    $verify = Join-Path $scripts 'kb-verify-backup.ps1'
    $restore = Join-Path $scripts 'kb-restore.ps1'
    $audit = Join-Path $scripts 'kb-audit.ps1'
    $backupSource = Get-Content -LiteralPath $backup -Raw -Encoding UTF8
    Assert-True (([regex]::Matches($backupSource, '(?m)^(?!\s*function\b).*Assert-ConfirmedPlanCurrent\s+-ExpectedPlan')).Count -eq 2) 'backup main flow must use only fixed pre-write and pre-publish full-plan gates'
    Assert-True ($backupSource -match '\[IO\.Directory\]::Move\(' -and $backupSource -notmatch '(?m)^\s*Move-Item\s+-LiteralPath\s+\$bundle') 'backup publication must use fail-if-exists Directory.Move'
    $restoreSource = Get-Content -LiteralPath $restore -Raw -Encoding UTF8
    Assert-True ($restoreSource -match '\.restore-incomplete-' -and $restoreSource -match '\[IO\.File\]::Copy\(' -and $restoreSource -match '\[IO\.Directory\]::Move\(') 'restore must stage exact files and publish with Directory.Move'
    $plan = Get-BackupPlan $fixture.Root $parent
    Assert-True ($plan.ExitCode -eq 0 -and $plan.Data.status -eq 'plan') 'default backup must be a successful plan'
    $planAgain = Get-BackupPlan $fixture.Root $parent
    Assert-True ($plan.Data.data.plan.plan_digest -eq $planAgain.Data.data.plan.plan_digest) 'identical plans must have the same deterministic digest'
    $planFiles = @($plan.Data.data.plan.files)
    Assert-True ($planFiles.Count -eq 4) 'plan must list kb.yaml, every content file, and one deduplicated external source'
    Assert-True ((@($planFiles | ForEach-Object { "$($_.kind)|$($_.portable_path)" }) -join '|') -eq 'kb_manifest|kb.yaml|content|content/index.md|content|content/knowledge/来源 note.md|external|external/projects/demo-project/资料/证据 文件.txt') 'plan file ordering must be stable and portable-path sorted within kind'
    foreach ($record in $planFiles) {
        Assert-True (-not [string]::IsNullOrWhiteSpace($record.source_path) -and $record.size_bytes -ge 0 -and -not [string]::IsNullOrWhiteSpace($record.mtime_utc) -and $record.sha256 -match '^[0-9a-f]{64}$') 'every plan record must expose canonical path, size, mtime, and SHA-256'
    }
    $externalPlanRecord = @($planFiles | Where-Object kind -eq 'external')
    Assert-True ($externalPlanRecord.Count -eq 1 -and $externalPlanRecord[0].project_id -eq 'demo-project' -and $externalPlanRecord[0].project_relative_source -eq '资料/证据 文件.txt') 'external plan record must preserve project mapping'
    Assert-True (-not (Test-Path -LiteralPath $parent)) 'read-only plan must not create its destination'
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $parent 'portable-kb'))) 'plan must not create bundle'
    $missingConfirmation = Invoke-Json $backup @('-Root',$fixture.Root,'-Destination',(Join-Path $temp 'missing confirmation'),'-Execute')
    Assert-True ($missingConfirmation.ExitCode -eq 2 -and $missingConfirmation.Data.status -eq 'confirmation_required') 'Execute without digest must require confirmation'
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $temp 'missing confirmation'))) 'missing confirmation must not create destination or staging'
    $wrongConfirmation = Invoke-Json $backup @('-Root',$fixture.Root,'-Destination',(Join-Path $temp 'wrong confirmation'),'-Execute','-ConfirmedPlanDigest',('0' * 64))
    Assert-True ($wrongConfirmation.ExitCode -eq 2 -and $wrongConfirmation.Data.status -eq 'reconfirm_required' -and $wrongConfirmation.Data.data.plan.plan_digest -match '^[0-9a-f]{64}$' -and @($wrongConfirmation.Data.data.change_summary).Count -gt 0) 'wrong digest must return a newly listed plan and reconfirmation'
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $temp 'wrong confirmation'))) 'wrong digest must not create destination or staging'
    $created = Invoke-ConfirmedBackup $fixture.Root $parent
    Assert-True ($created.ExitCode -eq 0) 'ReferenceComplete execute must create backup'
    $after = [IO.File]::ReadAllBytes((Join-Path $fixture.Root 'content\knowledge\来源 note.md'))
    $sameBytes = $before.Length -eq $after.Length
    if ($sameBytes) { for ($i = 0; $i -lt $before.Length; $i++) { if ($before[$i] -ne $after[$i]) { $sameBytes = $false; break } } }
    Assert-True $sameBytes 'live KB must remain byte-identical'
    $bundle = Join-Path $parent 'portable-kb'
    $copy = Join-Path $bundle 'content\knowledge\来源 note.md'
    $copyText = Get-Content -LiteralPath $copy -Raw -Encoding UTF8
    Assert-True ($copyText -match 'kb-portable-source' -and $copyText -notmatch 'kb-external-local') 'only copied marked links must become portable'
    Assert-True ($copyText -match [regex]::Escape($fixture.Source)) 'same-line provenance prose must not be rewritten'
    Assert-True (@(Get-ChildItem -LiteralPath (Join-Path $bundle 'external') -Recurse -File).Count -eq 1) 'duplicate references must deduplicate copied external target'
    Assert-True ((Get-Content -LiteralPath (Join-Path $bundle 'kb.yaml') -Raw) -match 'unknown_field: preserve-me') 'unknown kb.yaml fields must survive backup'
    $verified = Invoke-Json $verify @('-Bundle',$bundle)
    Assert-True ($verified.ExitCode -eq 0) 'created backup must verify'
    $portableAudit = Invoke-Json $audit @('-Root',$bundle,'-Format','Json')
    Assert-True ($portableAudit.ExitCode -eq 0) 'portable marker must audit within external_dir'
    Move-Item -LiteralPath $fixture.Project -Destination (Join-Path $temp 'main\isolated-original-project')
    $restorePlan = Invoke-Json $restore @('-Bundle',$bundle,'-Destination',(Join-Path $temp 'other-drive-neutral\restored'))
    Assert-True ($restorePlan.ExitCode -eq 0 -and $restorePlan.Data.status -eq 'plan') 'restore default must be plan-only'
    $restoreDone = Invoke-Json $restore @('-Bundle',$bundle,'-Destination',(Join-Path $temp 'other-drive-neutral\restored'),'-Execute')
    Assert-True ($restoreDone.ExitCode -eq 0) 'portable restore must succeed independent of original root'
    $restoredAudit = Invoke-Json $audit @('-Root',(Join-Path $temp 'other-drive-neutral\restored'),'-Format','Json')
    Assert-True ($restoredAudit.ExitCode -eq 0) 'restored KB must audit'
    $conflict = Invoke-Json $restore @('-Bundle',$bundle,'-Destination',(Join-Path $temp 'other-drive-neutral\restored'),'-Execute')
    Assert-True ($conflict.ExitCode -eq 2) 'restore must refuse nonempty conflict destination'
    Add-Content -LiteralPath (Join-Path $bundle 'external\projects\demo-project\资料\证据 文件.txt') -Value 'tamper'
    $tampered = Invoke-Json $verify @('-Bundle',$bundle)
    Assert-True ($tampered.ExitCode -eq 2) 'checksum tampering must fail verification'

    $missing = New-Fixture 'missing'
    Remove-Item -LiteralPath $missing.Source -Force
    $missingResult = Invoke-Json $backup @('-Root',$missing.Root,'-Destination',(Join-Path $temp 'missing backup'))
    Assert-True ($missingResult.ExitCode -eq 2) 'missing registered source must block complete backup'

    $legacy = New-Fixture 'legacy'
    Add-Content -LiteralPath (Join-Path $legacy.Root 'content\knowledge\来源 note.md') -Value "`n[legacy]($($legacy.Source))"
    $legacyResult = Invoke-Json $backup @('-Root',$legacy.Root,'-Destination',(Join-Path $temp 'legacy backup'))
    Assert-True ($legacyResult.ExitCode -eq 2) 'unmarked legacy absolute path must block backup'
    $ignored = Invoke-Json $backup @('-Root',$legacy.Root,'-Destination',(Join-Path $temp 'legacy ignored'),'-IgnoreLegacyPath',($legacy.Source + '|historical duplicate locator'))
    Assert-True ($ignored.ExitCode -eq 0) 'legacy path with explicit reason may be ignored'

    $traversal = New-Fixture 'traversal'
    (Get-Content -LiteralPath (Join-Path $traversal.Root 'content\knowledge\来源 note.md') -Raw).Replace('资料/证据 文件.txt','../escape.txt') | Set-Content -LiteralPath (Join-Path $traversal.Root 'content\knowledge\来源 note.md') -Encoding UTF8 -NoNewline
    $traversalResult = Invoke-Json $backup @('-Root',$traversal.Root,'-Destination',(Join-Path $temp 'traversal backup'))
    Assert-True ($traversalResult.ExitCode -eq 2) 'project-relative traversal must block backup'
    $inside = Invoke-Json $backup @('-Root',$fixture.Root,'-Destination',(Join-Path $fixture.Root 'bad destination'))
    Assert-True ($inside.ExitCode -eq 2) 'destination inside source root must block'
    $snapshot = Invoke-Json $backup @('-Root',$fixture.Root,'-Destination',(Join-Path $temp 'snapshot'),'-Mode','ProjectSnapshot')
    Assert-True ($snapshot.ExitCode -eq 2) 'unsupported snapshot mode must clearly block'
    $relink = Invoke-Json $restore @('-Bundle',$bundle,'-Destination',(Join-Path $temp 'relink'),'-Mode','Relink')
    Assert-True ($relink.ExitCode -eq 2) 'unsupported relink mode must clearly block'

    $zero = Join-Path $temp 'zero external\kb'
    Write-Utf8 (Join-Path $zero 'kb.yaml') "schema_version: 1`ncontent_dir: content`nentrypoint: content/index.md`n"
    Write-Utf8 (Join-Path $zero 'content\index.md') '# Zero external'
    $zeroParent = Join-Path $temp 'zero external backup'
    $zeroCreate = Invoke-ConfirmedBackup $zero $zeroParent
    Assert-True ($zeroCreate.ExitCode -eq 0) ("a KB with zero external sources must back up: $($zeroCreate.Raw -join ' ')")
    $zeroBundle = Join-Path $zeroParent 'portable-kb'
    Assert-True (Test-Path -LiteralPath (Join-Path $zeroBundle 'external\projects') -PathType Container) 'zero-source bundle must still contain external/projects'
    Assert-True ((Invoke-Json $verify @('-Bundle',$zeroBundle)).ExitCode -eq 0) 'zero-source bundle must verify'

    $existingEmpty = Join-Path $temp 'existing empty restore'
    New-Item -ItemType Directory -Path $existingEmpty -Force | Out-Null
    Assert-True ((Invoke-Json $restore @('-Bundle',$zeroBundle,'-Destination',$existingEmpty)).ExitCode -eq 2) 'restore must reject even an empty existing destination so publication can stay atomic'

    $redirectTarget = Join-Path $temp 'redirect target'
    $redirectParent = Join-Path $temp 'redirect parent'
    New-Item -ItemType Directory -Path $redirectTarget -Force | Out-Null
    New-Item -ItemType Junction -Path $redirectParent -Target $redirectTarget | Out-Null
    $redirectBackup = Invoke-Json $backup @('-Root',$zero,'-Destination',(Join-Path $redirectParent 'backup'))
    Assert-True ($redirectBackup.ExitCode -eq 2 -and (($redirectBackup.Raw -join ' ') -match 'junction|symbolic link')) 'backup destination ancestors must reject junctions'
    $redirectRestore = Invoke-Json $restore @('-Bundle',$zeroBundle,'-Destination',(Join-Path $redirectParent 'restored'))
    Assert-True ($redirectRestore.ExitCode -eq 2 -and (($redirectRestore.Raw -join ' ') -match 'junction|symbolic link')) 'restore destination ancestors must reject junctions'
    Remove-Item -LiteralPath $redirectParent -Force

    $junctionSourceRoot = Join-Path $temp 'junction source kb'
    $junctionContentTarget = Join-Path $temp 'junction source content'
    Write-Utf8 (Join-Path $junctionSourceRoot 'kb.yaml') "schema_version: 1`ncontent_dir: content`nentrypoint: content/index.md`n"
    Write-Utf8 (Join-Path $junctionContentTarget 'index.md') '# Junction source'
    $junctionContentPath = Join-Path $junctionSourceRoot 'content'
    New-Item -ItemType Junction -Path $junctionContentPath -Target $junctionContentTarget | Out-Null
    $junctionSourceResult = Invoke-Json $backup @('-Root',$junctionSourceRoot,'-Destination',(Join-Path $temp 'junction source backup'))
    Assert-True ($junctionSourceResult.ExitCode -eq 2 -and (($junctionSourceResult.Raw -join ' ') -match 'junction|symbolic link')) 'backup must reject a junction-backed content tree'
    Remove-Item -LiteralPath $junctionContentPath -Force

    $bundleRedirectTarget = Join-Path $temp 'bundle redirect target'
    Write-Utf8 (Join-Path $bundleRedirectTarget 'hidden.txt') 'outside bundle'
    $bundleRedirect = Join-Path $zeroBundle 'redirected'
    New-Item -ItemType Junction -Path $bundleRedirect -Target $bundleRedirectTarget | Out-Null
    $redirectVerify = Invoke-Json $verify @('-Bundle',$zeroBundle)
    Assert-True ($redirectVerify.ExitCode -eq 3 -and (($redirectVerify.Raw -join ' ') -match 'junction|symbolic link')) 'verification must reject every redirecting reparse point in a bundle'
    Remove-Item -LiteralPath $bundleRedirect -Force

    $missingId = New-Fixture 'missing-id'
    (Get-Content -LiteralPath (Join-Path $missingId.Root 'content\knowledge\来源 note.md') -Raw) -replace 'project-id:[^;；]+;\s*','' | Set-Content -LiteralPath (Join-Path $missingId.Root 'content\knowledge\来源 note.md') -Encoding UTF8 -NoNewline
    $missingIdResult = Invoke-Json $backup @('-Root',$missingId.Root,'-Destination',(Join-Path $temp 'missing-id backup'))
    Assert-True ($missingIdResult.ExitCode -eq 2) 'missing project-id must block backup'
    $invalidId = New-Fixture 'invalid-id'
    (Get-Content -LiteralPath (Join-Path $invalidId.Root 'content\knowledge\来源 note.md') -Raw).Replace('demo-project','Invalid Project') | Set-Content -LiteralPath (Join-Path $invalidId.Root 'content\knowledge\来源 note.md') -Encoding UTF8 -NoNewline
    Assert-True ((Invoke-Json $backup @('-Root',$invalidId.Root,'-Destination',(Join-Path $temp 'invalid-id backup'))).ExitCode -eq 2) 'invalid project-id must block backup'
    $codeLegacy = New-Fixture 'code-legacy'
    Add-Content -LiteralPath (Join-Path $codeLegacy.Root 'content\knowledge\来源 note.md') -Value ("`nLegacy path: ``$($codeLegacy.Source)``")
    Assert-True ((Invoke-Json $backup @('-Root',$codeLegacy.Root,'-Destination',(Join-Path $temp 'code legacy backup'))).ExitCode -eq 2) 'absolute code-span path must block backup'

    $externalDrift = New-Fixture 'external-drift'
    $externalDriftParent = Join-Path $temp 'external drift backup'
    $externalDriftPlan = Get-BackupPlan $externalDrift.Root $externalDriftParent
    $externalBefore = [IO.File]::ReadAllBytes($externalDrift.Source)
    [IO.File]::WriteAllBytes($externalDrift.Source, @(for ($i = 0; $i -lt $externalBefore.Length; $i++) { if ($i -eq 0) { [byte]($externalBefore[$i] -bxor 1) } else { $externalBefore[$i] } }))
    $externalDriftResult = Invoke-Json $backup @('-Root',$externalDrift.Root,'-Destination',$externalDriftParent,'-Execute','-ConfirmedPlanDigest',$externalDriftPlan.Data.data.plan.plan_digest)
    Assert-True ($externalDriftResult.ExitCode -eq 2 -and $externalDriftResult.Data.status -eq 'reconfirm_required') 'same-size external content mutation must be detected by SHA-256'
    Assert-True (-not (Test-Path -LiteralPath $externalDriftParent)) 'pre-write external drift must not create destination or staging'

    $mtimeDrift = New-Fixture 'mtime-drift'
    $mtimeDriftParent = Join-Path $temp 'mtime drift backup'
    $mtimeDriftPlan = Get-BackupPlan $mtimeDrift.Root $mtimeDriftParent
    $mtimeFile = Get-Item -LiteralPath (Join-Path $mtimeDrift.Root 'content\index.md')
    $mtimeFile.LastWriteTimeUtc = $mtimeFile.LastWriteTimeUtc.AddSeconds(5)
    $mtimeDriftResult = Invoke-Json $backup @('-Root',$mtimeDrift.Root,'-Destination',$mtimeDriftParent,'-Execute','-ConfirmedPlanDigest',$mtimeDriftPlan.Data.data.plan.plan_digest)
    $mtimeActualPlan = Get-KbBackupPlan -KbRoot $mtimeDrift.Root -Destination $mtimeDriftParent -Mode 'ReferenceComplete'
    Assert-True ($mtimeDriftResult.ExitCode -eq 2 -and $mtimeDriftResult.Data.status -eq 'reconfirm_required' -and $mtimeActualPlan.plan_digest -ne $mtimeDriftPlan.Data.data.plan.plan_digest -and ((Get-KbPlanChangeSummary $mtimeDriftPlan.Data.data.plan $mtimeActualPlan) -join ' ') -match 'mtime_utc') 'mtime-only drift must require reconfirmation'

    $additionDrift = New-Fixture 'addition-drift'
    $additionParent = Join-Path $temp 'addition drift backup'
    $additionPlan = Get-BackupPlan $additionDrift.Root $additionParent
    Write-Utf8 (Join-Path $additionDrift.Root 'content\new.md') '# added'
    $additionResult = Invoke-Json $backup @('-Root',$additionDrift.Root,'-Destination',$additionParent,'-Execute','-ConfirmedPlanDigest',$additionPlan.Data.data.plan.plan_digest)
    $additionActualPlan = Get-KbBackupPlan -KbRoot $additionDrift.Root -Destination $additionParent -Mode 'ReferenceComplete'
    Assert-True ($additionResult.ExitCode -eq 2 -and $additionResult.Data.status -eq 'reconfirm_required' -and ((Get-KbPlanChangeSummary $additionPlan.Data.data.plan $additionActualPlan) -join ' ') -match 'source added') 'content additions must require reconfirmation'

    $renameDrift = New-Fixture 'rename-drift'
    $renameParent = Join-Path $temp 'rename drift backup'
    $renamePlan = Get-BackupPlan $renameDrift.Root $renameParent
    Move-Item -LiteralPath (Join-Path $renameDrift.Root 'content\index.md') -Destination (Join-Path $renameDrift.Root 'content\renamed.md')
    $renameResult = Invoke-Json $backup @('-Root',$renameDrift.Root,'-Destination',$renameParent,'-Execute','-ConfirmedPlanDigest',$renamePlan.Data.data.plan.plan_digest)
    Assert-True ($renameResult.ExitCode -eq 2 -and $renameResult.Data.status -eq 'reconfirm_required') 'content rename/removal must require reconfirmation'

    $mappingDrift = New-Fixture 'mapping-drift'
    $mappingParent = Join-Path $temp 'mapping drift backup'
    $mappingPlan = Get-BackupPlan $mappingDrift.Root $mappingParent
    (Get-Content -LiteralPath (Join-Path $mappingDrift.Root 'content\knowledge\来源 note.md') -Raw).Replace('version-state: unversioned','version-state: changed-state') | Set-Content -LiteralPath (Join-Path $mappingDrift.Root 'content\knowledge\来源 note.md') -Encoding UTF8 -NoNewline
    $mappingResult = Invoke-Json $backup @('-Root',$mappingDrift.Root,'-Destination',$mappingParent,'-Execute','-ConfirmedPlanDigest',$mappingPlan.Data.data.plan.plan_digest)
    $mappingActualPlan = Get-KbBackupPlan -KbRoot $mappingDrift.Root -Destination $mappingParent -Mode 'ReferenceComplete'
    Assert-True ($mappingResult.ExitCode -eq 2 -and $mappingResult.Data.status -eq 'reconfirm_required' -and ((Get-KbPlanChangeSummary $mappingPlan.Data.data.plan $mappingActualPlan) -join ' ') -match 'reference mapping') 'reference provenance changes must require reconfirmation'

    $manifestDrift = New-Fixture 'manifest-drift'
    $manifestParent = Join-Path $temp 'manifest drift backup'
    $manifestPlan = Get-BackupPlan $manifestDrift.Root $manifestParent
    (Get-Content -LiteralPath (Join-Path $manifestDrift.Root 'kb.yaml') -Raw).Replace('unknown_field: preserve-me','unknown_field: changed-after-plan') | Set-Content -LiteralPath (Join-Path $manifestDrift.Root 'kb.yaml') -Encoding UTF8 -NoNewline
    $manifestResult = Invoke-Json $backup @('-Root',$manifestDrift.Root,'-Destination',$manifestParent,'-Execute','-ConfirmedPlanDigest',$manifestPlan.Data.data.plan.plan_digest)
    $manifestActualPlan = Get-KbBackupPlan -KbRoot $manifestDrift.Root -Destination $manifestParent -Mode 'ReferenceComplete'
    Assert-True ($manifestResult.ExitCode -eq 2 -and $manifestResult.Data.status -eq 'reconfirm_required' -and ((Get-KbPlanChangeSummary $manifestPlan.Data.data.plan $manifestActualPlan) -join ' ') -match 'kb_manifest') 'kb.yaml changes must require reconfirmation'

    $recordComparison = New-Fixture 'record-comparison'
    $recordPlan = Get-KbBackupPlan -KbRoot $recordComparison.Root -Destination (Join-Path $temp 'record comparison backup') -Mode 'ReferenceComplete'
    $record = @($recordPlan.files | Where-Object kind -eq 'external')[0]
    Assert-True (Test-KbSnapshotRecord $record) 'copy-time snapshot comparison must accept an unchanged record'
    $recordItem = Get-Item -LiteralPath $record.source_path
    $recordItem.LastWriteTimeUtc = $recordItem.LastWriteTimeUtc.AddSeconds(7)
    Assert-True (-not (Test-KbSnapshotRecord $record)) 'copy-time snapshot comparison must reject metadata-only drift'

    $stageBad = Join-Path $temp 'stage-bad\kb'
    Write-Utf8 (Join-Path $stageBad 'kb.yaml') "schema_version: 1`ncontent_dir: content`nentrypoint: content/index.md`n"
    Write-Utf8 (Join-Path $stageBad 'content\index.md') "# Bad`n`n[missing](missing.md)"
    $stageParent = Join-Path $temp 'stage bad backup'
    $stageResult = Invoke-ConfirmedBackup $stageBad $stageParent
    Assert-True ($stageResult.ExitCode -eq 3 -and (($stageResult.Raw -join ' ') -match 'incomplete_bundle')) 'staging audit failure must report incomplete bundle'
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $stageParent 'portable-kb'))) 'staging failure must not publish portable-kb'

    $coverage = New-Fixture 'checksum-coverage'
    $coverageParent = Join-Path $temp 'checksum coverage backup'
    Assert-True ((Invoke-ConfirmedBackup $coverage.Root $coverageParent).ExitCode -eq 0) 'checksum coverage fixture must create'
    $coverageBundle = Join-Path $coverageParent 'portable-kb'
    Write-Utf8 (Join-Path $coverageBundle 'uncovered.txt') 'not checksummed'
    Assert-True ((Invoke-Json $verify @('-Bundle',$coverageBundle)).ExitCode -eq 2) 'uncovered bundle file must fail verification'

    $duplicate = New-Fixture 'checksum-duplicate'
    $duplicateParent = Join-Path $temp 'checksum duplicate backup'
    Assert-True ((Invoke-ConfirmedBackup $duplicate.Root $duplicateParent).ExitCode -eq 0) 'duplicate checksum fixture must create'
    $duplicateBundle = Join-Path $duplicateParent 'portable-kb'
    $firstChecksum = Get-Content -LiteralPath (Join-Path $duplicateBundle 'CHECKSUMS.sha256') -TotalCount 1
    Add-Content -LiteralPath (Join-Path $duplicateBundle 'CHECKSUMS.sha256') -Value $firstChecksum
    Assert-True ((Invoke-Json $verify @('-Bundle',$duplicateBundle)).ExitCode -eq 2) 'duplicate checksum record must fail verification'
    $ghost = New-Fixture 'checksum-ghost'
    $ghostParent = Join-Path $temp 'checksum ghost backup'
    Assert-True ((Invoke-ConfirmedBackup $ghost.Root $ghostParent).ExitCode -eq 0) 'ghost checksum fixture must create'
    $ghostBundle = Join-Path $ghostParent 'portable-kb'
    Add-Content -LiteralPath (Join-Path $ghostBundle 'CHECKSUMS.sha256') -Value (('0' * 64) + '  ghost.txt')
    Assert-True ((Invoke-Json $verify @('-Bundle',$ghostBundle)).ExitCode -eq 2) 'ghost checksum record must fail verification'
    $referenceMismatch = New-Fixture 'reference-mismatch'
    $referenceParent = Join-Path $temp 'reference mismatch backup'
    Assert-True ((Invoke-ConfirmedBackup $referenceMismatch.Root $referenceParent).ExitCode -eq 0) 'reference mismatch fixture must create'
    $referenceBundle = Join-Path $referenceParent 'portable-kb'
    $manifestJson = Get-Content -LiteralPath (Join-Path $referenceBundle 'backup-manifest.json') -Raw | ConvertFrom-Json
    $manifestJson.references[0].portable_path = 'external/projects/demo-project/missing.txt'
    $manifestJson | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $referenceBundle 'backup-manifest.json') -Encoding UTF8 -NoNewline
    Update-Checksums $referenceBundle
    Assert-True ((Invoke-Json $verify @('-Bundle',$referenceBundle)).ExitCode -eq 2) 'reference without matching external manifest file must fail verification'
    Write-Output 'kb-backup tests passed.'
    $global:LASTEXITCODE = 0
}
finally { if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Recurse -Force } }
