#Requires -Version 7.0
# Read-only navigation model. MarkdownFiles is a FileInfo[] already checked by
# the caller's data-path safety validation; EntrySourcePath is an absolute file
# below ContentRoot. Pages is keyed by content-relative source path and contains
# Source, Output, Title (plain text), Type, Children and Parents. Digest covers
# only navigation metadata and explicit edges, never arbitrary body text.
function Get-KbStaticNavigationModel {
    param([Parameter(Mandatory)][AllowEmptyCollection()][object[]]$MarkdownFiles,
        [Parameter(Mandatory)][string]$ContentRoot,
        [Parameter(Mandatory)][string]$EntrySourcePath)

    $root = [IO.Path]::GetFullPath($ContentRoot).TrimEnd('\', '/')
    $entry = [IO.Path]::GetRelativePath($root, $EntrySourcePath).Replace('\', '/')
    $pages = @{}
    $blocks = @{}
    foreach ($file in $MarkdownFiles) {
        $source = [IO.Path]::GetRelativePath($root, $file.FullName).Replace('\', '/')
        $text = [IO.File]::ReadAllText($file.FullName)
        $type = ''
        $front = [regex]::Match($text, '\A---\s*\r?\n(?<fields>[\s\S]*?)\r?\n---[ \t]*(?:\r?\n|$)')
        if ($front.Success) {
            $typeMatch = [regex]::Match($front.Groups['fields'].Value, '(?m)^type:[ \t]*(?<value>[^\r\n]*)\r?$')
            if ($typeMatch.Success) { $type = $typeMatch.Groups['value'].Value.Trim().Trim('"', "'").ToLowerInvariant() }
            $text = $text.Substring($front.Length)
        }
        # Mark only exact standalone protocol lines. The Markdown renderer then
        # distinguishes real comments from fenced/indented code, including fences
        # nested in lists/quotes, without a second approximate Markdown parser.
        $token = 'kb-nav-' + [guid]::NewGuid().ToString('N')
        $marked = [regex]::Replace($text, '(?m)^<!-- kb-nav:children:(start|end) -->\r?$', {
            param($match)
            '<!-- ' + $token + ':' + $match.Groups[1].Value + ' -->'
        })
        $html = if ([string]::IsNullOrEmpty($marked)) { '' } else { (ConvertFrom-Markdown -InputObject $marked).Html }
        $title = [IO.Path]::GetFileNameWithoutExtension($file.Name)
        $heading = [regex]::Match($html, '(?is)<h1\b[^>]*>(.*?)</h1>')
        if ($heading.Success) {
            $title = [System.Net.WebUtility]::HtmlDecode([regex]::Replace($heading.Groups[1].Value, '<[^>]+>', '')).Trim()
        }
        $markers = @([regex]::Matches($html, '<!-- ' + $token + ':(start|end) -->'))
        if ($markers.Count -ne 0) {
            if ($markers.Count -ne 2 -or $markers[0].Groups[1].Value -ne 'start' -or $markers[1].Groups[1].Value -ne 'end') {
                throw "BLOCKER: invalid kb-nav children block (duplicate, nested, or unmatched markers): $source"
            }
            if ($source -ne $entry -and $type -notin @('project', 'map')) { throw "BLOCKER: kb-nav children block requires project/map type: $source" }
            $start = $markers[0].Index + $markers[0].Length
            $blocks[$source] = $html.Substring($start, $markers[1].Index - $start)
        }
        $pages[$source] = [pscustomobject]@{
            Source = $source; Output = [regex]::Replace($source, '(?i)\.md$', '.html')
            Title = $title; Type = $type; Children = @(); Parents = @()
        }
    }
    if (-not $pages.ContainsKey($entry)) { throw 'BLOCKER: navigation entrypoint is missing from Markdown files' }
    foreach ($source in @($blocks.Keys)) {
        $block = [regex]::Replace($blocks[$source], '(?is)<(pre|code)\b[^>]*>.*?</\1>', '')
        $nestedListPattern = '(?is)(?<=<li\b[^>]*>(?:(?!<li\b)[\s\S])*?)<(ul|ol)\b(?:(?!<(ul|ol)\b)[\s\S])*?</\1>'
        while ([regex]::IsMatch($block, $nestedListPattern)) {
            $block = [regex]::Replace($block, $nestedListPattern, '')
        }
        $targets = @{}
        foreach ($anchor in [regex]::Matches($block, '(?is)<a\b[^>]*\bhref\s*=\s*"([^"]*)"[^>]*>(.*?)</a>')) {
            if ($anchor.Groups[2].Value -match '(?is)<img\b') { continue }
            $href = [System.Net.WebUtility]::HtmlDecode($anchor.Groups[1].Value)
            $path = ($href -split '#', 2)[0]
            if ($path.Contains('?')) { throw "BLOCKER: query is unsupported in kb-nav link: $source -> $href" }
            $path = [uri]::UnescapeDataString($path)
            if ([string]::IsNullOrWhiteSpace($path) -or $path -match '^[A-Za-z][A-Za-z0-9+.-]*:' -or $path.StartsWith('/') -or $path.StartsWith('\') -or [IO.Path]::IsPathRooted($path)) {
                throw "BLOCKER: kb-nav link must target a relative local Markdown file: $source -> $href"
            }
            $candidate = [IO.Path]::GetFullPath((Join-Path (Split-Path -Parent (Join-Path $root $source)) $path.Replace('/', [IO.Path]::DirectorySeparatorChar)))
            if (-not $candidate.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw "BLOCKER: kb-nav link escapes content root: $source -> $href" }
            $target = [IO.Path]::GetRelativePath($root, $candidate).Replace('\', '/')
            if (-not $pages.ContainsKey($target)) { throw "BLOCKER: kb-nav target is not an existing Markdown file: $source -> $href" }
            if ($target -eq $source) { throw "BLOCKER: self collection in kb-nav: $source" }
            if ($source -eq $entry -and $pages[$target].Type -notin @('project', 'map')) { throw "BLOCKER: entrypoint may collect only project/map pages: $target" }
            $targets[$target] = $true
        }
        $pages[$source].Children = @($targets.Keys | Sort-Object)
        foreach ($target in $pages[$source].Children) { $pages[$target].Parents = @($pages[$target].Parents) + $source }
    }
    # Kahn's algorithm checks every component, including collections disconnected
    # from the entrypoint, without recursion-depth limits.
    $indegree = @{}
    $queue = [Collections.Generic.Queue[string]]::new()
    foreach ($source in $pages.Keys) {
        $pages[$source].Parents = @($pages[$source].Parents | Sort-Object)
        $indegree[$source] = $pages[$source].Parents.Count
        if ($indegree[$source] -eq 0) { $queue.Enqueue($source) }
    }
    $visited = 0
    while ($queue.Count -gt 0) {
        $source = $queue.Dequeue(); $visited++
        foreach ($target in $pages[$source].Children) {
            $indegree[$target]--
            if ($indegree[$target] -eq 0) { $queue.Enqueue($target) }
        }
    }
    if ($visited -ne $pages.Count) { throw 'BLOCKER: cycle in kb-nav collections' }
    $records = @($pages.Keys | Sort-Object | ForEach-Object {
        $page = $pages[$_]
        [ordered]@{ source = $page.Source; output = $page.Output; title = $page.Title; type = $page.Type; children = @($page.Children) }
    })
    $serialized = [ordered]@{ entry = $entry; pages = $records } | ConvertTo-Json -Depth 6 -Compress
    $hasher = [Security.Cryptography.SHA256]::Create()
    try { $digest = [BitConverter]::ToString($hasher.ComputeHash([Text.Encoding]::UTF8.GetBytes($serialized))).Replace('-', '').ToLowerInvariant() }
    finally { $hasher.Dispose() }
    return [pscustomobject]@{ Pages = $pages; Digest = $digest; EntrySource = $entry }
}

# Encode actual filesystem-relative output paths once, including literal #/%/?;
# unlike Markdown destination normalization, this never URI-decodes file names.
function Get-KbStaticNavigationHref {
    param([Parameter(Mandatory)][string]$FromOutput, [Parameter(Mandatory)][string]$ToOutput)
    $base = [IO.Path]::GetFullPath((Join-Path ([IO.Path]::GetTempPath()) 'kb-navigation-path-base'))
    $from = Split-Path -Parent (Join-Path $base $FromOutput)
    $relative = [IO.Path]::GetRelativePath($from, (Join-Path $base $ToOutput)).Replace('\', '/')
    return (($relative -split '/' | ForEach-Object { [uri]::EscapeDataString($_) }) -join '/')
}
