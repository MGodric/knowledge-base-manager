#Requires -Version 7.0
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'kb-path-safety.ps1')

function Get-KbFullPath {
    param([Parameter(Mandatory)][string]$Path)
    $full = [System.IO.Path]::GetFullPath($Path)
    $root = [System.IO.Path]::GetPathRoot($full)
    if ($full.Equals($root, [System.StringComparison]::OrdinalIgnoreCase)) { return $root }
    return $full.TrimEnd('\', '/')
}

function Test-KbPathInside {
    param([Parameter(Mandatory)][string]$Candidate, [Parameter(Mandatory)][string]$Root)
    $candidateFull = (Get-KbFullPath $Candidate)
    $rootFull = (Get-KbFullPath $Root)
    $separator = [System.IO.Path]::DirectorySeparatorChar
    $prefix = if ($rootFull.EndsWith([string]$separator)) { $rootFull } else { $rootFull + $separator }
    return $candidateFull.Equals($rootFull, [System.StringComparison]::OrdinalIgnoreCase) -or
        $candidateFull.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)
}

function Get-KbRelativePath {
    param([Parameter(Mandatory)][string]$Base, [Parameter(Mandatory)][string]$Path)
    return [System.IO.Path]::GetRelativePath((Get-KbFullPath $Base), (Get-KbFullPath $Path)).Replace('\', '/')
}

function Get-KbSha256 {
    param([Parameter(Mandatory)][string]$Path)
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Get-KbCanonicalExistingPath {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "BLOCKER: source file is missing: $Path" }
    $canonical = Get-KbFullPath (Resolve-Path -LiteralPath $Path).Path
    Assert-KbNoRedirectingReparsePoint -Path $canonical -Label 'source path' | Out-Null
    return $canonical
}

function New-KbSnapshotRecord {
    param(
        [Parameter(Mandatory)][string]$Kind,
        [Parameter(Mandatory)][string]$SourcePath,
        [Parameter(Mandatory)][string]$PortablePath,
        [string]$ProjectId,
        [string]$ProjectRelativeSource
    )
    $canonical = Get-KbCanonicalExistingPath $SourcePath
    $item = Get-Item -LiteralPath $canonical -ErrorAction Stop
    $record = [ordered]@{
        kind = $Kind
        source_path = $canonical
        portable_path = $PortablePath.Replace('\\', '/')
        size_bytes = [int64]$item.Length
        mtime_utc = $item.LastWriteTimeUtc.ToString('o')
        sha256 = Get-KbSha256 $canonical
    }
    if ($Kind -eq 'external') {
        $record.project_id = $ProjectId
        $record.project_relative_source = $ProjectRelativeSource.Replace('\\', '/')
    }
    return [pscustomobject]$record
}

function Get-KbDeterministicJson {
    param([Parameter(Mandatory)]$Value)
    return $Value | ConvertTo-Json -Depth 20 -Compress
}

function Get-KbOptionalProperty {
    param([Parameter(Mandatory)]$Object, [Parameter(Mandatory)][string]$Name)
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) { return $null }
    return $property.Value
}

function Get-KbPlanDigest {
    param([Parameter(Mandatory)]$PlanWithoutDigest)
    $json = Get-KbDeterministicJson $PlanWithoutDigest
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes($json)
    $hasher = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($hasher.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant() }
    finally { $hasher.Dispose() }
}

function Get-KbBackupPlan {
    param(
        [Parameter(Mandatory)][string]$KbRoot,
        [Parameter(Mandatory)][string]$Destination,
        [Parameter(Mandatory)][string]$Mode,
        [string[]]$IgnoreLegacyPath = @()
    )
    $manifest = Read-KbManifest $KbRoot
    $references = Get-KbBackupReferences -Manifest $manifest -KbRoot $KbRoot -IgnoreLegacyPath $IgnoreLegacyPath
    $destinationFull = Get-KbFullPath $Destination
    Assert-KbNoRedirectingReparsePoint -Path $destinationFull -Label 'backup destination' | Out-Null
    $bundle = Join-Path $destinationFull 'portable-kb'
    $sourceRoots = @($KbRoot) + @($references.References | ForEach-Object ProjectRoot | Select-Object -Unique)
    foreach ($sourceRoot in $sourceRoots) {
        if (Test-KbPathInside $destinationFull $sourceRoot) { throw "BLOCKER: destination must not be inside a source root: $destinationFull" }
    }
    if (Test-KbPathInside $bundle $KbRoot) { throw 'BLOCKER: bundle output must not be inside the knowledge-base root' }

    $records = [Collections.Generic.List[object]]::new()
    $records.Add((New-KbSnapshotRecord -Kind 'kb_manifest' -SourcePath $manifest.ManifestPath -PortablePath 'kb.yaml'))
    $content = @(Get-KbSafeTreeFiles -Root $manifest.Content -Label 'knowledge-base content' | ForEach-Object {
        $relative = Get-KbRelativePath $manifest.Content $_.FullName
        New-KbSnapshotRecord -Kind 'content' -SourcePath $_.FullName -PortablePath ("content/$relative")
    } | Sort-Object portable_path, source_path)
    foreach ($record in $content) { $records.Add($record) }
    $external = @($references.Targets.GetEnumerator() | ForEach-Object {
        $reference = $_.Value
        New-KbSnapshotRecord -Kind 'external' -SourcePath $reference.Source -PortablePath $_.Key -ProjectId $reference.ProjectId -ProjectRelativeSource $reference.Relative
    } | Sort-Object portable_path, source_path)
    foreach ($record in $external) { $records.Add($record) }
    $referenceMappings = @($references.References | ForEach-Object {
        [pscustomobject][ordered]@{
            source_path = Get-KbCanonicalExistingPath $_.Source
            portable_path = ("external/projects/$($_.ProjectId)/$($_.Relative)").Replace('\\', '/')
            project = $_.Project
            project_id = $_.ProjectId
            project_relative_source = $_.Relative
            referrer = $_.Referrer
            line = [int]$_.Line
            verified = $_.Verified
            revision = $_.Revision
            version_state = $_.VersionState
        }
    } | Sort-Object portable_path, source_path, referrer, line)
    $ignored = @($references.IgnoredLegacy.GetEnumerator() | ForEach-Object {
        [pscustomobject][ordered]@{ path = Get-KbFullPath $_.Key; reason = $_.Value }
    } | Sort-Object path)
    $planWithoutDigest = [pscustomobject][ordered]@{
        root = $KbRoot
        destination = $destinationFull
        bundle = $bundle
        mode = $Mode
        content_dir = $manifest.Content
        ignored_legacy_paths = $ignored
        files = @($records)
        reference_mappings = $referenceMappings
        totals = [pscustomobject][ordered]@{
            kb_manifest_files = 1
            content_files = @($content).Count
            external_files = @($external).Count
            external_references = @($referenceMappings).Count
            all_source_files = @($records).Count
        }
    }
    $plan = [ordered]@{}
    foreach ($property in $planWithoutDigest.PSObject.Properties) { $plan[$property.Name] = $property.Value }
    $plan.plan_digest = Get-KbPlanDigest $planWithoutDigest
    return [pscustomobject]$plan
}

function Get-KbPlanChangeSummary {
    param([Parameter(Mandatory)]$Expected, [Parameter(Mandatory)]$Actual)
    $changes = [Collections.Generic.List[string]]::new()
    foreach ($setting in @('root', 'destination', 'bundle', 'mode', 'content_dir')) {
        if ([string]$Expected.$setting -cne [string]$Actual.$setting) { $changes.Add("plan setting changed: $setting") }
    }
    $expectedFiles = @{}
    foreach ($record in @($Expected.files)) { $expectedFiles["$($record.kind)|$($record.portable_path)"] = $record }
    $actualFiles = @{}
    foreach ($record in @($Actual.files)) { $actualFiles["$($record.kind)|$($record.portable_path)"] = $record }
    $fileKeys = @((@($expectedFiles.Keys) + @($actualFiles.Keys)) | Sort-Object -Unique)
    foreach ($key in $fileKeys) {
        if (-not $expectedFiles.ContainsKey($key)) { $changes.Add("source added: $key"); continue }
        if (-not $actualFiles.ContainsKey($key)) { $changes.Add("source removed: $key"); continue }
        foreach ($field in @('source_path', 'size_bytes', 'mtime_utc', 'sha256', 'project_id', 'project_relative_source')) {
            if ([string](Get-KbOptionalProperty $expectedFiles[$key] $field) -cne [string](Get-KbOptionalProperty $actualFiles[$key] $field)) { $changes.Add("source changed ($field): $key") }
        }
    }
    $expectedReferences = Get-KbDeterministicJson @($Expected.reference_mappings)
    $actualReferences = Get-KbDeterministicJson @($Actual.reference_mappings)
    if ($expectedReferences -cne $actualReferences) { $changes.Add('registered reference mapping or provenance changed') }
    $expectedIgnored = Get-KbDeterministicJson @($Expected.ignored_legacy_paths)
    $actualIgnored = Get-KbDeterministicJson @($Actual.ignored_legacy_paths)
    if ($expectedIgnored -cne $actualIgnored) { $changes.Add('ignored legacy path configuration changed') }
    if ($changes.Count -eq 0) { $changes.Add('confirmed plan digest differs from the current plan') }
    return @($changes | Select-Object -Unique)
}

function Test-KbSnapshotRecord {
    param([Parameter(Mandatory)]$Record)
    try { $actual = New-KbSnapshotRecord -Kind $Record.kind -SourcePath $Record.source_path -PortablePath $Record.portable_path -ProjectId (Get-KbOptionalProperty $Record 'project_id') -ProjectRelativeSource (Get-KbOptionalProperty $Record 'project_relative_source') }
    catch { return $false }
    foreach ($field in @('kind', 'source_path', 'portable_path', 'size_bytes', 'mtime_utc', 'sha256', 'project_id', 'project_relative_source')) {
        if ([string](Get-KbOptionalProperty $Record $field) -cne [string](Get-KbOptionalProperty $actual $field)) { return $false }
    }
    return $true
}

function Read-KbManifest {
    param([Parameter(Mandatory)][string]$Root)
    $path = Join-Path $Root 'kb.yaml'
    Assert-KbNoRedirectingReparsePoint -Path $Root -Label 'knowledge-base root' | Out-Null
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "BLOCKER: kb.yaml is missing: $path" }
    Assert-KbNoRedirectingReparsePoint -Path $path -Label 'kb.yaml' | Out-Null
    $values = @{}
    foreach ($line in Get-Content -LiteralPath $path -Encoding UTF8) {
        if ($line -match '^\s*(?<key>[A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(?<value>.*?)\s*$') {
            $value = $Matches.value.Trim().Trim('"').Trim("'")
            $values[$Matches.key] = $value
        }
    }
    foreach ($key in @('schema_version', 'content_dir', 'entrypoint')) {
        if (-not $values.ContainsKey($key) -or [string]::IsNullOrWhiteSpace($values[$key])) { throw "BLOCKER: kb.yaml requires $key" }
    }
    if ($values.schema_version -ne '1') { throw "BLOCKER: only schema_version 1 is supported" }
    $content = Get-KbFullPath (Join-Path $Root $values.content_dir)
    if ([IO.Path]::IsPathRooted($values.content_dir) -or -not (Test-KbPathInside $content $Root)) { throw 'BLOCKER: content_dir escapes knowledge-base root' }
    if (-not (Test-Path -LiteralPath $content -PathType Container)) { throw "BLOCKER: content_dir is missing: $content" }
    Assert-KbNoRedirectingReparsePoint -Path $content -Label 'content_dir' | Out-Null
    return [pscustomobject]@{ Values = $values; Content = $content; ManifestPath = $path }
}

function Get-KbLinksInLine {
    param([string]$Line)
    $links = [Collections.Generic.List[object]]::new()
    foreach ($match in [regex]::Matches($Line, '!?(?<label>\[[^\]]*\])\((?<inside>[^)]+)\)')) {
        $inside = $match.Groups['inside'].Value.Trim()
        $target = $inside
        if ($inside.StartsWith('<')) { $target = $inside.Substring(1, $inside.IndexOf('>') - 1) }
        elseif ($inside -match '^(?<url>\S+)(?:\s+["''].*)?$') { $target = $Matches.url }
        $links.Add([pscustomobject]@{ Target = $target; Match = $match })
    }
    return $links
}

function Get-KbField {
    param([string]$Line, [string]$Name)
    $m = [regex]::Match($Line, "(?i)$([regex]::Escape($Name))\s*[:：]\s*(?<value>[^;；,，]+)")
    if (-not $m.Success) { return $null }
    return $m.Groups['value'].Value.Trim().Trim('`')
}

function Test-KbSafeRelativeSourcePath {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path) -or [IO.Path]::IsPathRooted($Path)) { return $false }
    $parts = $Path.Replace('\', '/').Split('/')
    return -not (@($parts | Where-Object { $_ -eq '' -or $_ -eq '.' -or $_ -eq '..' }).Count -gt 0)
}

function Get-KbIgnoreMap {
    param([string[]]$IgnoreLegacyPath)
    $map = @{}
    foreach ($item in @($IgnoreLegacyPath)) {
        $split = $item -split '\|', 2
        if ($split.Count -ne 2 -or [string]::IsNullOrWhiteSpace($split[1])) { throw "BLOCKER: IgnoreLegacyPath must be 'absolute-path|reason': $item" }
        $map[(Get-KbFullPath $split[0])] = $split[1].Trim()
    }
    return $map
}

function Get-KbBackupReferences {
    param([Parameter(Mandatory)]$Manifest, [Parameter(Mandatory)][string]$KbRoot, [string[]]$IgnoreLegacyPath)
    $ignoreMap = Get-KbIgnoreMap $IgnoreLegacyPath
    $refs = [Collections.Generic.List[object]]::new()
    $blockers = [Collections.Generic.List[string]]::new()
    foreach ($file in @(Get-KbSafeTreeFiles -Root $Manifest.Content -Label 'knowledge-base content' | Where-Object Extension -ieq '.md')) {
        $lineNo = 0
        foreach ($line in Get-Content -LiteralPath $file.FullName -Encoding UTF8) {
            $lineNo++
            $registeredOnLine = @{}
            foreach ($candidateLink in Get-KbLinksInLine $line) {
                $candidateTarget = [string]$candidateLink.Target
                if (($candidateTarget -match '^[A-Za-z]:[\\/]' -or $candidateTarget.StartsWith('\\')) -and $line -match '(?i)<!--\s*kb-external-local\s*-->') {
                    $registeredOnLine[(Get-KbFullPath $candidateTarget)] = $true
                }
            }
            foreach ($link in Get-KbLinksInLine $line) {
                $target = [string]$link.Target
                if ($target -notmatch '^[A-Za-z]:[\\/]' -and -not $target.StartsWith('\\')) { continue }
                $source = Get-KbFullPath $target
                $marked = $line -match '(?i)<!--\s*kb-external-local\s*-->'
                if (-not $marked) {
                    if (-not $registeredOnLine.ContainsKey($source) -and -not $ignoreMap.ContainsKey($source)) { $blockers.Add("legacy absolute local link at $(Get-KbRelativePath $Manifest.Content $file.FullName):$lineNo -> $target") }
                    continue
                }
                $project = Get-KbField $line 'project'
                if ([string]::IsNullOrWhiteSpace($project)) { $project = Get-KbField $line '项目' }
                $projectId = Get-KbField $line 'project-id'
                $relative = Get-KbField $line 'project-relative source'
                if ([string]::IsNullOrWhiteSpace($relative)) { $relative = Get-KbField $line '项目相对来源' }
                $verified = Get-KbField $line 'verified'
                $revision = Get-KbField $line 'revision'
                $versionState = Get-KbField $line 'version-state'
                if ([string]::IsNullOrWhiteSpace($project) -or $projectId -notmatch '^[a-z0-9][a-z0-9._-]{0,63}$' -or -not (Test-KbSafeRelativeSourcePath $relative) -or
                    $verified -notmatch '^\d{4}-\d{2}-\d{2}$' -or ([string]::IsNullOrWhiteSpace($revision) -and [string]::IsNullOrWhiteSpace($versionState))) {
                    $blockers.Add("incomplete external-source metadata at $(Get-KbRelativePath $Manifest.Content $file.FullName):$lineNo")
                    continue
                }
                if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { $blockers.Add("external source is missing: $source"); continue }
                try { Assert-KbNoRedirectingReparsePoint -Path $source -Label 'external source' | Out-Null }
                catch { $blockers.Add($_.Exception.Message); continue }
                $suffix = $relative.Replace('/', '\')
                if (-not $source.EndsWith('\' + $suffix, [StringComparison]::OrdinalIgnoreCase)) { $blockers.Add("source-path/root inconsistency: $source does not end in project-relative source $relative"); continue }
                $projectRoot = $source.Substring(0, $source.Length - $suffix.Length).TrimEnd('\', '/')
                if ([string]::IsNullOrWhiteSpace($projectRoot) -or -not (Test-Path -LiteralPath $projectRoot -PathType Container) -or (Test-KbPathInside $projectRoot $KbRoot)) { $blockers.Add("invalid external project root for $source"); continue }
                try { Assert-KbNoRedirectingReparsePoint -Path $projectRoot -Label 'external project root' | Out-Null }
                catch { $blockers.Add($_.Exception.Message); continue }
                $refs.Add([pscustomobject]@{ Source = $source; OriginalTarget = $target; ProjectRoot = $projectRoot; Project = $project; ProjectId = $projectId; Relative = $relative.Replace('\', '/'); Verified = $verified; Revision = $revision; VersionState = $versionState; Referrer = Get-KbRelativePath $Manifest.Content $file.FullName; Line = $lineNo; OriginalLine = $line; LinkStart = $link.Match.Index; LinkLength = $link.Match.Length })
            }
            foreach ($span in [regex]::Matches($line, '`(?<path>(?:[A-Za-z]:[\\/]|\\\\)[^`]+)`')) {
                $source = Get-KbFullPath $span.Groups['path'].Value.Trim()
                if (-not $registeredOnLine.ContainsKey($source) -and -not $ignoreMap.ContainsKey($source)) {
                    $blockers.Add("legacy absolute local path in code span at $(Get-KbRelativePath $Manifest.Content $file.FullName):$lineNo -> $($span.Groups['path'].Value)")
                }
            }
        }
    }
    if ($blockers.Count -gt 0) { throw ('BLOCKER: ' + ($blockers -join '; ')) }
    $targets = @{}
    $sources = @{}
    foreach ($ref in $refs) {
        $target = "external/projects/$($ref.ProjectId)/$($ref.Relative)"
        if ($targets.ContainsKey($target) -and -not $targets[$target].Source.Equals($ref.Source, [StringComparison]::OrdinalIgnoreCase)) { throw "BLOCKER: two canonical sources map to one portable target: $target" }
        $canonicalSource = Get-KbCanonicalExistingPath $ref.Source
        if ($sources.ContainsKey($canonicalSource) -and $sources[$canonicalSource] -cne $target) { throw "BLOCKER: one canonical external source maps to multiple portable targets: $canonicalSource" }
        $targets[$target] = $ref
        $sources[$canonicalSource] = $target
    }
    return [pscustomobject]@{ References = @($refs); Targets = $targets; IgnoredLegacy = $ignoreMap }
}

function Add-KbPortableManifestField {
    param([string]$SourceManifest, [string]$DestinationManifest)
    $raw = Get-Content -LiteralPath $SourceManifest -Raw -Encoding UTF8
    if ($raw -notmatch '(?m)^\s*external_dir\s*:') { $raw = $raw.TrimEnd("`r", "`n") + "`nexternal_dir: external`n" }
    [IO.File]::WriteAllText($DestinationManifest, $raw, [Text.UTF8Encoding]::new($false))
}
