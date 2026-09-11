#Requires -Version 7.0
# Graph and preview data extraction module for static knowledge base reader.
# Produces GraphDataV1 and PreviewDataV1 conforming to docs/local/proposals/知识库图谱设计与数据接口.md.
# Pure PowerShell 7, zero external dependencies.

function Get-KbPageFrontmatter {
    param([Parameter(Mandatory)][string]$Text)

    $result = [ordered]@{
        id = $null
        type = $null
        status = $null
        tags = @()
    }
    if (-not $Text.StartsWith('---')) { return $result }
    $front = [regex]::Match($Text, '\A---\s*\r?\n(?<fields>[\s\S]*?)\r?\n---[ \t]*(?:\r?\n|$)')
    if (-not $front.Success) { return $result }
    $fields = $front.Groups['fields'].Value

    $idMatch = [regex]::Match($fields, '(?m)^id:[ \t]*(?<val>[^\r\n#]+)')
    if ($idMatch.Success) {
        $val = $idMatch.Groups['val'].Value.Trim().Trim('"', "'")
        if (-not [string]::IsNullOrWhiteSpace($val)) { $result.id = $val }
    }
    $typeMatch = [regex]::Match($fields, '(?m)^type:[ \t]*(?<val>[^\r\n#]+)')
    if ($typeMatch.Success) {
        $val = $typeMatch.Groups['val'].Value.Trim().Trim('"', "'").ToLowerInvariant()
        if (-not [string]::IsNullOrWhiteSpace($val)) { $result.type = $val }
    }
    $statusMatch = [regex]::Match($fields, '(?m)^status:[ \t]*(?<val>[^\r\n#]+)')
    if ($statusMatch.Success) {
        $val = $statusMatch.Groups['val'].Value.Trim().Trim('"', "'").ToLowerInvariant()
        if (-not [string]::IsNullOrWhiteSpace($val)) { $result.status = $val }
    }
    $inlineTags = [regex]::Match($fields, '(?m)^tags:[ \t]*\[(?<val>[^\]]*)\]')
    if ($inlineTags.Success) {
        $rawTags = $inlineTags.Groups['val'].Value -split ','
        $tagList = [System.Collections.Generic.List[string]]::new()
        foreach ($t in $rawTags) {
            $clean = $t.Trim().Trim('"', "'")
            if (-not [string]::IsNullOrWhiteSpace($clean)) { $tagList.Add($clean) }
        }
        $result.tags = @($tagList)
    } else {
        $blockTags = [regex]::Match($fields, '(?m)^tags:[ \t]*\r?\n(?<items>(?:[ \t]+-[ \t]+[^\r\n]+\r?\n?)+)')
        if ($blockTags.Success) {
            $tagList = [System.Collections.Generic.List[string]]::new()
            foreach ($line in ($blockTags.Groups['items'].Value -split '\r?\n')) {
                $m = [regex]::Match($line, '^[ \t]+-[ \t]+(?<val>[^\r\n#]+)')
                if ($m.Success) {
                    $clean = $m.Groups['val'].Value.Trim().Trim('"', "'")
                    if (-not [string]::IsNullOrWhiteSpace($clean)) { $tagList.Add($clean) }
                }
            }
            $result.tags = @($tagList)
        }
    }
    return $result
}

function Update-KbHeadingAnchors {
    param(
        [Parameter(Mandatory)][string]$Html,
        [string]$OwnerPageId = '',
        [string]$SourcePath = ''
    )

    $usedIds = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
    $diagnostics = [System.Collections.Generic.List[object]]::new()

    foreach ($m in [regex]::Matches($Html, '(?i)\bid\s*=\s*(?<q>["''])(?<id>[^"'']+)\k<q>')) {
        $usedIds.Add($m.Groups['id'].Value) | Out-Null
    }

    $codeTokens = [System.Collections.Generic.List[string]]::new()
    $tokenPrefix = 'KBCODEBLOCK_' + [guid]::NewGuid().ToString('N') + '_'
    $tokenRegex = '(?is)<(pre|code)\b[^>]*>.*?</\1>'
    $maskedHtml = [regex]::Replace($Html, $tokenRegex, {
        param($match)
        $idx = $codeTokens.Count
        $codeTokens.Add($match.Value)
        return "<!-- ${tokenPrefix}${idx} -->"
    })

    $headingRegex = '(?is)<h(?<level>[2-6])(?<attrs>\b[^>]*)>(?<content>.*?)</h\k<level>>'
    $headingMatches = @([regex]::Matches($maskedHtml, $headingRegex))

    $h24ToAssign = [System.Collections.Generic.List[int]]::new()
    $h56ToAssign = [System.Collections.Generic.List[int]]::new()
    $headingIds = [string[]]::new($headingMatches.Count)
    $seenHeadingIds = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)

    for ($i = 0; $i -lt $headingMatches.Count; $i++) {
        $m = $headingMatches[$i]
        $lvl = [int]$m.Groups['level'].Value
        $attrs = $m.Groups['attrs'].Value
        $idMatch = [regex]::Match($attrs, '(?i)\bid\s*=\s*(?<q>["''])(?<id>[^"'']+)\k<q>')
        if ($idMatch.Success) {
            $existingId = $idMatch.Groups['id'].Value
            $headingIds[$i] = $existingId
            if (-not $seenHeadingIds.Add($existingId)) {
                $diagnostics.Add([ordered]@{
                    code = 'duplicate_heading_id'
                    severity = 'warning'
                    source_path = $SourcePath
                    link_ordinal = $null
                    message = "Duplicate heading id '$existingId' in $SourcePath"
                })
            }
        } else {
            if ($lvl -le 4) { $h24ToAssign.Add($i) } else { $h56ToAssign.Add($i) }
        }
    }

    $nextNum = 1
    foreach ($idx in $h24ToAssign) {
        while ($usedIds.Contains("kb-heading-$nextNum")) { $nextNum++ }
        $id = "kb-heading-$nextNum"
        $usedIds.Add($id) | Out-Null
        $headingIds[$idx] = $id
    }
    foreach ($idx in $h56ToAssign) {
        while ($usedIds.Contains("kb-heading-$nextNum")) { $nextNum++ }
        $id = "kb-heading-$nextNum"
        $usedIds.Add($id) | Out-Null
        $headingIds[$idx] = $id
    }

    $sections = [System.Collections.Generic.List[object]]::new()
    $sb = [System.Text.StringBuilder]::new()
    $lastIndex = 0
    $ancestors = [System.Collections.Generic.List[object]]::new()

    for ($i = 0; $i -lt $headingMatches.Count; $i++) {
        $m = $headingMatches[$i]
        $sb.Append($maskedHtml.Substring($lastIndex, $m.Index - $lastIndex)) | Out-Null
        $lastIndex = $m.Index + $m.Length

        $lvl = [int]$m.Groups['level'].Value
        $attrs = $m.Groups['attrs'].Value
        $content = $m.Groups['content'].Value
        $finalId = $headingIds[$i]

        $newAttrs = if ($attrs -match '(?i)\bid\s*=\s*') {
            $attrs
        } else {
            " id=""$finalId""$attrs"
        }
        $sb.Append("<h$lvl$newAttrs>$content</h$lvl>") | Out-Null

        $plainTitle = [System.Net.WebUtility]::HtmlDecode([regex]::Replace($content, '<[^>]+>', '')).Trim()
        $secNodeId = if ($OwnerPageId) { "section:$OwnerPageId#$finalId" } else { "section:#$finalId" }

        while ($ancestors.Count -gt 0 -and $ancestors[$ancestors.Count - 1].Level -ge $lvl) {
            $ancestors.RemoveAt($ancestors.Count - 1)
        }
        $parentNodeId = if ($ancestors.Count -gt 0) { $ancestors[$ancestors.Count - 1].NodeId } else { $OwnerPageId }
        $ancestors.Add([pscustomobject]@{ Level = $lvl; NodeId = $secNodeId })

        $contentStart = $m.Index + $m.Length
        $contentEnd = if ($i + 1 -lt $headingMatches.Count) { $headingMatches[$i + 1].Index } else { $maskedHtml.Length }
        $secHtmlSlice = $maskedHtml.Substring($contentStart, [Math]::Max(0, $contentEnd - $contentStart))

        $sections.Add([pscustomobject]@{
            NodeId = $secNodeId
            HeadingLevel = $lvl
            Ordinal = $i
            Title = $plainTitle
            Fragment = $finalId
            ParentNodeId = $parentNodeId
            OwnerPageId = $OwnerPageId
            HtmlContent = $secHtmlSlice
        })
    }
    $sb.Append($maskedHtml.Substring($lastIndex)) | Out-Null
    $reconstructed = $sb.ToString()

    for ($i = 0; $i -lt $codeTokens.Count; $i++) {
        $reconstructed = $reconstructed.Replace("<!-- ${tokenPrefix}${i} -->", $codeTokens[$i])
    }

    return [pscustomobject]@{
        Html = $reconstructed
        Sections = @($sections)
        Diagnostics = @($diagnostics)
    }
}

function Get-KbTextExcerpt {
    param(
        [Parameter(Mandatory)][string]$Html,
        [int]$MaxLength = 600
    )

    $clean = [regex]::Replace($Html, '(?is)<(h[1-6]|pre|script|style)\b[^>]*>.*?</\1>', ' ')
    $clean = [regex]::Replace($clean, '(?is)<!-- kb-nav:children:start -->.*?<!-- kb-nav:children:end -->', ' ')

    $blockMatch = [regex]::Match($clean, '(?is)<(p|ul|ol|blockquote|table)\b[^>]*>.*?</\1>')
    $candidateHtml = if ($blockMatch.Success) { $blockMatch.Value } else { $clean }

    $cleanText = [regex]::Replace($candidateHtml, '(?is)<br\s*/?>', ' ')
    $cleanText = [regex]::Replace($cleanText, '(?is)</(p|li|tr|div|blockquote|td|th)>', ' ')
    $cleanText = [regex]::Replace($cleanText, '<[^>]+>', ' ')
    $decoded = [System.Net.WebUtility]::HtmlDecode($cleanText)
    $text = [regex]::Replace($decoded, '\s+', ' ').Trim()

    if (-not [string]::IsNullOrWhiteSpace($text)) {
        $truncated = $false
        if ($text.Length -gt $MaxLength) {
            $text = $text.Substring(0, $MaxLength)
            $truncated = $true
        }
        return [pscustomobject]@{
            Mode = 'excerpt'
            Text = $text
            Truncated = $truncated
        }
    }

    return [pscustomobject]@{
        Mode = 'unavailable'
        Text = ''
        Truncated = $false
    }
}

function Get-KbSha256Hex {
    param([Parameter(Mandatory)][string]$Text)
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        return [BitConverter]::ToString($hasher.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($Text))).Replace('-', '').ToLowerInvariant()
    } finally {
        $hasher.Dispose()
    }
}

function Get-KbGraphModel {
    param(
        [Parameter(Mandatory)][string]$ContentRoot,
        [Parameter(Mandatory)][object]$Navigation,
        [object[]]$ValidatedPages,
        [object[]]$MarkdownFiles
    )

    $root = [IO.Path]::GetFullPath($ContentRoot).TrimEnd('\', '/')
    $entrypoint = $Navigation.EntrySource.Replace('\', '/')

    $pages = [System.Collections.Generic.List[object]]::new()
    $formalIds = [System.Collections.Generic.Dictionary[string, string]]::new([System.StringComparer]::OrdinalIgnoreCase)

    if ($null -ne $ValidatedPages -and $ValidatedPages.Count -gt 0) {
        foreach ($vp in $ValidatedPages) {
            $source = [string]$vp.Source
            if ($source.StartsWith('inbox/', [System.StringComparison]::OrdinalIgnoreCase) -or
                $source.StartsWith('archive/', [System.StringComparison]::OrdinalIgnoreCase)) {
                continue
            }
            $raw = if ($null -ne $vp.PSObject.Properties['RawMarkdown']) { [string]$vp.RawMarkdown } else { '' }
            $fm = if ($null -ne $vp.PSObject.Properties['Frontmatter'] -and $null -ne $vp.Frontmatter) {
                $vp.Frontmatter
            } else {
                Get-KbPageFrontmatter -Text $raw
            }
            $title = if ($null -ne $vp.PSObject.Properties['Title'] -and -not [string]::IsNullOrWhiteSpace($vp.Title)) {
                [string]$vp.Title
            } elseif ($Navigation.Pages.ContainsKey($source)) {
                $Navigation.Pages[$source].Title
            } else {
                [IO.Path]::GetFileNameWithoutExtension($source)
            }
            $output = if ($Navigation.Pages.ContainsKey($source)) {
                $Navigation.Pages[$source].Output
            } else {
                [regex]::Replace($source, '(?i)\.md$', '.html')
            }
            $html = if ($null -ne $vp.PSObject.Properties['Html']) { [string]$vp.Html } else { $null }

            $pages.Add([pscustomobject]@{
                Source = $source
                Output = $output
                Title = $title
                RawMarkdown = $raw
                Frontmatter = $fm
                PreRenderedHtml = $html
            })
        }
    } elseif ($null -ne $MarkdownFiles -and $MarkdownFiles.Count -gt 0) {
        foreach ($file in $MarkdownFiles) {
            $source = [IO.Path]::GetRelativePath($root, $file.FullName).Replace('\', '/')
            if ($source.StartsWith('inbox/', [System.StringComparison]::OrdinalIgnoreCase) -or
                $source.StartsWith('archive/', [System.StringComparison]::OrdinalIgnoreCase)) {
                continue
            }
            $raw = [IO.File]::ReadAllText($file.FullName)
            $fm = Get-KbPageFrontmatter -Text $raw
            $title = if ($Navigation.Pages.ContainsKey($source)) {
                $Navigation.Pages[$source].Title
            } else {
                [IO.Path]::GetFileNameWithoutExtension($file.Name)
            }
            $output = if ($Navigation.Pages.ContainsKey($source)) {
                $Navigation.Pages[$source].Output
            } else {
                [regex]::Replace($source, '(?i)\.md$', '.html')
            }
            $pages.Add([pscustomobject]@{
                Source = $source
                Output = $output
                Title = $title
                RawMarkdown = $raw
                Frontmatter = $fm
                PreRenderedHtml = $null
            })
        }
    } else {
        throw "BLOCKER: Get-KbGraphModel requires either ValidatedPages or MarkdownFiles"
    }

    $pageNodeIds = [System.Collections.Generic.Dictionary[string, string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($p in $pages) {
        $kbId = $p.Frontmatter.id
        if (-not [string]::IsNullOrWhiteSpace($kbId)) {
            if ($formalIds.ContainsKey($kbId)) {
                throw "BLOCKER: duplicate formal id '$kbId' in '$($formalIds[$kbId])' and '$($p.Source)'"
            }
            $formalIds[$kbId] = $p.Source
            $pageNodeIds[$p.Source] = "page:id:$kbId"
        } else {
            $pageNodeIds[$p.Source] = "page:path:$($p.Source)"
        }
    }

    if (-not $pageNodeIds.ContainsKey($entrypoint)) {
        throw "BLOCKER: entrypoint '$entrypoint' not found in validated pages"
    }
    $entryId = $pageNodeIds[$entrypoint]

    $nodes = [System.Collections.Generic.Dictionary[string, object]]::new([System.StringComparer]::Ordinal)
    $edges = [System.Collections.Generic.Dictionary[string, object]]::new([System.StringComparer]::Ordinal)
    $previewRecords = [System.Collections.Generic.Dictionary[string, object]]::new([System.StringComparer]::Ordinal)
    $diagnostics = [System.Collections.Generic.List[object]]::new()
    $pageFragments = [System.Collections.Generic.Dictionary[string, System.Collections.Generic.HashSet[string]]]::new([System.StringComparer]::OrdinalIgnoreCase)

    $renderedPageMap = @{}
    foreach ($p in $pages) {
        $source = $p.Source
        $pageNodeId = $pageNodeIds[$source]
        $fm = $p.Frontmatter

        $rawHtml = if ($null -ne $p.PreRenderedHtml) {
            $p.PreRenderedHtml
        } else {
            $text = $p.RawMarkdown
            if ($text.StartsWith('---')) {
                $frontMatch = [regex]::Match($text, '\A---\s*\r?\n[\s\S]*?\r?\n---[ \t]*(?:\r?\n|$)')
                if ($frontMatch.Success) { $text = $text.Substring($frontMatch.Length) }
            }
            if ([string]::IsNullOrWhiteSpace($text)) { '' } else { (ConvertFrom-Markdown -InputObject $text).Html }
        }

        $anchorResult = Update-KbHeadingAnchors -Html $rawHtml -OwnerPageId $pageNodeId -SourcePath $source
        $unifiedHtml = $anchorResult.Html
        $sections = $anchorResult.Sections
        if ($null -ne $anchorResult.Diagnostics -and $anchorResult.Diagnostics.Count -gt 0) {
            $diagnostics.AddRange($anchorResult.Diagnostics)
        }

        $fragSet = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
        foreach ($sec in $sections) {
            $fragSet.Add($sec.Fragment) | Out-Null
        }
        $pageFragments[$source] = $fragSet

        $pageTarget = [ordered]@{
            kind = 'internal'
            path = $p.Output
            fragment = $null
        }

        $pageKbId = if (-not [string]::IsNullOrWhiteSpace($fm.id)) { [string]$fm.id } else { $null }
        $pageType = if (-not [string]::IsNullOrWhiteSpace($fm.type)) { [string]$fm.type } else { $null }
        $pageStatus = if (-not [string]::IsNullOrWhiteSpace($fm.status)) { [string]$fm.status } else { $null }

        $pageDetails = [ordered]@{
            source_path = $source
            kb_id = $pageKbId
            type = $pageType
            status = $pageStatus
            tags = @($fm.tags)
        }
        $pageNode = [ordered]@{
            id = $pageNodeId
            kind = 'page'
            title = $p.Title
            depth = $null
            target = $pageTarget
            preview_key = $pageNodeId
            page = $pageDetails
            section = $null
            reference = $null
        }
        $nodes[$pageNodeId] = $pageNode

        $pageExcerpt = Get-KbTextExcerpt -Html $unifiedHtml -MaxLength 600
        $pageOrigin = if ($pageExcerpt.Mode -eq 'excerpt') { 'rendered-body' } else { 'none' }

        $previewRecords[$pageNodeId] = [ordered]@{
            key = $pageNodeId
            node_id = $pageNodeId
            mode = $pageExcerpt.Mode
            text = $pageExcerpt.Text
            truncated = $pageExcerpt.Truncated
            origin = $pageOrigin
        }

        $siblingCounters = @{}
        foreach ($sec in $sections) {
            if ($source -eq $entrypoint -or $sec.Title -match '(?i)^(待整理笔记|待整理|收件箱|inbox)$') {
                continue
            }
            $secNodeId = $sec.NodeId
            $secTarget = [ordered]@{
                kind = 'internal'
                path = $p.Output
                fragment = $sec.Fragment
            }
            $secDetails = [ordered]@{
                owner_page = $pageNodeId
                heading_level = [int]$sec.HeadingLevel
                ordinal = [int]$sec.Ordinal
            }
            $secNode = [ordered]@{
                id = $secNodeId
                kind = 'section'
                title = $sec.Title
                depth = $null
                target = $secTarget
                preview_key = $secNodeId
                page = $null
                section = $secDetails
                reference = $null
            }
            $nodes[$secNodeId] = $secNode

            $secExcerpt = Get-KbTextExcerpt -Html $sec.HtmlContent -MaxLength 600
            $secOrigin = if ($secExcerpt.Mode -eq 'excerpt') { 'rendered-body' } else { 'none' }

            $previewRecords[$secNodeId] = [ordered]@{
                key = $secNodeId
                node_id = $secNodeId
                mode = $secExcerpt.Mode
                text = $secExcerpt.Text
                truncated = $secExcerpt.Truncated
                origin = $secOrigin
            }

            $parentId = $sec.ParentNodeId
            if (-not $siblingCounters.ContainsKey($parentId)) { $siblingCounters[$parentId] = 0 }
            $containsOrder = $siblingCounters[$parentId]
            $siblingCounters[$parentId] = $containsOrder + 1

            $sourceSecOcc = if ($parentId -ne $pageNodeId) { $parentId } else { $null }

            $containsEdgeId = "edge:contains:$parentId->$secNodeId"
            $edges[$containsEdgeId] = [ordered]@{
                id = $containsEdgeId
                kind = 'contains'
                source = $parentId
                target = $secNodeId
                order = $containsOrder
                occurrences = @(
                    [ordered]@{
                        owner_page = $pageNodeId
                        source_section = $sourceSecOcc
                        link_ordinal = -1
                        target_fragment = $sec.Fragment
                        label = $sec.Title
                    }
                )
            }
        }

        $renderedPageMap[$source] = [pscustomobject]@{
            Page = $p
            UnifiedHtml = $unifiedHtml
            Sections = $sections
        }
    }

    # Collects edges
    foreach ($p in $pages) {
        $source = $p.Source
        $pageNodeId = $pageNodeIds[$source]

        $rawText = $p.RawMarkdown
        $navBlockMatch = [regex]::Match($rawText, '(?is)<!-- kb-nav:children:start -->([\s\S]*?)<!-- kb-nav:children:end -->')
        $orderedChildren = [System.Collections.Generic.List[string]]::new()

        $collectSourceNodeId = $pageNodeId
        if ($source -ne $entrypoint -and $renderedPageMap.ContainsKey($source)) {
            $matchedSec = $renderedPageMap[$source].Sections | Where-Object { $_.HtmlContent -match '<!--\s*kb-nav:children:start\s*-->' } | Select-Object -Last 1
            if ($null -ne $matchedSec -and $nodes.ContainsKey($matchedSec.NodeId)) {
                $collectSourceNodeId = $matchedSec.NodeId
            }
        }
        if ($navBlockMatch.Success) {
            $blockText = $navBlockMatch.Groups[1].Value
            $blockText = [regex]::Replace($blockText, '(?is)```[\s\S]*?```', '')
            $topLevelBlockText = [regex]::Replace($blockText, '(?m)^[ \t]+[-*+0-9].*$', '')
            $linkMatches = [regex]::Matches($topLevelBlockText, '(?is)\[([^\]]*)\]\((<[^>]+>|[^)\s]+)[^)]*\)')
            $seenChildren = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)

            foreach ($lm in $linkMatches) {
                $rawTarget = $lm.Groups[2].Value.Trim().Trim('<', '>')
                $targetPath = ($rawTarget -split '[?#]', 2)[0]
                try { $decodedPath = [uri]::UnescapeDataString($targetPath) } catch { $decodedPath = $targetPath }
                $candidate = [IO.Path]::GetFullPath((Join-Path (Split-Path -Parent (Join-Path $root $source)) $decodedPath.Replace('/', [IO.Path]::DirectorySeparatorChar)))
                if ($candidate.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
                    $relChild = [IO.Path]::GetRelativePath($root, $candidate).Replace('\', '/')
                    if ($pageNodeIds.ContainsKey($relChild) -and $seenChildren.Add($relChild)) {
                        $orderedChildren.Add($relChild)
                    }
                }
            }
        }

        if ($Navigation.Pages.ContainsKey($source)) {
            $navChildren = @($Navigation.Pages[$source].Children)
            foreach ($nc in $navChildren) {
                if (-not $orderedChildren.Contains($nc)) {
                    $orderedChildren.Add($nc)
                }
            }
        }

        $collectOrder = 0
        foreach ($childSource in $orderedChildren) {
            if ($pageNodeIds.ContainsKey($childSource)) {
                $childNodeId = $pageNodeIds[$childSource]
                $collectEdgeId = "edge:collects:$collectSourceNodeId->$childNodeId"
                $childTitle = if ($Navigation.Pages.ContainsKey($childSource)) { $Navigation.Pages[$childSource].Title } else { $childSource }

                $edges[$collectEdgeId] = [ordered]@{
                    id = $collectEdgeId
                    kind = 'collects'
                    source = $collectSourceNodeId
                    target = $childNodeId
                    order = $collectOrder++
                    occurrences = @(
                        [ordered]@{
                            owner_page = $pageNodeId
                            source_section = if ($collectSourceNodeId -ne $pageNodeId) { $collectSourceNodeId } else { $null }
                            link_ordinal = 0
                            target_fragment = $null
                            label = $childTitle
                        }
                    )
                }
            }
        }
    }

    # References edges
    foreach ($p in $pages) {
        $source = $p.Source
        $pageNodeId = $pageNodeIds[$source]
        $unifiedHtml = $renderedPageMap[$source].UnifiedHtml

        $cleanHtml = [regex]::Replace($unifiedHtml, '(?is)<(pre|code)\b[^>]*>.*?</\1>', '')
        $cleanHtml = [regex]::Replace($cleanHtml, '(?is)<!-- kb-nav:children:start -->.*?<!-- kb-nav:children:end -->', '')

        $scanRegex = '(?is)(?<heading><h(?<hlevel>[2-6])\b[^>]*\bid\s*=\s*(?<hquote>["''])(?<hid>[^"'']+)\k<hquote>[^>]*>)|(?<anchor><a\b(?<aattrs>[^>]*)\bhref\s*=\s*(?<aquote>["''])(?<href>[^"'']*)\k<aquote>[^>]*>(?<alabel>.*?)</a>)'
        $scanMatches = [regex]::Matches($cleanHtml, $scanRegex)

        $currentSectionNodeId = $null
        $linkOrdinal = 0
        $refEdgeOccurrences = @{}
        $refEdgeOrder = @{}
        $nextRefOrder = 0

        foreach ($sm in $scanMatches) {
            if ($sm.Groups['heading'].Success) {
                $hid = $sm.Groups['hid'].Value
                $candidateSecId = "section:$pageNodeId#$hid"
                $currentSectionNodeId = if ($nodes.ContainsKey($candidateSecId)) { $candidateSecId } else { $null }
                continue
            }

            $href = [System.Net.WebUtility]::HtmlDecode($sm.Groups['href'].Value).Trim()
            $rawLabel = $sm.Groups['alabel'].Value
            if ($rawLabel -match '(?is)<img\b') { continue }

            $plainLabel = [System.Net.WebUtility]::HtmlDecode([regex]::Replace($rawLabel, '<[^>]+>', '')).Trim()
            $ordinal = $linkOrdinal++

            if ([string]::IsNullOrWhiteSpace($href)) { continue }

            if ($href -match '^[a-zA-Z][a-zA-Z0-9+.-]*:' -and $href -notmatch '^(https?|file):') {
                $diagnostics.Add([ordered]@{
                    code = 'unsupported_scheme'
                    severity = 'warning'
                    source_path = $source
                    link_ordinal = $ordinal
                    message = "Unsupported link scheme in href '$href'"
                })
                continue
            }

            $targetNodeId = $null
            $targetFragment = $null

            # Determine whether this link is on the same line as <!-- kb-external-local -->
            $lineStart = $cleanHtml.LastIndexOf("`n", $sm.Index)
            if ($lineStart -lt 0) { $lineStart = 0 }
            $lineEnd = $cleanHtml.IndexOf("`n", $sm.Index + $sm.Length)
            if ($lineEnd -lt 0) { $lineEnd = $cleanHtml.Length }
            $lineText = $cleanHtml.Substring($lineStart, $lineEnd - $lineStart)
            $isExternalLocal = ($href -match '^file://') -or ($lineText -match '<!--\s*kb-external-local\s*-->')

            if ($href.StartsWith('#')) {
                $frag = $href.Substring(1)
                $targetFragment = $frag
                $targetNodeId = $pageNodeId
                if (-not $pageFragments[$source].Contains($frag)) {
                    $diagnostics.Add([ordered]@{
                        code = 'missing_fragment'
                        severity = 'warning'
                        source_path = $source
                        link_ordinal = $ordinal
                        message = "Target fragment '#$frag' not found in $source"
                    })
                }
            } elseif ($href -match '^https?://') {
                $canonicalTarget = "web:$href"
                $refHash = Get-KbSha256Hex -Text $canonicalTarget
                $refNodeId = "ref:$refHash"
                $targetNodeId = $refNodeId

                if (-not $nodes.ContainsKey($refNodeId)) {
                    $refTitle = if (-not [string]::IsNullOrWhiteSpace($plainLabel)) { $plainLabel } else { $href }
                    $nodes[$refNodeId] = [ordered]@{
                        id = $refNodeId
                        kind = 'reference'
                        title = $refTitle
                        target = [ordered]@{
                            kind = 'web'
                            url = $href
                        }
                        preview_key = $refNodeId
                        page = $null
                        section = $null
                        reference = [ordered]@{
                            medium = 'web'
                            source_label = $plainLabel
                        }
                    }
                    $webPreviewText = if ($plainLabel) { "$plainLabel`n$href (外部来源)" } else { "$href (外部来源)" }
                    $previewRecords[$refNodeId] = [ordered]@{
                        key = $refNodeId
                        node_id = $refNodeId
                        mode = 'metadata'
                        text = $webPreviewText
                        truncated = $false
                        origin = 'link-registration'
                    }
                }
            } elseif ($isExternalLocal) {
                $safeLabel = if (-not [string]::IsNullOrWhiteSpace($plainLabel)) { $plainLabel } else { '外部来源' }
                $canonicalTarget = "external-local:$safeLabel"
                $refHash = Get-KbSha256Hex -Text $canonicalTarget
                $refNodeId = "ref:$refHash"
                $targetNodeId = $refNodeId

                if (-not $nodes.ContainsKey($refNodeId)) {
                    $nodes[$refNodeId] = [ordered]@{
                        id = $refNodeId
                        kind = 'reference'
                        title = $safeLabel
                        target = [ordered]@{
                            kind = 'display-only'
                            label = $safeLabel
                            reason = 'external-local'
                        }
                        preview_key = $refNodeId
                        page = $null
                        section = $null
                        reference = [ordered]@{
                            medium = 'external-local'
                            source_label = $safeLabel
                        }
                    }
                    $previewRecords[$refNodeId] = [ordered]@{
                        key = $refNodeId
                        node_id = $refNodeId
                        mode = 'metadata'
                        text = "$safeLabel (外部来源)"
                        truncated = $false
                        origin = 'link-registration'
                    }
                }
            } else {
                $pathPart = ($href -split '[?#]', 2)[0]
                $fragPart = if ($href -match '#(?<frag>.*)$') { $Matches['frag'] } else { $null }

                try { $decodedPath = [uri]::UnescapeDataString($pathPart) } catch { $decodedPath = $pathPart }

                if ([string]::IsNullOrWhiteSpace($decodedPath)) {
                    if ($fragPart) {
                        $targetFragment = $fragPart
                        $targetNodeId = $pageNodeId
                        if (-not $pageFragments[$source].Contains($fragPart)) {
                            $diagnostics.Add([ordered]@{
                                code = 'missing_fragment'
                                severity = 'warning'
                                source_path = $source
                                link_ordinal = $ordinal
                                message = "Target fragment '#$fragPart' not found in $source"
                            })
                        }
                    }
                } else {
                    $candidatePath = [IO.Path]::GetFullPath((Join-Path (Split-Path -Parent (Join-Path $root $source)) $decodedPath.Replace('/', [IO.Path]::DirectorySeparatorChar)))
                    $isInside = $candidatePath.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)

                    if ($isInside) {
                        $relTarget = [IO.Path]::GetRelativePath($root, $candidatePath).Replace('\', '/')
                        if ($relTarget.StartsWith('inbox/', [System.StringComparison]::OrdinalIgnoreCase) -or
                            $relTarget.StartsWith('archive/', [System.StringComparison]::OrdinalIgnoreCase)) {
                            # Inbox and archive files are excluded from the knowledge graph.
                            continue
                        }
                        $mdEquivalent = [regex]::Replace($relTarget, '(?i)\.html$', '.md')
                        $resolvedTargetSource = $null

                        if ($pageNodeIds.ContainsKey($relTarget)) {
                            $targetNodeId = $pageNodeIds[$relTarget]
                            $resolvedTargetSource = $relTarget
                        } elseif ($pageNodeIds.ContainsKey($mdEquivalent)) {
                            $targetNodeId = $pageNodeIds[$mdEquivalent]
                            $resolvedTargetSource = $mdEquivalent
                        } elseif (Test-Path -LiteralPath $candidatePath -PathType Leaf) {
                            $canonicalTarget = "attachment:$relTarget"
                            $refHash = Get-KbSha256Hex -Text $canonicalTarget
                            $refNodeId = "ref:$refHash"
                            $targetNodeId = $refNodeId

                            if (-not $nodes.ContainsKey($refNodeId)) {
                                $attTitle = if (-not [string]::IsNullOrWhiteSpace($plainLabel)) { $plainLabel } else { [IO.Path]::GetFileName($relTarget) }
                                $nodes[$refNodeId] = [ordered]@{
                                    id = $refNodeId
                                    kind = 'reference'
                                    title = $attTitle
                                    target = [ordered]@{
                                        kind = 'internal'
                                        path = $relTarget
                                        fragment = $null
                                    }
                                    preview_key = $refNodeId
                                    page = $null
                                    section = $null
                                    reference = [ordered]@{
                                        medium = 'attachment'
                                        source_label = $attTitle
                                    }
                                }
                                $previewRecords[$refNodeId] = [ordered]@{
                                    key = $refNodeId
                                    node_id = $refNodeId
                                    mode = 'metadata'
                                    text = "$attTitle`n$relTarget (附件)"
                                    truncated = $false
                                    origin = 'link-registration'
                                }
                            }
                        } else {
                            $diagnostics.Add([ordered]@{
                                code = 'missing_target'
                                severity = 'warning'
                                source_path = $source
                                link_ordinal = $ordinal
                                message = "Target not found: $pathPart"
                            })
                            continue
                        }

                        if ($null -ne $fragPart) {
                            $targetFragment = $fragPart
                            if ($resolvedTargetSource -and $pageFragments.ContainsKey($resolvedTargetSource) -and -not $pageFragments[$resolvedTargetSource].Contains($fragPart)) {
                                $diagnostics.Add([ordered]@{
                                    code = 'missing_fragment'
                                    severity = 'warning'
                                    source_path = $source
                                    link_ordinal = $ordinal
                                    message = "Target fragment '#$fragPart' not found in $resolvedTargetSource"
                                })
                            }
                        }
                    } else {
                        $safeLabel = if (-not [string]::IsNullOrWhiteSpace($plainLabel)) { $plainLabel } else { '外部来源' }
                        $canonicalTarget = "external-local:$safeLabel"
                        $refHash = Get-KbSha256Hex -Text $canonicalTarget
                        $refNodeId = "ref:$refHash"
                        $targetNodeId = $refNodeId

                        if (-not $nodes.ContainsKey($refNodeId)) {
                            $nodes[$refNodeId] = [ordered]@{
                                id = $refNodeId
                                kind = 'reference'
                                title = $safeLabel
                                target = [ordered]@{
                                    kind = 'display-only'
                                    label = $safeLabel
                                    reason = 'external-local'
                                }
                                preview_key = $refNodeId
                                page = $null
                                section = $null
                                reference = [ordered]@{
                                    medium = 'external-local'
                                    source_label = $safeLabel
                                }
                            }
                            $previewRecords[$refNodeId] = [ordered]@{
                                key = $refNodeId
                                node_id = $refNodeId
                                mode = 'metadata'
                                text = "$safeLabel (外部来源)"
                                truncated = $false
                                origin = 'link-registration'
                            }
                        }
                    }
                }
            }

            if ($null -ne $targetNodeId) {
                $edgeKey = "$pageNodeId->$targetNodeId"
                if (-not $refEdgeOccurrences.ContainsKey($edgeKey)) {
                    $refEdgeOccurrences[$edgeKey] = [System.Collections.Generic.List[object]]::new()
                    $refEdgeOrder[$edgeKey] = $nextRefOrder++
                }
                $occLabel = if ($plainLabel) { $plainLabel } else { $href }
                $refEdgeOccurrences[$edgeKey].Add([ordered]@{
                    owner_page = $pageNodeId
                    source_section = $currentSectionNodeId
                    link_ordinal = $ordinal
                    target_fragment = $targetFragment
                    label = $occLabel
                })
            }
        }

        foreach ($edgeKey in $refEdgeOccurrences.Keys) {
            $parts = $edgeKey -split '->', 2
            $src = $parts[0]
            $tgt = $parts[1]
            $refEdgeId = "edge:references:$src->$tgt"
            $edges[$refEdgeId] = [ordered]@{
                id = $refEdgeId
                kind = 'references'
                source = $src
                target = $tgt
                order = [int]$refEdgeOrder[$edgeKey]
                occurrences = @($refEdgeOccurrences[$edgeKey])
            }
        }
    }

    # -------------------------------------------------------------
    # BFS Shortest Path Depth Calculation from Entrypoint
    # -------------------------------------------------------------
    $bfsDepths = [System.Collections.Generic.Dictionary[string, int]]::new([System.StringComparer]::Ordinal)
    if ($entryId -and $nodes.ContainsKey($entryId)) {
        $bfsDepths[$entryId] = 0
        $bfsQueue = [System.Collections.Generic.Queue[string]]::new()
        $bfsQueue.Enqueue($entryId)

        $bfsChildren = [System.Collections.Generic.Dictionary[string, System.Collections.Generic.HashSet[string]]]::new([System.StringComparer]::Ordinal)
        foreach ($nid in $nodes.Keys) {
            $bfsChildren[$nid] = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
        }

        # 1. contains edges: parent section contains subsection, page contains section
        foreach ($e in $edges.Values) {
            if ($e['kind'] -eq 'contains') {
                $s = [string]$e['source']
                $t = [string]$e['target']
                if ($bfsChildren.ContainsKey($s) -and $nodes.ContainsKey($t)) {
                    $bfsChildren[$s].Add($t) | Out-Null
                }
            }
        }

        # 2. collects edges: collects target page
        foreach ($e in $edges.Values) {
            if ($e['kind'] -eq 'collects') {
                $s = [string]$e['source']
                $t = [string]$e['target']
                if ($bfsChildren.ContainsKey($s) -and $nodes.ContainsKey($t)) {
                    $bfsChildren[$s].Add($t) | Out-Null
                }
            }
        }

        # 3. references edges: links to pages or external references
        foreach ($e in $edges.Values) {
            if ($e['kind'] -eq 'references') {
                $t = [string]$e['target']
                if ($null -ne $e['occurrences'] -and $e['occurrences'].Count -gt 0) {
                    foreach ($occ in $e['occurrences']) {
                        $occSec = [string]$occ['source_section']
                        $parentId = if (-not [string]::IsNullOrWhiteSpace($occSec) -and $nodes.ContainsKey($occSec)) {
                            $occSec
                        } else {
                            [string]$e['source']
                        }
                        if ($bfsChildren.ContainsKey($parentId) -and $nodes.ContainsKey($t)) {
                            $bfsChildren[$parentId].Add($t) | Out-Null
                        }
                    }
                } else {
                    $s = [string]$e['source']
                    if ($bfsChildren.ContainsKey($s) -and $nodes.ContainsKey($t)) {
                        $bfsChildren[$s].Add($t) | Out-Null
                    }
                }
            }
        }

        # Execute BFS
        while ($bfsQueue.Count -gt 0) {
            $curr = $bfsQueue.Dequeue()
            $currDepth = $bfsDepths[$curr]
            if ($bfsChildren.ContainsKey($curr)) {
                foreach ($child in $bfsChildren[$curr]) {
                    if (-not $bfsDepths.ContainsKey($child) -or ($currDepth + 1 -lt $bfsDepths[$child])) {
                        $bfsDepths[$child] = $currDepth + 1
                        $bfsQueue.Enqueue($child)
                    }
                }
            }
        }
    }

    foreach ($n in $nodes.Values) {
        $nid = [string]$n['id']
        if ($bfsDepths.ContainsKey($nid)) {
            $n['depth'] = $bfsDepths[$nid]
        } else {
            $n['depth'] = $null
        }
    }

    $sortedNodes = @($nodes.Values | Sort-Object { $_['id'] })
    $sortedEdges = @($edges.Values | Sort-Object { $_['id'] })
    $sortedDiagnostics = @($diagnostics | Sort-Object { $_['source_path'] }, { [int]$_['link_ordinal'] }, { $_['code'] }, { $_['message'] })
    $sortedPreviewRecords = @($previewRecords.Values | Sort-Object { $_['node_id'] })

    $digestPayload = [ordered]@{
        schema = 'kb-graph'
        schema_version = 1
        entry_id = $entryId
        nodes = $sortedNodes
        edges = $sortedEdges
        diagnostics = $sortedDiagnostics
    }
    $serializedForDigest = $digestPayload | ConvertTo-Json -Depth 10 -Compress
    $graphDigest = Get-KbSha256Hex -Text $serializedForDigest

    $graphData = [ordered]@{
        schema = 'kb-graph'
        schema_version = 1
        graph_digest = $graphDigest
        entry_id = $entryId
        nodes = $sortedNodes
        edges = $sortedEdges
        diagnostics = $sortedDiagnostics
    }

    $previewDigestPayload = [ordered]@{
        schema = 'kb-graph-previews'
        schema_version = 1
        graph_digest = $graphDigest
        records = $sortedPreviewRecords
    }
    $previewSerializedForDigest = $previewDigestPayload | ConvertTo-Json -Depth 10 -Compress
    $previewDigest = Get-KbSha256Hex -Text $previewSerializedForDigest

    $previewData = [ordered]@{
        schema = 'kb-graph-previews'
        schema_version = 1
        preview_digest = $previewDigest
        graph_digest = $graphDigest
        records = $sortedPreviewRecords
    }

    return [pscustomobject]@{
        GraphData = $graphData
        PreviewData = $previewData
        Diagnostics = $sortedDiagnostics
    }
}

function ConvertTo-KbGraphJavaScript {
    param([Parameter(Mandatory)][object]$GraphData)

    $json = $GraphData | ConvertTo-Json -Depth 10
    $safeJson = $json.Replace('<', '\u003c').Replace('>', '\u003e').Replace('&', '\u0026').Replace("`u{2028}", '\u2028').Replace("`u{2029}", '\u2029')
    return "window.__KB_GRAPH_DATA__ = $safeJson;`n"
}

function ConvertTo-KbGraphPreviewsJavaScript {
    param([Parameter(Mandatory)][object]$PreviewData)

    $json = $PreviewData | ConvertTo-Json -Depth 10
    $safeJson = $json.Replace('<', '\u003c').Replace('>', '\u003e').Replace('&', '\u0026').Replace("`u{2028}", '\u2028').Replace("`u{2029}", '\u2029')
    return "window.__KB_GRAPH_PREVIEWS__ = $safeJson;`n"
}
