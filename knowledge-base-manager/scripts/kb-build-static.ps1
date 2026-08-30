#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Root,

    [Parameter(Mandatory = $true)]
    [string]$Destination,

    [switch]$Force,

    # This is intended for isolated verification fixtures. Normal Skill use
    # always reads the versioned assets shipped alongside this script.
    [string]$KatexAssetsRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'kb-path-safety.ps1')

# Bump either value when generated page markup or its common template changes.
$generatorVersion = '1.1.0'
$templateVersion = '2'
$manifestName = '.kb-static-manifest.json'
$katexAssetVersion = '0.18.1'

function Test-KbStaticPathInside {
    param([Parameter(Mandatory)][string]$Candidate, [Parameter(Mandatory)][string]$Base)

    $candidateFull = [IO.Path]::GetFullPath($Candidate).TrimEnd('\', '/')
    $baseFull = [IO.Path]::GetFullPath($Base).TrimEnd('\', '/')
    if ($candidateFull.Equals($baseFull, [StringComparison]::OrdinalIgnoreCase)) { return $true }
    return $candidateFull.StartsWith($baseFull + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)
}

function Get-KbStaticRelativePath {
    param([Parameter(Mandatory)][string]$Base, [Parameter(Mandatory)][string]$Path)
    return [IO.Path]::GetRelativePath($Base, $Path).Replace('\', '/')
}

function Get-KbStaticSha256 {
    param([Parameter(Mandatory)][string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Read-KbStaticManifestFields {
    param([Parameter(Mandatory)][string]$Path)
    $values = @{}
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        if ($line -match '^\s*(?<key>[A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(?<value>.*?)\s*$') {
            $value = $Matches.value.Trim()
            if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            $values[$Matches.key] = $value
        }
    }
    return $values
}

function Get-KbStaticBody {
    param([Parameter(Mandatory)][string]$Text)

    # Front matter is metadata only when the opening delimiter begins the file
    # and has a matching delimiter. Other horizontal rules remain Markdown.
    if (-not $Text.StartsWith('---')) { return $Text }
    $lines = $Text -split "`r?`n", 0
    if ($lines.Count -lt 2 -or $lines[0].Trim() -ne '---') { return $Text }
    for ($index = 1; $index -lt $lines.Count; $index++) {
        if ($lines[$index].Trim() -eq '---') {
            if ($index -eq ($lines.Count - 1)) { return '' }
            return (($lines[($index + 1)..($lines.Count - 1)]) -join "`n")
        }
    }
    return $Text
}

function Get-KbStaticLinkDestination {
    param([Parameter(Mandatory)][string]$Inside)
    $trimmed = $Inside.Trim()
    if ($trimmed.StartsWith('<')) {
        $close = $trimmed.IndexOf('>')
        if ($close -gt 0) {
            return [pscustomobject]@{ Destination = $trimmed.Substring(1, $close - 1); Suffix = $trimmed.Substring($close + 1) }
        }
    }
    $match = [regex]::Match($trimmed, '^(?<destination>\S+)(?<suffix>\s+.*)?$')
    if ($match.Success) {
        return [pscustomobject]@{ Destination = $match.Groups['destination'].Value; Suffix = $match.Groups['suffix'].Value }
    }
    return [pscustomobject]@{ Destination = $trimmed; Suffix = '' }
}

function ConvertTo-KbStaticHref {
    param([Parameter(Mandatory)][string]$Target)

    $pathPart = ($Target -split '[?#]', 2)[0]
    $trailer = $Target.Substring($pathPart.Length)
    try { $decoded = [uri]::UnescapeDataString($pathPart) }
    catch { $decoded = $pathPart }
    # Markdig requires spaces in link destinations to be URI encoded. Encode
    # path components individually so relative navigation and / remain intact.
    $encoded = (([regex]::Split($decoded, '/') | ForEach-Object { [uri]::EscapeDataString($_) }) -join '/')
    return $encoded + $trailer
}

function Convert-KbStaticSingleLink {
    param(
        [Parameter(Mandatory)][System.Text.RegularExpressions.Match]$Match,
        [Parameter(Mandatory)][string]$SourceFile,
        [Parameter(Mandatory)][string]$ContentRoot
    )

    $parsed = Get-KbStaticLinkDestination -Inside $Match.Groups['inside'].Value
    $target = [string]$parsed.Destination
    if ([string]::IsNullOrWhiteSpace($target) -or $target.StartsWith('#') -or $target -match '^[A-Za-z][A-Za-z0-9+.-]*:' -or $target.StartsWith('\\')) { return $Match.Value }
    $pathPart = ($target -split '[?#]', 2)[0]
    if ([string]::IsNullOrWhiteSpace($pathPart)) { return $Match.Value }
    try { $decodedPath = [uri]::UnescapeDataString($pathPart).Replace('/', [IO.Path]::DirectorySeparatorChar) }
    catch { return $Match.Value }
    if ([IO.Path]::IsPathRooted($decodedPath)) { return $Match.Value }
    $candidate = [IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $SourceFile) $decodedPath))
    if (-not (Test-KbStaticPathInside -Candidate $candidate -Base $ContentRoot)) { return $Match.Value }

    $rewritten = $target
    if ($pathPart -match '(?i)\.md$') {
        $rewritten = [regex]::Replace($target, '(?i)\.md(?=([?#]|$))', '.html')
    }
    elseif (Test-Path -LiteralPath $candidate -PathType Container) {
        $suffix = $target.Substring($pathPart.Length)
        $directoryPart = $pathPart.TrimEnd('/', '\')
        $rewritten = if ([string]::IsNullOrWhiteSpace($directoryPart)) { 'index.html' + $suffix } else { $directoryPart + '/index.html' + $suffix }
    }
    if ($rewritten -eq $target) { return $Match.Value }
    return $Match.Groups['prefix'].Value + (ConvertTo-KbStaticHref -Target $rewritten) + $parsed.Suffix + $Match.Groups['close'].Value
}

function Convert-KbStaticLinks {
    param(
        [Parameter(Mandatory)][string]$Markdown,
        [Parameter(Mandatory)][string]$SourceFile,
        [Parameter(Mandatory)][string]$ContentRoot
    )

    return [regex]::Replace($Markdown, '(?<prefix>!?\[[^\]]*\]\()(?<inside>[^)]+)(?<close>\))', {
        param($match)
        Convert-KbStaticSingleLink -Match $match -SourceFile $SourceFile -ContentRoot $ContentRoot
    })
}

function Get-KbStaticPageOutputPath {
    param([Parameter(Mandatory)][string]$RelativeSource)
    if ($RelativeSource -match '(?i)(^|/)index\.md$') {
        return [regex]::Replace($RelativeSource, '(?i)index\.md$', 'index.html')
    }
    return [regex]::Replace($RelativeSource, '(?i)\.md$', '.html')
}

function Get-KbStaticKatexPrefix {
    param([Parameter(Mandatory)][string]$OutputRelative)

    $directory = Split-Path -Parent ($OutputRelative.Replace('/', [IO.Path]::DirectorySeparatorChar))
    if ([string]::IsNullOrWhiteSpace($directory) -or $directory -eq '.') { return './_assets/katex' }
    $levels = @($directory -split '[\\/]+' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }).Count
    return (('../' * $levels) + '_assets/katex')
}

function New-KbStaticHtmlDocument {
    param(
        [Parameter(Mandatory)][string]$Title,
        [Parameter(Mandatory)][string]$BodyHtml,
        [Parameter(Mandatory)][string]$OutputRelative
    )
    $safeTitle = [System.Net.WebUtility]::HtmlEncode($Title)
    $katexPrefix = Get-KbStaticKatexPrefix -OutputRelative $OutputRelative
    $template = @'
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{0}</title>
<style>body{{max-width:920px;margin:2rem auto;padding:0 1rem;font:16px/1.65 system-ui,sans-serif;color:#1f2937}}a{{color:#0f5da8}}pre{{overflow:auto;padding:1rem;background:#f3f4f6}}code{{font-family:ui-monospace,monospace}}table{{border-collapse:collapse}}th,td{{border:1px solid #d1d5db;padding:.4rem .6rem}}</style>
<link rel="stylesheet" href="{2}/katex.min.css">
<script defer src="{2}/katex.min.js"></script>
<script defer src="{2}/contrib/auto-render.min.js"></script>
<script defer>document.addEventListener('DOMContentLoaded',function(){{renderMathInElement(document.body,{{delimiters:[{{left:'\\(',right:'\\)',display:false}},{{left:'\\[',right:'\\]',display:true}}],throwOnError:false}});}});</script>
</head>
<body>
{1}
</body>
</html>
'@
    return [string]::Format($template, $safeTitle, $BodyHtml, $katexPrefix)
}

function Get-KbStaticSafeAssetFiles {
    param(
        [Parameter(Mandatory)][string]$Root,
        [string]$Label = 'asset tree'
    )

    # The installed Skill directory may itself be a development junction. That
    # installation path is outside the generated-data safety boundary, so only
    # the asset root and entries below it are checked here. A redirect at the
    # asset root or anywhere inside the bundled tree remains a blocker.
    $rootFull = [IO.Path]::GetFullPath($Root)
    if (-not (Test-Path -LiteralPath $rootFull -PathType Container)) {
        throw "BLOCKER: $Label is not a directory: $rootFull"
    }
    $rootItem = Get-Item -LiteralPath $rootFull -Force -ErrorAction Stop
    if (Test-KbRedirectingReparsePoint $rootItem) {
        throw "BLOCKER: $Label contains a junction or symbolic link: $rootFull"
    }

    $files = [System.Collections.Generic.List[System.IO.FileInfo]]::new()
    foreach ($item in Get-ChildItem -LiteralPath $rootFull -Recurse -Force) {
        if (Test-KbRedirectingReparsePoint $item) {
            throw "BLOCKER: $Label contains a junction or symbolic link: $($item.FullName)"
        }
        if (-not $item.PSIsContainer) { $files.Add($item) }
    }
    return @($files)
}

function Get-KbStaticKatexAssetRecords {
    param([Parameter(Mandatory)][string]$AssetsRoot)

    $assetsFull = [IO.Path]::GetFullPath($AssetsRoot)
    $files = @(Get-KbStaticSafeAssetFiles -Root $assetsFull -Label 'bundled KaTeX assets')
    foreach ($required in @('katex.min.js', 'katex.min.css', 'contrib/auto-render.min.js')) {
        $requiredPath = Join-Path $assetsFull ($required.Replace('/', [IO.Path]::DirectorySeparatorChar))
        if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) { throw "BLOCKER: bundled KaTeX asset is missing: $required" }
    }
    $fontsRoot = Join-Path $assetsFull 'fonts'
    if (-not (Test-Path -LiteralPath $fontsRoot -PathType Container)) { throw 'BLOCKER: bundled KaTeX fonts directory is missing' }
    if (@($files | Where-Object { (Get-KbStaticRelativePath -Base $assetsFull -Path $_.FullName) -match '^fonts/' }).Count -eq 0) {
        throw 'BLOCKER: bundled KaTeX fonts directory is empty'
    }
    return @($files | Sort-Object FullName | ForEach-Object {
        $relative = Get-KbStaticRelativePath -Base $assetsFull -Path $_.FullName
        [pscustomobject][ordered]@{
            source_path = 'assets/katex/' + $relative
            source_relative_path = $relative
            output_path = '_assets/katex/' + $relative
            sha256 = Get-KbStaticSha256 -Path $_.FullName
            full_path = $_.FullName
        }
    })
}

function Get-KbStaticDirectoryHash {
    param([Parameter(Mandatory)][string]$Directory, [Parameter(Mandatory)][string]$ContentRoot)
    $children = @(
        Get-ChildItem -LiteralPath $Directory -Force | Where-Object { $_.PSIsContainer -or $_.Extension -ieq '.md' } |
            ForEach-Object { if ($_.PSIsContainer) { 'd:' + $_.Name } else { 'm:' + $_.Name } } | Sort-Object
    )
    $text = ((Get-KbStaticRelativePath -Base $ContentRoot -Path $Directory) + "`n" + ($children -join "`n"))
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes($text)
    return ([Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes))).ToLowerInvariant()
}

try {
    $defaultKatexAssetsRoot = Join-Path (Split-Path -Parent $PSScriptRoot) 'assets\katex'
    $effectiveKatexAssetsRoot = if ([string]::IsNullOrWhiteSpace($KatexAssetsRoot)) { $defaultKatexAssetsRoot } else { $KatexAssetsRoot }
    $katexAssets = @(Get-KbStaticKatexAssetRecords -AssetsRoot $effectiveKatexAssetsRoot)
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) { throw "BLOCKER: knowledge-base root is not a directory: $Root" }
    $rootFull = [IO.Path]::GetFullPath((Resolve-Path -LiteralPath $Root).Path).TrimEnd('\', '/')
    Assert-KbNoRedirectingReparsePoint -Path $rootFull -Label 'knowledge-base root' | Out-Null
    $kbManifestPath = Join-Path $rootFull 'kb.yaml'
    if (-not (Test-Path -LiteralPath $kbManifestPath -PathType Leaf)) { throw 'BLOCKER: knowledge-base root must contain kb.yaml' }
    Assert-KbNoRedirectingReparsePoint -Path $kbManifestPath -Label 'kb.yaml' | Out-Null
    $kbManifest = Read-KbStaticManifestFields -Path $kbManifestPath
    if (-not $kbManifest.ContainsKey('content_dir') -or [string]::IsNullOrWhiteSpace($kbManifest.content_dir)) { throw 'BLOCKER: kb.yaml must define content_dir' }
    if (-not $kbManifest.ContainsKey('entrypoint') -or [string]::IsNullOrWhiteSpace($kbManifest.entrypoint)) { throw 'BLOCKER: kb.yaml must define entrypoint' }
    if ([IO.Path]::IsPathRooted([string]$kbManifest.content_dir)) { throw 'BLOCKER: content_dir must be relative to the knowledge-base root' }
    $contentRoot = [IO.Path]::GetFullPath((Join-Path $rootFull ([string]$kbManifest.content_dir)))
    if (-not (Test-KbStaticPathInside -Candidate $contentRoot -Base $rootFull)) { throw 'BLOCKER: content_dir escapes knowledge-base root' }
    if (-not (Test-Path -LiteralPath $contentRoot -PathType Container)) { throw "BLOCKER: content_dir is not a directory: $contentRoot" }
    Assert-KbNoRedirectingReparsePoint -Path $contentRoot -Label 'knowledge-base content' | Out-Null
    $contentFiles = @(Get-KbSafeTreeFiles -Root $contentRoot -Label 'knowledge-base content')
    if ([IO.Path]::IsPathRooted([string]$kbManifest.entrypoint)) { throw 'BLOCKER: entrypoint must be relative to the knowledge-base root' }
    $entrypointFull = [IO.Path]::GetFullPath((Join-Path $rootFull ([string]$kbManifest.entrypoint)))
    if (-not (Test-KbStaticPathInside -Candidate $entrypointFull -Base $contentRoot)) { throw 'BLOCKER: entrypoint must resolve inside content_dir' }
    if (-not (Test-Path -LiteralPath $entrypointFull -PathType Leaf) -or [IO.Path]::GetExtension($entrypointFull) -ine '.md') { throw 'BLOCKER: entrypoint must be an existing Markdown file' }
    $entrypointRelative = Get-KbStaticRelativePath -Base $contentRoot -Path $entrypointFull
    $entryOutputRelative = Get-KbStaticPageOutputPath -RelativeSource $entrypointRelative

    $destinationFull = [IO.Path]::GetFullPath($Destination).TrimEnd('\', '/')
    Assert-KbNoRedirectingReparsePoint -Path $destinationFull -Label 'static-site destination' | Out-Null
    if ((Test-KbStaticPathInside -Candidate $destinationFull -Base $rootFull) -or (Test-KbStaticPathInside -Candidate $rootFull -Base $destinationFull)) {
        throw 'BLOCKER: static-site destination must be outside and must not contain the knowledge-base root'
    }
    if (Test-Path -LiteralPath $destinationFull -PathType Leaf) { throw "BLOCKER: static-site destination is a file: $destinationFull" }
    if (-not (Test-Path -LiteralPath $destinationFull)) { New-Item -ItemType Directory -Path $destinationFull -Force | Out-Null }
    Assert-KbNoRedirectingReparsePoint -Path $destinationFull -Label 'static-site destination' | Out-Null

    $manifestPath = Join-Path $destinationFull $manifestName
    $previous = $null
    if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
        try { $previous = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json }
        catch { throw "BLOCKER: existing static-site manifest is invalid JSON: $($_.Exception.Message)" }
        if ($previous.schema -ne 'knowledge-base-static-site' -or [int]$previous.schema_version -ne 1) { throw 'BLOCKER: existing static-site manifest uses an unsupported schema' }
    }
    $previousPages = @{}
    $previousDirectories = @{}
    $previousKatexAssets = @{}
    if ($null -ne $previous) {
        foreach ($page in @($previous.pages)) { $previousPages[[string]$page.source_path] = $page }
        foreach ($directory in @($previous.directories)) { $previousDirectories[[string]$directory.output_path] = $directory }
        if ($null -ne $previous.PSObject.Properties['katex']) {
            foreach ($asset in @($previous.katex.assets)) { $previousKatexAssets[[string]$asset.source_path] = $asset }
        }
    }
    $stateMatches = $null -ne $previous -and $previous.generator_version -eq $generatorVersion -and $previous.template_version -eq $templateVersion
    $katexStateMatches = $null -ne $previous -and $null -ne $previous.PSObject.Properties['katex'] -and $previous.katex.asset_version -eq $katexAssetVersion

    $markdownFiles = @($contentFiles | Where-Object { $_.Extension -ieq '.md' } | Sort-Object FullName)
    $directories = @($contentRoot) + @(Get-ChildItem -LiteralPath $contentRoot -Recurse -Directory -Force | ForEach-Object FullName)
    $currentOutputPaths = @{}
    foreach ($file in $markdownFiles) {
        $currentOutputPaths[(Get-KbStaticPageOutputPath -RelativeSource (Get-KbStaticRelativePath -Base $contentRoot -Path $file.FullName))] = $true
    }
    foreach ($directory in $directories) {
        if (Test-Path -LiteralPath (Join-Path $directory 'index.md') -PathType Leaf) { continue }
        $relative = Get-KbStaticRelativePath -Base $contentRoot -Path $directory
        $directoryOutput = if ([string]::IsNullOrEmpty($relative) -or $relative -eq '.') { 'index.html' } else { $relative + '/index.html' }
        $currentOutputPaths[$directoryOutput] = $true
    }
    $previousOwnedOutputs = @{}
    foreach ($record in @($previousPages.Values) + @($previousDirectories.Values) + @($previousKatexAssets.Values)) {
        $relative = [string]$record.output_path
        if (-not [string]::IsNullOrWhiteSpace($relative) -and -not [IO.Path]::IsPathRooted($relative) -and $relative -notmatch '(^|[\\/])\.\.([\\/]|$)') {
            $previousOwnedOutputs[$relative] = $true
        }
    }
    foreach ($relative in $currentOutputPaths.Keys) {
        $candidate = [IO.Path]::GetFullPath((Join-Path $destinationFull ($relative.Replace('/', [IO.Path]::DirectorySeparatorChar))))
        if (-not (Test-KbStaticPathInside -Candidate $candidate -Base $destinationFull)) { throw "BLOCKER: static output path escapes destination: $relative" }
        if (Test-Path -LiteralPath $candidate -PathType Container) { throw "BLOCKER: static output path is an existing directory: $relative" }
        if ((Test-Path -LiteralPath $candidate -PathType Leaf) -and -not $previousOwnedOutputs.ContainsKey($relative)) {
            throw "BLOCKER: refusing to overwrite destination file not owned by a prior static-site manifest: $relative"
        }
    }
    foreach ($asset in $katexAssets) {
        $candidate = [IO.Path]::GetFullPath((Join-Path $destinationFull ($asset.output_path.Replace('/', [IO.Path]::DirectorySeparatorChar))))
        if (-not (Test-KbStaticPathInside -Candidate $candidate -Base $destinationFull)) { throw "BLOCKER: KaTeX asset output path escapes destination: $($asset.output_path)" }
        if (Test-Path -LiteralPath $candidate -PathType Container) { throw "BLOCKER: KaTeX asset output is an existing directory: $($asset.output_path)" }
        if ((Test-Path -LiteralPath $candidate -PathType Leaf) -and -not $previousOwnedOutputs.ContainsKey($asset.output_path)) {
            throw "BLOCKER: refusing to overwrite destination file not owned by a prior static-site manifest: $($asset.output_path)"
        }
    }
    $generated = [Collections.Generic.List[string]]::new()
    $skipped = [Collections.Generic.List[string]]::new()
    $removed = [Collections.Generic.List[string]]::new()
    $assetGenerated = [Collections.Generic.List[string]]::new()
    $assetSkipped = [Collections.Generic.List[string]]::new()
    $assetRecords = [Collections.Generic.List[object]]::new()
    foreach ($asset in $katexAssets) {
        $outputPath = Join-Path $destinationFull ($asset.output_path.Replace('/', [IO.Path]::DirectorySeparatorChar))
        $old = if ($previousKatexAssets.ContainsKey($asset.source_path)) { $previousKatexAssets[$asset.source_path] } else { $null }
        $canSkip = -not $Force.IsPresent -and $katexStateMatches -and $null -ne $old -and $old.sha256 -eq $asset.sha256 -and $old.output_path -eq $asset.output_path -and (Test-Path -LiteralPath $outputPath -PathType Leaf)
        if ($canSkip -and $null -ne $old.PSObject.Properties['output_sha256']) {
            $canSkip = ([string]$old.output_sha256 -eq (Get-KbStaticSha256 -Path $outputPath))
        }
        if ($canSkip) {
            $outputHash = Get-KbStaticSha256 -Path $outputPath
            $assetSkipped.Add($asset.output_path)
        }
        else {
            $parent = Split-Path -Parent $outputPath
            if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
            [IO.File]::Copy($asset.full_path, $outputPath, $true)
            $outputHash = Get-KbStaticSha256 -Path $outputPath
            if ($outputHash -ne $asset.sha256) { throw "BLOCKER: copied KaTeX asset hash does not match source: $($asset.source_path)" }
            $assetGenerated.Add($asset.output_path)
        }
        $assetRecords.Add([pscustomobject][ordered]@{ source_path = $asset.source_path; output_path = $asset.output_path; sha256 = $asset.sha256; output_sha256 = $outputHash })
    }
    $pageRecords = [Collections.Generic.List[object]]::new()
    foreach ($file in $markdownFiles) {
        $sourceRelative = Get-KbStaticRelativePath -Base $contentRoot -Path $file.FullName
        $outputRelative = Get-KbStaticPageOutputPath -RelativeSource $sourceRelative
        $currentOutputPaths[$outputRelative] = $true
        $sourceHash = Get-KbStaticSha256 -Path $file.FullName
        $outputPath = Join-Path $destinationFull ($outputRelative.Replace('/', [IO.Path]::DirectorySeparatorChar))
        $old = if ($previousPages.ContainsKey($sourceRelative)) { $previousPages[$sourceRelative] } else { $null }
        $canSkip = -not $Force.IsPresent -and $stateMatches -and $null -ne $old -and $old.sha256 -eq $sourceHash -and $old.output_path -eq $outputRelative -and (Test-Path -LiteralPath $outputPath -PathType Leaf)
        if ($canSkip -and $null -ne $old.PSObject.Properties['output_sha256']) {
            $canSkip = ([string]$old.output_sha256 -eq (Get-KbStaticSha256 -Path $outputPath))
        }
        if ($canSkip) {
            $outputHash = Get-KbStaticSha256 -Path $outputPath
            $skipped.Add($outputRelative)
        }
        else {
            $markdown = Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8
            $body = Get-KbStaticBody -Text $markdown
            $rewritten = Convert-KbStaticLinks -Markdown $body -SourceFile $file.FullName -ContentRoot $contentRoot
            $rendered = ConvertFrom-Markdown -InputObject $rewritten
            $title = [IO.Path]::GetFileNameWithoutExtension($file.Name)
            if ($rewritten -match '(?m)^#\s+(?<title>.+?)\s*$') { $title = $Matches.title.Trim() }
            $html = New-KbStaticHtmlDocument -Title $title -BodyHtml $rendered.Html -OutputRelative $outputRelative
            $parent = Split-Path -Parent $outputPath
            if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
            [IO.File]::WriteAllText($outputPath, $html, [Text.UTF8Encoding]::new($false))
            $outputHash = Get-KbStaticSha256 -Path $outputPath
            $generated.Add($outputRelative)
        }
        $pageRecords.Add([pscustomobject][ordered]@{ source_path = $sourceRelative; output_path = $outputRelative; sha256 = $sourceHash; output_sha256 = $outputHash })
    }

    $directoryRecords = [Collections.Generic.List[object]]::new()
    foreach ($directory in $directories | Sort-Object) {
        $directoryRelative = Get-KbStaticRelativePath -Base $contentRoot -Path $directory
        $outputRelative = if ([string]::IsNullOrEmpty($directoryRelative) -or $directoryRelative -eq '.') { 'index.html' } else { $directoryRelative + '/index.html' }
        $directoryIndexSource = Join-Path $directory 'index.md'
        if (Test-Path -LiteralPath $directoryIndexSource -PathType Leaf) { continue }
        $currentOutputPaths[$outputRelative] = $true
        $structureHash = Get-KbStaticDirectoryHash -Directory $directory -ContentRoot $contentRoot
        $outputPath = Join-Path $destinationFull ($outputRelative.Replace('/', [IO.Path]::DirectorySeparatorChar))
        $old = if ($previousDirectories.ContainsKey($outputRelative)) { $previousDirectories[$outputRelative] } else { $null }
        $canSkip = -not $Force.IsPresent -and $stateMatches -and $null -ne $old -and $old.structure_sha256 -eq $structureHash -and (Test-Path -LiteralPath $outputPath -PathType Leaf)
        if ($canSkip -and $null -ne $old.PSObject.Properties['output_sha256']) { $canSkip = ([string]$old.output_sha256 -eq (Get-KbStaticSha256 -Path $outputPath)) }
        if ($canSkip) {
            $outputHash = Get-KbStaticSha256 -Path $outputPath
            $skipped.Add($outputRelative)
        }
        else {
            $items = [Collections.Generic.List[string]]::new()
            foreach ($child in Get-ChildItem -LiteralPath $directory -Force | Sort-Object @{ Expression = { -not $_.PSIsContainer } }, Name) {
                if ($child.PSIsContainer) { $href = './' + [uri]::EscapeDataString($child.Name) + '/index.html'; $label = $child.Name + '/' }
                elseif ($child.Extension -ieq '.md') { $childRelative = Get-KbStaticRelativePath -Base $contentRoot -Path $child.FullName; $href = './' + ((Get-KbStaticPageOutputPath -RelativeSource $childRelative) -split '/' | Select-Object -Last 1); $label = [IO.Path]::GetFileNameWithoutExtension($child.Name) }
                else { continue }
                $items.Add('<li><a href="' + [System.Net.WebUtility]::HtmlEncode($href) + '">' + [System.Net.WebUtility]::HtmlEncode($label) + '</a></li>')
            }
            $heading = if ([string]::IsNullOrEmpty($directoryRelative) -or $directoryRelative -eq '.') { 'Knowledge Base' } else { $directoryRelative }
            $html = New-KbStaticHtmlDocument -Title $heading -BodyHtml ('<h1>' + [System.Net.WebUtility]::HtmlEncode($heading) + '</h1><ul>' + ($items -join "`n") + '</ul>') -OutputRelative $outputRelative
            $parent = Split-Path -Parent $outputPath
            if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
            [IO.File]::WriteAllText($outputPath, $html, [Text.UTF8Encoding]::new($false))
            $outputHash = Get-KbStaticSha256 -Path $outputPath
            $generated.Add($outputRelative)
        }
        $directoryRecords.Add([pscustomobject][ordered]@{ output_path = $outputRelative; structure_sha256 = $structureHash; output_sha256 = $outputHash })
    }

    foreach ($oldPage in $previousPages.Values) {
        if ($currentOutputPaths.ContainsKey([string]$oldPage.output_path)) { continue }
        $relative = [string]$oldPage.output_path
        if ([string]::IsNullOrWhiteSpace($relative) -or [IO.Path]::IsPathRooted($relative) -or $relative -match '(^|[\\/])\.\.([\\/]|$)') { continue }
        $candidate = [IO.Path]::GetFullPath((Join-Path $destinationFull ($relative.Replace('/', [IO.Path]::DirectorySeparatorChar))))
        if ((Test-KbStaticPathInside -Candidate $candidate -Base $destinationFull) -and (Test-Path -LiteralPath $candidate -PathType Leaf) -and $null -ne $oldPage.PSObject.Properties['output_sha256'] -and (Get-KbStaticSha256 -Path $candidate) -eq [string]$oldPage.output_sha256) {
            Remove-Item -LiteralPath $candidate -Force
            $removed.Add($relative)
        }
    }
    foreach ($oldDirectory in $previousDirectories.Values) {
        if ($currentOutputPaths.ContainsKey([string]$oldDirectory.output_path)) { continue }
        $relative = [string]$oldDirectory.output_path
        if ([string]::IsNullOrWhiteSpace($relative) -or [IO.Path]::IsPathRooted($relative) -or $relative -match '(^|[\\/])\.\.([\\/]|$)') { continue }
        $candidate = [IO.Path]::GetFullPath((Join-Path $destinationFull ($relative.Replace('/', [IO.Path]::DirectorySeparatorChar))))
        if ((Test-KbStaticPathInside -Candidate $candidate -Base $destinationFull) -and (Test-Path -LiteralPath $candidate -PathType Leaf) -and $null -ne $oldDirectory.PSObject.Properties['output_sha256'] -and (Get-KbStaticSha256 -Path $candidate) -eq [string]$oldDirectory.output_sha256) {
            Remove-Item -LiteralPath $candidate -Force
            $removed.Add($relative)
        }
    }

    $currentKatexSources = @{}
    foreach ($asset in $katexAssets) { $currentKatexSources[$asset.source_path] = $true }
    foreach ($oldAsset in $previousKatexAssets.Values) {
        if ($currentKatexSources.ContainsKey([string]$oldAsset.source_path)) { continue }
        $relative = [string]$oldAsset.output_path
        if ([string]::IsNullOrWhiteSpace($relative) -or $relative -notmatch '^_assets/katex(?:/|$)' -or [IO.Path]::IsPathRooted($relative) -or $relative -match '(^|[\\/])\.\.([\\/]|$)') { continue }
        $candidate = [IO.Path]::GetFullPath((Join-Path $destinationFull ($relative.Replace('/', [IO.Path]::DirectorySeparatorChar))))
        if (-not (Test-KbStaticPathInside -Candidate $candidate -Base $destinationFull) -or -not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        if ($null -eq $oldAsset.PSObject.Properties['output_sha256'] -or [string]::IsNullOrWhiteSpace([string]$oldAsset.output_sha256)) { continue }
        if ((Get-KbStaticSha256 -Path $candidate) -ne [string]$oldAsset.output_sha256) { continue }
        Remove-Item -LiteralPath $candidate -Force
        $removed.Add($relative)
    }

    $newManifest = [pscustomobject][ordered]@{
        schema = 'knowledge-base-static-site'; schema_version = 1; generator_version = $generatorVersion; template_version = $templateVersion
        root_content_dir = $contentRoot; entry_source_path = $entrypointRelative; entry_output_path = $entryOutputRelative; generated_utc = [DateTime]::UtcNow.ToString('o')
        katex = [pscustomobject][ordered]@{ asset_version = $katexAssetVersion; assets = @($assetRecords | Sort-Object source_path) }
        pages = @($pageRecords | Sort-Object source_path); directories = @($directoryRecords | Sort-Object output_path)
    }
    $newManifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding UTF8 -NoNewline
    [pscustomobject][ordered]@{
        status = 'success'; root = $rootFull; destination = $destinationFull; manifest = $manifestName; entry_page = (Join-Path $destinationFull ($entryOutputRelative.Replace('/', [IO.Path]::DirectorySeparatorChar)))
        generator_version = $generatorVersion; template_version = $templateVersion
        force_rebuild = [bool]$Force.IsPresent
        generated = $generated.Count; generated_paths = @($generated); skipped = $skipped.Count; skipped_paths = @($skipped); removed = $removed.Count; removed_paths = @($removed)
        assets_generated = $assetGenerated.Count; assets_generated_paths = @($assetGenerated); assets_skipped = $assetSkipped.Count; assets_skipped_paths = @($assetSkipped)
    } | ConvertTo-Json -Depth 6
}
catch {
    [pscustomobject][ordered]@{ status = 'blocked'; message = $_.Exception.Message } | ConvertTo-Json -Depth 4
    exit 2
}
