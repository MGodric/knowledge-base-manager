#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Root,

    [ValidateSet('Text', 'Json')]
    [string]$Format = 'Text'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'kb-path-safety.ps1')

$issues = [System.Collections.Generic.List[object]]::new()
$fatalFailure = $false
$rootFull = $null

function Add-Issue {
    param(
        [ValidateSet('error', 'warning')]
        [string]$Severity,
        [string]$Code,
        [string]$File,
        [string]$Message,
        [string]$Target = ''
    )

    $issues.Add([pscustomobject][ordered]@{
        severity = $Severity
        code     = $Code
        file     = $File
        message  = $Message
        target   = $Target
    })
}

function Get-NormalizedRelativePath {
    param([string]$BasePath, [string]$TargetPath)

    $base = [System.IO.Path]::GetFullPath($BasePath)
    $target = [System.IO.Path]::GetFullPath($TargetPath)
    $method = [System.IO.Path].GetMethod('GetRelativePath', [type[]]@([string], [string]))
    if ($null -ne $method) {
        return ([System.IO.Path]::GetRelativePath($base, $target)).Replace('\', '/')
    }

    $separator = [System.IO.Path]::DirectorySeparatorChar
    if (-not $base.EndsWith([string]$separator)) {
        $base += $separator
    }
    $baseUri = [uri]$base
    $targetUri = [uri]$target
    return [uri]::UnescapeDataString($baseUri.MakeRelativeUri($targetUri).ToString()).Replace('\', '/')
}

function Test-PathInsideRoot {
    param([string]$Candidate, [string]$BaseRoot)

    $candidateFull = [System.IO.Path]::GetFullPath($Candidate).TrimEnd('\', '/')
    $baseFull = [System.IO.Path]::GetFullPath($BaseRoot).TrimEnd('\', '/')
    if ($candidateFull.Equals($baseFull, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $true
    }
    $prefix = $baseFull + [System.IO.Path]::DirectorySeparatorChar
    return $candidateFull.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)
}

function Read-SimpleManifest {
    param([string]$Path)

    $result = @{}
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        if ($line -match '^\s*(?<key>[A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(?<value>.*?)\s*$') {
            $value = $Matches.value.Trim()
            if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
                ($value.StartsWith("'") -and $value.EndsWith("'"))) {
                if ($value.Length -ge 2) {
                    $value = $value.Substring(1, $value.Length - 2)
                }
            }
            $result[$Matches.key] = $value
        }
    }
    return $result
}

function Get-FrontMatter {
    param([string[]]$Lines)

    $fields = @{}
    $endIndex = -1
    if ($Lines.Count -eq 0 -or $Lines[0].Trim() -ne '---') {
        return [pscustomobject]@{ Present = $false; EndIndex = -1; Fields = $fields }
    }

    for ($i = 1; $i -lt $Lines.Count; $i++) {
        if ($Lines[$i].Trim() -eq '---') {
            $endIndex = $i
            break
        }
        if ($Lines[$i] -match '^(?<key>[A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(?<value>.*)$') {
            $fields[$Matches.key] = $Matches.value.Trim().Trim('"').Trim("'")
        }
    }

    return [pscustomobject]@{
        Present  = ($endIndex -ge 1)
        EndIndex = $endIndex
        Fields   = $fields
    }
}

function Get-LevelOneHeadingCount {
    param([string[]]$Lines, [int]$StartIndex)

    $count = 0
    $inFence = $false
    for ($i = [Math]::Max(0, $StartIndex); $i -lt $Lines.Count; $i++) {
        if ($Lines[$i] -match '^\s*(```|~~~)') {
            $inFence = -not $inFence
            continue
        }
        if (-not $inFence -and $Lines[$i] -match '^#\s+\S') {
            $count++
        }
    }
    return $count
}

function Test-HighConfidenceMathExpression {
    param([string]$Content)

    $value = $Content.Trim()
    if ([string]::IsNullOrWhiteSpace($value)) {
        return $false
    }

    # Keep the detector deliberately conservative. Ordinary identifiers, commands,
    # paths, and generic function calls such as foo() remain valid code spans.
    if ($value -match '^[A-Za-z]:[\\/]' -or $value -match '^\\\\') {
        return $false
    }
    if ($value -match '(?i)^GF\s*\(\s*2\s*\^\s*\d+\s*\)$') {
        return $true
    }
    if ($value -match '(?i)^P\s*\([^)]*=.*\|.*\)$') {
        return $true
    }
    if ($value -match '(?i)^(?:alpha|beta|gamma|delta|epsilon|theta|lambda|mu|sigma|tau|phi|psi|omega)\s*\([^)]*\)$') {
        return $true
    }
    if ($value -match '[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9{}]+\s*=') {
        return $true
    }
    if ($value -match '(?<![:A-Za-z0-9_.-])\\(?:alpha|beta|gamma|delta|epsilon|theta|lambda|mu|sigma|tau|phi|psi|omega|frac|sqrt|sum|prod|int|mathrm|mathbf|mathbb|mathcal|left|right|cdot|times|leq|geq|neq|in|notin|subset|subseteq|cup|cap|to|rightarrow|ldots|dots)\b') {
        return $true
    }
    if ($value -match '[α-ωΑ-Ω∑∏√∞≈≠≤≥∈∉⊂⊆∪∩→←↔⇒⇔±×÷·∘⊕⊗∂∇∀∃∅∧∨¬]') {
        return $true
    }
    return $false
}

function Get-MathCodeSpanIssues {
    param([string[]]$Lines, [int]$StartIndex)

    $results = [System.Collections.Generic.List[object]]::new()
    $inFence = $false
    for ($i = [Math]::Max(0, $StartIndex); $i -lt $Lines.Count; $i++) {
        $line = $Lines[$i]
        if ($line -match '^\s*(```|~~~)') {
            $inFence = -not $inFence
            continue
        }
        if ($inFence -or $line -match '<!--\s*kb-literal-code\s*-->') {
            continue
        }

        foreach ($match in [regex]::Matches($line, '(?<!`)`(?<content>[^`\r\n]+)`(?!`)')) {
            $content = $match.Groups['content'].Value
            if (Test-HighConfidenceMathExpression -Content $content) {
                $results.Add([pscustomobject]@{
                    Content    = $content
                    LineNumber = $i + 1
                })
            }
        }
    }
    return $results
}

function Test-ExplicitExternalLocalLabel {
    param([string]$Line)

    if ($Line -match '(?i)kb-external-local') {
        return $true
    }
    if ($Line -match '知识库外' -and $Line -match '(仅本机|机器相关|本机专用)') {
        return $true
    }
    return ($Line -match '(?i)outside\s+(the\s+)?knowledge\s+base' -and
        $Line -match '(?i)machine[- ]specific|local[- ]only')
}

function Get-SourceVerificationMetadata {
    param([string]$Line)

    $dateMatch = [regex]::Match($Line, '(?i)(?:verified|last\s+verified|验证日期|已验证)\s*[:：]\s*(?<date>\d{4}-\d{2}-\d{2})')
    $versionMatch = [regex]::Match($Line, '(?i)(?:revision|version-state|版本状态|版本)\s*[:：]\s*(?<value>[^;；,，]+)')
    return [pscustomobject]@{
        HasDate     = $dateMatch.Success
        Date        = if ($dateMatch.Success) { $dateMatch.Groups['date'].Value } else { '' }
        HasVersion  = $versionMatch.Success -and -not [string]::IsNullOrWhiteSpace($versionMatch.Groups['value'].Value)
    }
}

function Get-MarkdownLinks {
    param([string[]]$Lines, [int]$StartIndex)

    $links = [System.Collections.Generic.List[object]]::new()
    $inFence = $false
    for ($i = [Math]::Max(0, $StartIndex); $i -lt $Lines.Count; $i++) {
        $rawLine = $Lines[$i]
        if ($rawLine -match '^\s*(```|~~~)') {
            $inFence = -not $inFence
            continue
        }
        if ($inFence) {
            continue
        }

        $searchLine = [regex]::Replace($rawLine, '`[^`]*`', '')
        foreach ($match in [regex]::Matches($searchLine, '!?\[[^\]]*\]\((?<inside>[^)]+)\)')) {
            $inside = $match.Groups['inside'].Value.Trim()
            $destination = $inside
            if ($inside.StartsWith('<')) {
                $close = $inside.IndexOf('>')
                if ($close -gt 0) {
                    $destination = $inside.Substring(1, $close - 1)
                }
            }
            elseif ($inside -match '^(?<url>\S+)(?:\s+["''].*)?$') {
                $destination = $Matches.url
            }
            $links.Add([pscustomobject]@{
                Target                  = $destination
                Line                    = $rawLine
                LineNumber              = $i + 1
                IsExplicitExternalLocal = Test-ExplicitExternalLocalLabel -Line $rawLine
            })
        }
    }
    return $links
}

function Test-IsoDate {
    param([string]$Value)

    $parsed = [datetime]::MinValue
    return [datetime]::TryParseExact(
        $Value,
        'yyyy-MM-dd',
        [System.Globalization.CultureInfo]::InvariantCulture,
        [System.Globalization.DateTimeStyles]::None,
        [ref]$parsed
    )
}

function Write-Result {
    param([int]$ExitCode)

    $severityRank = @{ error = 0; warning = 1 }
    $orderedIssues = @($issues | Sort-Object @{ Expression = { $severityRank[$_.severity] } }, file, code, target)
    $errorCount = @($orderedIssues | Where-Object severity -eq 'error').Count
    $warningCount = @($orderedIssues | Where-Object severity -eq 'warning').Count

    if ($Format -eq 'Json') {
        [pscustomobject][ordered]@{
            root     = $rootFull
            errors   = $errorCount
            warnings = $warningCount
            issues   = $orderedIssues
        } | ConvertTo-Json -Depth 6
    }
    else {
        Write-Output "Knowledge base audit: $rootFull"
        Write-Output "Errors: $errorCount  Warnings: $warningCount"
        foreach ($issue in $orderedIssues) {
            $location = if ([string]::IsNullOrWhiteSpace($issue.file)) { '' } else { " [$($issue.file)]" }
            $targetText = if ([string]::IsNullOrWhiteSpace($issue.target)) { '' } else { " -> $($issue.target)" }
            Write-Output "[$($issue.severity.ToUpperInvariant())] $($issue.code)$location$targetText - $($issue.message)"
        }
    }
    exit $ExitCode
}

try {
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
        $rootFull = [System.IO.Path]::GetFullPath($Root)
        Add-Issue error 'ROOT_NOT_FOUND' '' 'The knowledge-base root does not exist or is not a directory.' $Root
        $fatalFailure = $true
        throw 'Root not found.'
    }

    Assert-KbNoRedirectingReparsePoint -Path $Root -Label 'knowledge-base root' | Out-Null
    $rootFull = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $Root).Path).TrimEnd('\', '/')
    $manifestPath = Join-Path $rootFull 'kb.yaml'
    $manifestFile = 'kb.yaml'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        Add-Issue error 'MANIFEST_NOT_FOUND' $manifestFile 'The root must contain kb.yaml.'
        $fatalFailure = $true
        throw 'Manifest not found.'
    }
    Assert-KbNoRedirectingReparsePoint -Path $manifestPath -Label 'kb.yaml' | Out-Null

    $manifest = Read-SimpleManifest -Path $manifestPath

    foreach ($requiredKey in @('schema_version', 'content_dir', 'entrypoint')) {
        if (-not $manifest.ContainsKey($requiredKey) -or [string]::IsNullOrWhiteSpace($manifest[$requiredKey])) {
            Add-Issue error 'MANIFEST_FIELD_MISSING' $manifestFile "Required manifest field '$requiredKey' is missing."
        }
    }
    if (@($issues | Where-Object severity -eq 'error').Count -gt 0) {
        $fatalFailure = $true
        throw 'Manifest is incomplete.'
    }
    if ([string]$manifest.schema_version -ne '1') {
        Add-Issue error 'SCHEMA_VERSION_UNSUPPORTED' $manifestFile "Only schema_version 1 is supported; found '$($manifest.schema_version)'."
        $fatalFailure = $true
        throw 'Unsupported schema version.'
    }

    foreach ($fieldName in @('content_dir', 'entrypoint')) {
        $configuredPath = [string]$manifest[$fieldName]
        if ([System.IO.Path]::IsPathRooted($configuredPath)) {
            Add-Issue error 'MANIFEST_PATH_ABSOLUTE' $manifestFile "'$fieldName' must be relative to the knowledge-base root." $configuredPath
        }
    }
    if (@($issues | Where-Object severity -eq 'error').Count -gt 0) {
        $fatalFailure = $true
        throw 'Manifest contains absolute paths.'
    }

    $contentFull = [System.IO.Path]::GetFullPath((Join-Path $rootFull $manifest.content_dir))
    $entrypointFull = [System.IO.Path]::GetFullPath((Join-Path $rootFull $manifest.entrypoint))
    $externalFull = $null
    if ($manifest.ContainsKey('external_dir') -and -not [string]::IsNullOrWhiteSpace($manifest.external_dir)) {
        if ([System.IO.Path]::IsPathRooted($manifest.external_dir)) {
            Add-Issue error 'EXTERNAL_DIR_ABSOLUTE' $manifestFile 'external_dir must be relative to the knowledge-base root.' $manifest.external_dir
        }
        else {
            $externalFull = [System.IO.Path]::GetFullPath((Join-Path $rootFull $manifest.external_dir))
            if (-not (Test-PathInsideRoot -Candidate $externalFull -BaseRoot $rootFull)) {
                Add-Issue error 'EXTERNAL_DIR_ESCAPES_ROOT' $manifestFile 'external_dir resolves outside the knowledge-base root.' $manifest.external_dir
            }
            elseif (-not (Test-Path -LiteralPath $externalFull -PathType Container)) {
                Add-Issue error 'EXTERNAL_DIR_NOT_FOUND' $manifestFile 'The configured external_dir does not exist.' $manifest.external_dir
            }
        }
    }
    if (-not (Test-PathInsideRoot -Candidate $contentFull -BaseRoot $rootFull)) {
        Add-Issue error 'CONTENT_DIR_ESCAPES_ROOT' $manifestFile 'content_dir resolves outside the knowledge-base root.' $manifest.content_dir
    }
    if (-not (Test-PathInsideRoot -Candidate $entrypointFull -BaseRoot $rootFull)) {
        Add-Issue error 'ENTRYPOINT_ESCAPES_ROOT' $manifestFile 'entrypoint resolves outside the knowledge-base root.' $manifest.entrypoint
    }
    if (-not (Test-PathInsideRoot -Candidate $entrypointFull -BaseRoot $contentFull)) {
        Add-Issue error 'ENTRYPOINT_OUTSIDE_CONTENT' $manifestFile 'entrypoint must resolve inside content_dir.' $manifest.entrypoint
    }
    if (@($issues | Where-Object severity -eq 'error').Count -gt 0) {
        $fatalFailure = $true
        throw 'Manifest paths escape their allowed roots.'
    }
    if (-not (Test-Path -LiteralPath $contentFull -PathType Container)) {
        Add-Issue error 'CONTENT_DIR_NOT_FOUND' $manifest.content_dir 'The configured content directory does not exist.'
        $fatalFailure = $true
        throw 'Content directory not found.'
    }
    if (-not (Test-Path -LiteralPath $entrypointFull -PathType Leaf)) {
        Add-Issue error 'ENTRYPOINT_NOT_FOUND' $manifest.entrypoint 'The configured entrypoint does not exist.'
    }

    Assert-KbNoRedirectingReparsePoint -Path $contentFull -Label 'content_dir' | Out-Null
    Assert-KbNoRedirectingReparsePoint -Path $entrypointFull -Label 'entrypoint' | Out-Null
    $contentFiles = @(Get-KbSafeTreeFiles -Root $contentFull -Label 'knowledge-base content')
    if ($null -ne $externalFull) {
        Assert-KbNoRedirectingReparsePoint -Path $externalFull -Label 'external_dir' | Out-Null
        Get-KbSafeTreeFiles -Root $externalFull -Label 'knowledge-base external data' | Out-Null
    }

    $markdownFiles = @($contentFiles | Where-Object Extension -ieq '.md')
    $fileInfoByFullPath = @{}
    $inboundCount = @{}
    $ids = @{}
    $parsedFiles = @{}

    foreach ($file in $markdownFiles) {
        $full = [System.IO.Path]::GetFullPath($file.FullName)
        $relative = Get-NormalizedRelativePath -BasePath $contentFull -TargetPath $full
        $fileInfoByFullPath[$full] = $file
        $inboundCount[$relative] = 0

        $lines = @(Get-Content -LiteralPath $full -Encoding UTF8)
        $frontMatter = Get-FrontMatter -Lines $lines
        $bodyStart = if ($frontMatter.Present) { $frontMatter.EndIndex + 1 } else { 0 }
        $parsedFiles[$relative] = [pscustomobject]@{
            FullPath    = $full
            Relative    = $relative
            Lines       = $lines
            FrontMatter = $frontMatter
            BodyStart   = $bodyStart
        }

        $headingCount = Get-LevelOneHeadingCount -Lines $lines -StartIndex $bodyStart
        if ($headingCount -ne 1) {
            Add-Issue error 'H1_COUNT_INVALID' $relative "Expected exactly one level-one heading; found $headingCount."
        }

        foreach ($mathCodeSpan in Get-MathCodeSpanIssues -Lines $lines -StartIndex $bodyStart) {
            Add-Issue error 'MATH_CODE_SPAN' $relative "Inline code on line $($mathCodeSpan.LineNumber) looks like a mathematical expression; write inline math as `$...`$ or display math as `$$...`$$. Use <!-- kb-literal-code --> on the same line only when literal code is intentional." $mathCodeSpan.Content
        }

        $isEntrypoint = $full.Equals($entrypointFull, [System.StringComparison]::OrdinalIgnoreCase)
        $isInbox = $relative.StartsWith('inbox/', [System.StringComparison]::OrdinalIgnoreCase)
        $isArchive = $relative.StartsWith('archive/', [System.StringComparison]::OrdinalIgnoreCase)
        $isFormal = -not $isEntrypoint -and -not $isInbox -and -not $isArchive

        if ($isFormal) {
            if (-not $frontMatter.Present) {
                Add-Issue error 'FRONT_MATTER_MISSING' $relative 'Formal entries require YAML front matter.'
                continue
            }

            foreach ($fieldName in @('id', 'type', 'status', 'created', 'updated')) {
                if (-not $frontMatter.Fields.ContainsKey($fieldName) -or [string]::IsNullOrWhiteSpace($frontMatter.Fields[$fieldName])) {
                    Add-Issue error 'ENTRY_FIELD_MISSING' $relative "Required field '$fieldName' is missing."
                }
            }

            if ($frontMatter.Fields.ContainsKey('id')) {
                $id = [string]$frontMatter.Fields.id
                if ($id -notmatch '^kb-\d{8}-[0-9a-fA-F]{4,}$') {
                    Add-Issue error 'ID_FORMAT_INVALID' $relative "ID '$id' must match kb-YYYYMMDD-xxxx with a hexadecimal suffix."
                }
                if (-not $ids.ContainsKey($id)) {
                    $ids[$id] = [System.Collections.Generic.List[string]]::new()
                }
                $ids[$id].Add($relative)
            }
            if ($frontMatter.Fields.ContainsKey('type') -and $frontMatter.Fields.type -notin @('concept', 'method', 'source', 'decision', 'project', 'map')) {
                Add-Issue error 'TYPE_INVALID' $relative "Unknown type '$($frontMatter.Fields.type)'."
            }
            if ($frontMatter.Fields.ContainsKey('status') -and $frontMatter.Fields.status -notin @('draft', 'stable', 'deprecated')) {
                Add-Issue error 'STATUS_INVALID' $relative "Unknown status '$($frontMatter.Fields.status)'."
            }
            foreach ($dateField in @('created', 'updated')) {
                if ($frontMatter.Fields.ContainsKey($dateField) -and -not (Test-IsoDate -Value $frontMatter.Fields[$dateField])) {
                    Add-Issue error 'DATE_INVALID' $relative "Field '$dateField' must use a valid YYYY-MM-DD date."
                }
            }
        }
    }

    foreach ($id in $ids.Keys) {
        if ($ids[$id].Count -gt 1) {
            foreach ($relative in $ids[$id]) {
                $others = @($ids[$id] | Where-Object { $_ -ne $relative }) -join ', '
                Add-Issue error 'ID_DUPLICATE' $relative "ID '$id' is also used by: $others."
            }
        }
    }

    foreach ($parsed in $parsedFiles.Values) {
        $sourceRelative = $parsed.Relative
        $sourceIsCurrent = -not $sourceRelative.StartsWith('inbox/', [System.StringComparison]::OrdinalIgnoreCase) -and
            -not $sourceRelative.StartsWith('archive/', [System.StringComparison]::OrdinalIgnoreCase)

        foreach ($link in Get-MarkdownLinks -Lines $parsed.Lines -StartIndex $parsed.BodyStart) {
            $rawTarget = [string]$link.Target
            if ([string]::IsNullOrWhiteSpace($rawTarget) -or $rawTarget.StartsWith('#')) {
                continue
            }
            $isPortableSource = $link.Line -match '(?i)<!--\s*kb-portable-source\s*-->'
            if ($rawTarget -match '^[A-Za-z]:[\\/]' -or $rawTarget.StartsWith('\\')) {
                if (-not $link.IsExplicitExternalLocal) {
                    Add-Issue warning 'ABSOLUTE_LOCAL_LINK' $sourceRelative 'Local absolute links require an explicit outside-knowledge-base, machine-specific label.' $rawTarget
                    continue
                }

                $sourceMetadata = Get-SourceVerificationMetadata -Line $link.Line
                if (-not $sourceMetadata.HasDate) {
                    Add-Issue warning 'SOURCE_VERIFIED_DATE_MISSING' $sourceRelative "The labeled external local source on line $($link.LineNumber) requires verified: YYYY-MM-DD." $rawTarget
                }
                elseif (-not (Test-IsoDate -Value $sourceMetadata.Date)) {
                    Add-Issue warning 'SOURCE_VERIFIED_DATE_INVALID' $sourceRelative "The labeled external local source on line $($link.LineNumber) has an invalid verification date." $rawTarget
                }
                if (-not $sourceMetadata.HasVersion) {
                    Add-Issue warning 'SOURCE_VERSION_STATE_MISSING' $sourceRelative "The labeled external local source on line $($link.LineNumber) requires revision: <value> or version-state: <value>." $rawTarget
                }
                continue
            }
            if ($rawTarget -match '^[A-Za-z][A-Za-z0-9+.-]*:') {
                continue
            }
            if ($rawTarget.Contains('\')) {
                Add-Issue warning 'BACKSLASH_LINK' $sourceRelative 'Use / separators in Markdown links.' $rawTarget
            }

            $pathPart = ($rawTarget -split '#', 2)[0]
            $pathPart = ($pathPart -split '\?', 2)[0]
            if ([string]::IsNullOrWhiteSpace($pathPart)) {
                continue
            }
            try {
                $decodedPath = [uri]::UnescapeDataString($pathPart).Replace('/', [System.IO.Path]::DirectorySeparatorChar)
            }
            catch {
                Add-Issue error 'LINK_ENCODING_INVALID' $sourceRelative 'The link target contains invalid URL encoding.' $rawTarget
                continue
            }
            if ($isPortableSource -and $null -eq $externalFull) {
                Add-Issue error 'PORTABLE_LINK_WITHOUT_EXTERNAL_DIR' $sourceRelative 'A kb-portable-source link requires a valid external_dir in kb.yaml.' $rawTarget
                continue
            }

            if ([System.IO.Path]::IsPathRooted($decodedPath)) {
                Add-Issue warning 'ROOT_RELATIVE_LINK' $sourceRelative 'Use a relative Markdown link instead of a root-relative path.' $rawTarget
                $decodedPath = $decodedPath.TrimStart('\', '/')
                $rootForRootRelative = if ($isPortableSource) { $externalFull } else { $contentFull }
                $candidateFull = [System.IO.Path]::GetFullPath((Join-Path $rootForRootRelative $decodedPath))
            }
            else {
                $candidateFull = [System.IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $parsed.FullPath) $decodedPath))
            }

            $allowedRoot = if ($isPortableSource) { $externalFull } else { $contentFull }
            if (-not (Test-PathInsideRoot -Candidate $candidateFull -BaseRoot $allowedRoot)) {
                $code = if ($isPortableSource) { 'PORTABLE_LINK_ESCAPES_EXTERNAL' } else { 'LINK_ESCAPES_CONTENT' }
                $message = if ($isPortableSource) { 'Portable source links must remain inside external_dir.' } else { 'Internal links must remain inside content_dir.' }
                Add-Issue error $code $sourceRelative $message $rawTarget
                continue
            }
            if (-not (Test-Path -LiteralPath $candidateFull)) {
                Add-Issue error 'LINK_BROKEN' $sourceRelative 'The internal link target does not exist.' $rawTarget
                continue
            }
            if (Test-Path -LiteralPath $candidateFull -PathType Container) {
                Add-Issue warning 'DIRECTORY_LINK' $sourceRelative 'Link to a Markdown entry rather than a directory.' $rawTarget
                continue
            }

            $actualFull = [System.IO.Path]::GetFullPath((Get-Item -LiteralPath $candidateFull).FullName)
            $expectedRelative = Get-NormalizedRelativePath -BasePath $contentFull -TargetPath $candidateFull
            $actualRelative = Get-NormalizedRelativePath -BasePath $contentFull -TargetPath $actualFull
            if (-not $expectedRelative.Equals($actualRelative, [System.StringComparison]::Ordinal)) {
                Add-Issue warning 'LINK_CASE_MISMATCH' $sourceRelative 'Link path casing differs from the stored target.' $rawTarget
            }

            if ($actualFull.EndsWith('.md', [System.StringComparison]::OrdinalIgnoreCase) -and $inboundCount.ContainsKey($actualRelative) -and $sourceIsCurrent) {
                $inboundCount[$actualRelative]++
                if ($actualRelative.StartsWith('archive/', [System.StringComparison]::OrdinalIgnoreCase)) {
                    Add-Issue warning 'CURRENT_LINKS_TO_ARCHIVE' $sourceRelative 'Current content links to archived material; explain why the historical target is still relevant.' $rawTarget
                }
            }
        }
    }

    foreach ($parsed in $parsedFiles.Values) {
        $relative = $parsed.Relative
        $isEntrypoint = $parsed.FullPath.Equals($entrypointFull, [System.StringComparison]::OrdinalIgnoreCase)
        $excluded = $isEntrypoint -or
            $relative.StartsWith('inbox/', [System.StringComparison]::OrdinalIgnoreCase) -or
            $relative.StartsWith('archive/', [System.StringComparison]::OrdinalIgnoreCase)
        if (-not $excluded -and $inboundCount[$relative] -eq 0) {
            Add-Issue warning 'ORPHAN_ENTRY' $relative 'No current entry or map links to this formal entry.'
        }
    }

    foreach ($file in $contentFiles) {
        $relative = Get-NormalizedRelativePath -BasePath $contentFull -TargetPath $file.FullName
        if ($file.Name -match '(?i)(conflicted copy|sync-conflict|conflict copy|冲突副本|冲突的副本)') {
            Add-Issue warning 'SYNC_CONFLICT_COPY' $relative 'This filename looks like a synchronization conflict copy.'
        }
        elseif ($file.Name -match '(?i)(\.tmp$|\.temp$|\.swp$|~$|^~\$)') {
            Add-Issue warning 'TEMPORARY_FILE' $relative 'Temporary files should not remain in the synchronized knowledge base.'
        }
    }
}
catch {
    if (-not $fatalFailure) {
        Add-Issue error 'AUDIT_RUNTIME_FAILURE' '' $_.Exception.Message
        $fatalFailure = $true
    }
}

$errors = @($issues | Where-Object severity -eq 'error').Count
if ($fatalFailure) {
    Write-Result -ExitCode 3
}
elseif ($errors -gt 0) {
    Write-Result -ExitCode 2
}
else {
    Write-Result -ExitCode 0
}
