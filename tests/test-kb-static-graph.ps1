#Requires -Version 7.0
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$graphScript = Join-Path $projectRoot 'knowledge-base-manager/scripts/kb-static-graph.ps1'
$navScript = Join-Path $projectRoot 'knowledge-base-manager/scripts/kb-static-navigation.ps1'

. $navScript
. $graphScript

$tempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\', '/')
$testRoot = [IO.Path]::GetFullPath((Join-Path $tempBase ('kb-graph-tests-' + [guid]::NewGuid().ToString('N'))))

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw "Assertion failed: $Message" }
}

function Assert-Equal($Actual, $Expected, [string]$Message) {
    if ($Actual -ne $Expected) { throw "Assertion failed: $Message. Expected: '$Expected', Actual: '$Actual'" }
}

function Write-Utf8([string]$Path, [string]$Text) {
    New-Item -ItemType Directory -Path (Split-Path -Parent $Path) -Force | Out-Null
    [IO.File]::WriteAllText($Path, $Text, [Text.UTF8Encoding]::new($false))
}

try {
    # -------------------------------------------------------------
    # 1. Unit Test: Heading Anchor Unification (Update-KbHeadingAnchors)
    # -------------------------------------------------------------
    $htmlSample = @'
<div id="kb-heading-1">Existing collision div</div>
<h1>Page H1</h1>
<p>Intro paragraph.</p>
<h2>Section Alpha</h2>
<p>Alpha content.</p>
<pre><code><h2>Code heading ignored</h2></code></pre>
<h5>Deep Level 5</h5>
<p>Deep content.</p>
<h3>Sub Alpha 1</h3>
<p>Sub content.</p>
<h2 id="explicit-id">Explicit Section</h2>
<p>Explicit content.</p>
<h2 id="dup-id">Duplicate Heading 1</h2>
<h3 id="dup-id">Duplicate Heading 2</h3>
'@

    $anchorResult = Update-KbHeadingAnchors -Html $htmlSample -OwnerPageId "page:id:p1" -SourcePath "test.md"
    Assert-True ($null -ne $anchorResult.Html) "HTML returned"
    Assert-True ($anchorResult.Sections.Count -eq 6) "Extracted 6 outline sections (ignored code block)"

    # h2-h4 allocated before h5-h6:
    # kb-heading-1 was taken by div.
    # Section Alpha (h2) gets kb-heading-2
    # Sub Alpha 1 (h3) gets kb-heading-3
    # Deep Level 5 (h5) gets kb-heading-4
    $secAlpha = $anchorResult.Sections | Where-Object { $_.Title -eq 'Section Alpha' }
    $subAlpha = $anchorResult.Sections | Where-Object { $_.Title -eq 'Sub Alpha 1' }
    $deepLvl5 = $anchorResult.Sections | Where-Object { $_.Title -eq 'Deep Level 5' }
    $explicitSec = $anchorResult.Sections | Where-Object { $_.Title -eq 'Explicit Section' }

    Assert-Equal $secAlpha.Fragment "kb-heading-2" "Section Alpha gets kb-heading-2 (skipping existing kb-heading-1)"
    Assert-Equal $subAlpha.Fragment "kb-heading-3" "Sub Alpha 1 (h3) gets kb-heading-3 before h5"
    Assert-Equal $deepLvl5.Fragment "kb-heading-4" "Deep Level 5 (h5) gets kb-heading-4 after h2-h4"
    Assert-Equal $explicitSec.Fragment "explicit-id" "Explicit id is preserved"

    # Hierarchy: Section Alpha parent is page; Sub Alpha 1 parent is Section Alpha; Deep Level 5 parent is Section Alpha
    Assert-Equal $secAlpha.ParentNodeId "page:id:p1" "Section Alpha parent is page"
    Assert-Equal $deepLvl5.ParentNodeId $secAlpha.NodeId "Deep Level 5 parent is Section Alpha"
    Assert-Equal $subAlpha.ParentNodeId $secAlpha.NodeId "Sub Alpha 1 parent is Section Alpha (popped h5)"
    Assert-Equal $explicitSec.ParentNodeId "page:id:p1" "Explicit Section parent is page"

    # Duplicate explicit id diagnostic
    $dupDiag = @($anchorResult.Diagnostics | Where-Object { $_.code -eq 'duplicate_heading_id' })
    Assert-True ($dupDiag.Count -eq 1) "Duplicate explicit heading id detected and warned"

    # Code block heading was untouched
    Assert-True ($anchorResult.Html -match '<code><h2>Code heading ignored</h2></code>') "Code heading remains unchanged"

    # -------------------------------------------------------------
    # 2. Unit Test: Frontmatter parsing (Get-KbPageFrontmatter)
    # -------------------------------------------------------------
    $fmSample = @"
---
id: kb-20260910-abcd
type: concept
status: draft
tags:
  - math
  - logic
---
# Title
"@
    $fm = Get-KbPageFrontmatter -Text $fmSample
    Assert-Equal $fm.id "kb-20260910-abcd" "Parsed frontmatter id"
    Assert-Equal $fm.type "concept" "Parsed frontmatter type"
    Assert-Equal $fm.status "draft" "Parsed frontmatter status"
    Assert-True ($fm.tags.Count -eq 2 -and $fm.tags[0] -eq 'math' -and $fm.tags[1] -eq 'logic') "Parsed block tags"

    $fmInline = @"
---
id: "kb-inline"
type: 'map'
status: STABLE
tags: [tagA, "tagB"]
---
"@
    $fm2 = Get-KbPageFrontmatter -Text $fmInline
    Assert-Equal $fm2.id "kb-inline" "Parsed quoted id"
    Assert-Equal $fm2.type "map" "Parsed lowercase type"
    Assert-Equal $fm2.status "stable" "Parsed lowercase status"
    Assert-True ($fm2.tags.Count -eq 2 -and $fm2.tags[0] -eq 'tagA' -and $fm2.tags[1] -eq 'tagB') "Parsed inline tags"

    # -------------------------------------------------------------
    # 3. Unit Test: Excerpt extraction (Get-KbTextExcerpt)
    # -------------------------------------------------------------
    $excerptHtml = @'
<script>var x = 1;</script>
<style>.body { color: red; }</style>
<!-- kb-nav:children:start -->
<p>Nav child paragraph ignored</p>
<!-- kb-nav:children:end -->
<pre><code><p>Code paragraph ignored</p></code></pre>
<p>Hello <b>World</b> &amp; Antigravity assistant! This is a <i>clean</i> paragraph.</p>
<p>Second paragraph ignored.</p>
'@
    $exc = Get-KbTextExcerpt -Html $excerptHtml -MaxLength 600
    Assert-Equal $exc.Mode "excerpt" "Mode is excerpt"
    Assert-Equal $exc.Text "Hello World & Antigravity assistant! This is a clean paragraph." "Clean plain text with tags stripped and entities decoded"
    Assert-Equal $exc.Truncated $false "Not truncated"

    # Long text truncation test
    $longP = "<p>" + ("A" * 700) + "</p>"
    $excLong = Get-KbTextExcerpt -Html $longP -MaxLength 600
    Assert-Equal $excLong.Mode "excerpt" "Mode is excerpt"
    Assert-Equal $excLong.Text.Length 600 "Truncated exactly to 600 chars"
    Assert-Equal $excLong.Truncated $true "Truncated flag is true"

    # Unavailable fallback test
    $emptyHtml = "<h1>Only Title</h1><pre><code>Code only</code></pre>"
    $excEmpty = Get-KbTextExcerpt -Html $emptyHtml
    Assert-Equal $excEmpty.Mode "unavailable" "Mode is unavailable when no paragraph"
    Assert-Equal $excEmpty.Text "" "Empty text"

    # -------------------------------------------------------------
    # 4. Integration Test: Full Graph Extraction (Get-KbGraphModel)
    # -------------------------------------------------------------
    $kb = Join-Path $testRoot 'kb'
    $content = Join-Path $kb 'content'

    Write-Utf8 (Join-Path $kb 'kb.yaml') "schema_version: 1`ncontent_dir: content`nentrypoint: content/index.md`n"

    # index.md: Entrypoint, no formal id
    Write-Utf8 (Join-Path $content 'index.md') @'
# 知识库主页

欢迎来到知识库。

<!-- kb-nav:children:start -->
- [项目 Alpha](projects/alpha.md)
- [概览地图](maps/overview.md)
<!-- kb-nav:children:end -->
'@

    # projects/alpha.md: formal id, sections, links, external references
    Write-Utf8 (Join-Path $content 'projects/alpha.md') @'
---
id: kb-20260910-0001
type: project
status: stable
tags:
  - core
---
# 项目 Alpha

这是项目 Alpha 的主说明。

## 架构规划

在架构方面，请参考 [概览地图](<../maps/overview.md#sec-deep>) 的深度分析。

### 详细实现

此处引用了核心概念：[核心概念](../knowledge/concept.md)。
另可参考规范：[在线标准](https://example.com/spec?v=1#intro)。

## 资源清单

- 本地源码：[Local Project](file:///C:/projects/myrepo) <!-- kb-external-local -->
- 规格说明书：[Attachment Spec](../assets/spec.pdf)
- 概念再读：[再读核心概念](../knowledge/concept.md#sub-concept)
- 自引用章节：[查看架构规划](#kb-heading-1)
'@

    # maps/overview.md: formal id, cyclic link to alpha
    Write-Utf8 (Join-Path $content 'maps/overview.md') @'
---
id: kb-20260910-0002
type: map
status: draft
---
# 概览地图

知识库全景地图。

## 模块总览

此模块与 [项目 Alpha](../projects/alpha.md) 紧密相连。

<h4 id="sec-deep">深度切面</h4>

这是深度切面正文。
'@

    # knowledge/concept.md: formal id, sub-concept section
    Write-Utf8 (Join-Path $content 'knowledge/concept.md') @'
---
id: kb-20260910-0003
type: concept
status: stable
---
# 核心概念

核心概念定义。

## 概念详解

这是概念正文。

### 子概念说明

这是子概念详情。
'@

    # Attachment asset file
    Write-Utf8 (Join-Path $content 'assets/spec.pdf') 'disposable pdf binary content'

    # broken.md: contains broken links and duplicate heading
    Write-Utf8 (Join-Path $content 'broken.md') @'
# 诊断测试页

<h2 id="dup-heading">标题一</h2>
<h3 id="dup-heading">标题二</h3>

- [不存在的文件](missing-file.md)
- [不存在的锚点](maps/overview.md#non-existent-frag)
'@

    $mdFiles = @(Get-ChildItem -LiteralPath $content -Recurse -File -Filter "*.md" | Sort-Object FullName)
    $entrypointFull = Join-Path $content 'index.md'

    $navModel = Get-KbStaticNavigationModel -MarkdownFiles $mdFiles -ContentRoot $content -EntrySourcePath $entrypointFull
    Assert-True ($null -ne $navModel) "Navigation model loaded"

    $graphResult = Get-KbGraphModel -ContentRoot $content -Navigation $navModel -MarkdownFiles $mdFiles
    Assert-True ($null -ne $graphResult.GraphData) "GraphData generated"
    Assert-True ($null -ne $graphResult.PreviewData) "PreviewData generated"

    $gd = $graphResult.GraphData
    $pd = $graphResult.PreviewData

    # Verify schema & version
    Assert-Equal $gd.schema "kb-graph" "Graph schema is kb-graph"
    Assert-Equal $gd.schema_version 1 "Graph schema_version is 1"
    Assert-Equal $pd.schema "kb-graph-previews" "Preview schema is kb-graph-previews"
    Assert-Equal $pd.schema_version 1 "Preview schema_version is 1"

    # Verify Entry ID
    Assert-Equal $gd.entry_id "page:path:index.md" "Entrypoint without formal id gets page:path:index.md"

    # Verify Nodes
    $nodeMap = @{}
    foreach ($n in $gd.nodes) { $nodeMap[$n.id] = $n }

    Assert-True ($nodeMap.ContainsKey("page:path:index.md")) "Index page node exists"
    Assert-True ($nodeMap.ContainsKey("page:id:kb-20260910-0001")) "Alpha page node exists by formal id"
    Assert-True ($nodeMap.ContainsKey("page:id:kb-20260910-0002")) "Overview map node exists by formal id"
    Assert-True ($nodeMap.ContainsKey("page:id:kb-20260910-0003")) "Concept node exists by formal id"
    Assert-True ($nodeMap.ContainsKey("page:path:broken.md")) "Broken page node exists"

    $alphaNode = $nodeMap["page:id:kb-20260910-0001"]
    Assert-Equal $alphaNode.kind "page" "Alpha node kind is page"
    Assert-Equal $alphaNode.title "项目 Alpha" "Alpha page title extracted from H1"
    Assert-Equal $alphaNode.target.kind "internal" "Alpha target kind is internal"
    Assert-Equal $alphaNode.target.path "projects/alpha.html" "Alpha target output path is projects/alpha.html"
    Assert-Equal $alphaNode.page.kb_id "kb-20260910-0001" "Alpha page kb_id stored"
    Assert-Equal $alphaNode.page.type "project" "Alpha page type stored"
    Assert-Equal $alphaNode.page.status "stable" "Alpha page status stored"
    Assert-True ($alphaNode.page.tags -contains 'core') "Alpha page tags stored"

    # Verify Section Nodes
    $deepSec = $nodeMap["section:page:id:kb-20260910-0002#sec-deep"]
    Assert-True ($null -ne $deepSec) "Overview deep section node exists"
    Assert-Equal $deepSec.kind "section" "Section kind is section"
    Assert-Equal $deepSec.title "深度切面" "Section title is plain text"
    Assert-Equal $deepSec.section.owner_page "page:id:kb-20260910-0002" "Section owner page correct"
    Assert-Equal $deepSec.section.heading_level 4 "Section heading level is 4"

    # Verify Collects Edges
    $edgeMap = @{}
    foreach ($e in $gd.edges) { $edgeMap[$e.id] = $e }

    $c1 = $edgeMap["edge:collects:page:path:index.md->page:id:kb-20260910-0001"]
    $c2 = $edgeMap["edge:collects:page:path:index.md->page:id:kb-20260910-0002"]
    Assert-True ($null -ne $c1 -and $null -ne $c2) "Collects edges exist from index to alpha and overview"
    Assert-Equal $c1.order 0 "Index -> Alpha is order 0"
    Assert-Equal $c2.order 1 "Index -> Overview is order 1 (preserving children block order)"

    # Verify Contains Edges
    $containsAlpha = @($gd.edges | Where-Object { $_.kind -eq 'contains' -and $_.source -eq 'page:id:kb-20260910-0001' })
    Assert-True ($containsAlpha.Count -ge 2) "Alpha page contains top-level sections"

    # Verify References Edges & Occurrences Aggregation
    # alpha -> concept has 2 links in alpha.md:
    # link 1: ../knowledge/concept.md (in section '详细实现')
    # link 2: ../knowledge/concept.md#sub-concept (in section '资源清单')
    $refConcept = $edgeMap["edge:references:page:id:kb-20260910-0001->page:id:kb-20260910-0003"]
    Assert-True ($null -ne $refConcept) "Alpha -> Concept references edge exists"
    Assert-Equal $refConcept.kind "references" "Kind is references"
    Assert-Equal $refConcept.occurrences.Count 2 "2 occurrences aggregated into single edge"
    Assert-Equal $refConcept.occurrences[0].label "核心概念" "Occurrence 1 label"
    Assert-Equal $refConcept.occurrences[1].label "再读核心概念" "Occurrence 2 label"
    Assert-Equal $refConcept.occurrences[1].target_fragment "sub-concept" "Occurrence 2 preserves target_fragment"
    Assert-True ($refConcept.occurrences[0].source_section -match 'section:page:id:kb-20260910-0001#') "Occurrence 1 records source_section"
    Assert-True ($refConcept.occurrences[1].source_section -match 'section:page:id:kb-20260910-0001#') "Occurrence 2 records source_section"

    # Cyclic reference: alpha -> overview AND overview -> alpha
    $refAlphaToOverview = $edgeMap["edge:references:page:id:kb-20260910-0001->page:id:kb-20260910-0002"]
    $refOverviewToAlpha = $edgeMap["edge:references:page:id:kb-20260910-0002->page:id:kb-20260910-0001"]
    Assert-True ($null -ne $refAlphaToOverview) "Alpha -> Overview references edge exists"
    Assert-True ($null -ne $refOverviewToAlpha) "Overview -> Alpha references edge exists (cyclic link supported)"

    # Self-reference: alpha -> alpha
    $refSelf = $edgeMap["edge:references:page:id:kb-20260910-0001->page:id:kb-20260910-0001"]
    Assert-True ($null -ne $refSelf) "Self-reference edge exists"
    Assert-Equal $refSelf.occurrences[0].target_fragment "kb-heading-1" "Self-reference target_fragment preserved"

    # Web reference
    $webRefEdges = @($gd.edges | Where-Object { $_.source -eq 'page:id:kb-20260910-0001' -and $_.target -match '^ref:' })
    Assert-True ($webRefEdges.Count -ge 3) "Alpha has web, attachment, and external-local reference edges"

    # External local reference: display-only, no absolute machine path
    $extLocalNode = $gd.nodes | Where-Object { $_.reference -and $_.reference.medium -eq 'external-local' }
    Assert-True ($null -ne $extLocalNode) "External local reference node exists"
    Assert-Equal $extLocalNode.target.kind "display-only" "External local target is display-only"
    Assert-Equal $extLocalNode.target.reason "external-local" "Target reason is external-local"
    Assert-True ($extLocalNode.target.PSObject.Properties['url'] -eq $null) "No raw file:/// URL exposed in display-only target"

    # Attachment reference
    $attNode = $gd.nodes | Where-Object { $_.reference -and $_.reference.medium -eq 'attachment' }
    Assert-True ($null -ne $attNode) "Attachment reference node exists"
    Assert-Equal $attNode.target.kind "internal" "Attachment target is internal"
    Assert-Equal $attNode.target.path "assets/spec.pdf" "Attachment relative path stored"

    # Diagnostics Verification
    $missingTargetDiag = @($gd.diagnostics | Where-Object { $_.code -eq 'missing_target' })
    Assert-True ($missingTargetDiag.Count -ge 1) "missing_target diagnostic logged for missing-file.md"
    Assert-True ($missingTargetDiag[0].message -match 'missing-file\.md') "missing_target message identifies file"

    $missingFragDiag = @($gd.diagnostics | Where-Object { $_.code -eq 'missing_fragment' })
    Assert-True ($missingFragDiag.Count -ge 1) "missing_fragment diagnostic logged for non-existent-frag"

    $dupHeadingDiag = @($gd.diagnostics | Where-Object { $_.code -eq 'duplicate_heading_id' })
    Assert-True ($dupHeadingDiag.Count -ge 1) "duplicate_heading_id diagnostic logged for broken.md"

    # Digest Matching
    Assert-True ($gd.graph_digest -match '^[0-9a-f]{64}$') "graph_digest is 64 hex characters"
    Assert-True ($pd.preview_digest -match '^[0-9a-f]{64}$') "preview_digest is 64 hex characters"
    Assert-Equal $pd.graph_digest $gd.graph_digest "PreviewData graph_digest matches GraphData graph_digest"

    # -------------------------------------------------------------
    # 5. Determinism & Independent Digest Test
    # -------------------------------------------------------------
    # Run second time on same KB -> digests must be 100% identical
    $graphResult2 = Get-KbGraphModel -ContentRoot $content -Navigation $navModel -MarkdownFiles $mdFiles
    Assert-Equal $graphResult2.GraphData.graph_digest $gd.graph_digest "graph_digest is deterministic across runs"
    Assert-Equal $graphResult2.PreviewData.preview_digest $pd.preview_digest "preview_digest is deterministic across runs"

    # Now modify ONLY body paragraph text of concept.md (no headings or links changed)
    $modifiedConcept = @'
---
id: kb-20260910-0003
type: concept
status: stable
---
# 核心概念

核心概念定义已经被更新了，这里有全新的一段正文内容！

## 概念详解

这是概念正文修改版。

### 子概念说明

这是子概念详情。
'@
    Write-Utf8 (Join-Path $content 'knowledge/concept.md') $modifiedConcept
    $mdFilesUpdated = @(Get-ChildItem -LiteralPath $content -Recurse -File -Filter "*.md" | Sort-Object FullName)
    $graphResult3 = Get-KbGraphModel -ContentRoot $content -Navigation $navModel -MarkdownFiles $mdFilesUpdated

    Assert-Equal $graphResult3.GraphData.graph_digest $gd.graph_digest "graph_digest UNCHANGED when only body text excerpt changes!"
    Assert-True ($graphResult3.PreviewData.preview_digest -ne $pd.preview_digest) "preview_digest UPDATED when body text excerpt changes!"

    # -------------------------------------------------------------
    # 6. Blocker Test: Duplicate formal id
    # -------------------------------------------------------------
    Write-Utf8 (Join-Path $content 'duplicate-id.md') @'
---
id: kb-20260910-0001
---
# 冲突页面
'@
    $mdFilesWithDup = @(Get-ChildItem -LiteralPath $content -Recurse -File -Filter "*.md" | Sort-Object FullName)
    $duplicateBlocked = $false
    try {
        Get-KbGraphModel -ContentRoot $content -Navigation $navModel -MarkdownFiles $mdFilesWithDup | Out-Null
    } catch {
        if ($_.Exception.Message -match 'BLOCKER: duplicate formal id') {
            $duplicateBlocked = $true
        }
    }
    Assert-True $duplicateBlocked "Duplicate formal id throws BLOCKER exception"

    # Remove duplicate file
    Remove-Item -LiteralPath (Join-Path $content 'duplicate-id.md') -Force

    # -------------------------------------------------------------
    # 7. JavaScript Serialization & XSS Safety Test
    # -------------------------------------------------------------
    $xssGraph = [ordered]@{
        schema = 'kb-graph'
        title = '<script>alert("xss")</script>'
        content = '<img src=x onerror=alert(1)> & "quotes"'
        tags = @('<b>bold</b>')
    }
    $jsData = ConvertTo-KbGraphJavaScript -GraphData $xssGraph
    Assert-True ($jsData.StartsWith('window.__KB_GRAPH_DATA__ = ')) "JS prefix present"
    Assert-True ($jsData.TrimEnd().EndsWith(';')) "JS semicolon present"
    Assert-True ($jsData -notmatch '<script') "Raw <script tag is escaped"
    Assert-True ($jsData -notmatch '<img') "Raw <img tag is escaped"
    Assert-True ($jsData -match '\\u003cscript\\u003e') "\u003c escape used for <"
    Assert-True ($jsData -match '\\u0026') "\u0026 escape used for &"

    $xssPreview = [ordered]@{
        schema = 'kb-graph-previews'
        records = @(
            [ordered]@{
                text = '</script><script>eval()</script>'
            }
        )
    }
    $jsPreview = ConvertTo-KbGraphPreviewsJavaScript -PreviewData $xssPreview
    Assert-True ($jsPreview.StartsWith('window.__KB_GRAPH_PREVIEWS__ = ')) "Preview JS prefix present"
    Assert-True ($jsPreview -notmatch '</script>') "Raw </script> tag is escaped in preview JS"

    # -------------------------------------------------------------
    # 8. Inbox and Archive Exclusion Test
    # -------------------------------------------------------------
    Write-Utf8 (Join-Path $content 'inbox/draft-note.md') @'
# 暂存草稿笔记

这是收件箱中的草稿笔记，不应该作为图谱节点出现。
'@
    Write-Utf8 (Join-Path $content 'archive/historical.md') @'
---
id: kb-20260910-9999
type: concept
status: deprecated
---
# 历史归档条目

这是已归档的条目，不应该作为图谱节点出现。
'@
    $origIndex = [IO.File]::ReadAllText((Join-Path $content 'index.md'))
    $indexWithInboxLink = $origIndex + "`n`n## 待整理笔记`n`n- [草稿笔记](inbox/draft-note.md)`n"
    Write-Utf8 (Join-Path $content 'index.md') $indexWithInboxLink

    $mdFilesWithInbox = @(Get-ChildItem -LiteralPath $content -Recurse -File -Filter "*.md" | Sort-Object FullName)
    $graphResultWithInbox = Get-KbGraphModel -ContentRoot $content -Navigation $navModel -MarkdownFiles $mdFilesWithInbox

    $gdInbox = $graphResultWithInbox.GraphData
    $inboxNodes = @($gdInbox.nodes | Where-Object {
        $nid = [string]$_['id']
        if ($nid -match '(?i)inbox|archive') { return $true }
        if ($_.Contains('page') -and $null -ne $_['page'] -and $_['page'].Contains('source_path')) {
            $sp = [string]$_['page']['source_path']
            if ($sp -match '(?i)^inbox/|^archive/') { return $true }
        }
        if ($_.Contains('target') -and $null -ne $_['target'] -and $_['target'].Contains('path')) {
            $tp = [string]$_['target']['path']
            if ($tp -match '(?i)^inbox/|^archive/') { return $true }
        }
        return $false
    })
    Assert-True ($inboxNodes.Count -eq 0) "No graph nodes generated for inbox/ or archive/ files"

    $inboxEdges = @($gdInbox.edges | Where-Object {
        $s = [string]$_['source']
        $t = [string]$_['target']
        $s -match '(?i)inbox|archive' -or $t -match '(?i)inbox|archive'
    })
    Assert-True ($inboxEdges.Count -eq 0) "No graph edges reference inbox/ or archive/ files"

    $uncollectedSectionNodes = @($gdInbox.nodes | Where-Object {
        $_.kind -eq 'section' -and $_.title -match '(?i)待整理|inbox|导览'
    })
    Assert-True ($uncollectedSectionNodes.Count -eq 0) "No section nodes generated for uncollected notes or entrypoint sections"

    $indexSectionNodes = @($gdInbox.nodes | Where-Object {
        $_.kind -eq 'section' -and $_.section.owner_page -eq 'page:path:index.md'
    })
    Assert-True ($indexSectionNodes.Count -eq 0) "No section nodes generated for entrypoint page"

    Write-Utf8 (Join-Path $content 'index.md') $origIndex
    Remove-Item -LiteralPath (Join-Path $content 'inbox/draft-note.md') -Force
    Remove-Item -LiteralPath (Join-Path $content 'archive/historical.md') -Force

    # -------------------------------------------------------------
    # 9. Nested List in Collection Block Test
    # -------------------------------------------------------------
    $nestedIndex = @"
# 知识库主页

欢迎来到知识库。

<!-- kb-nav:children:start -->
- [概览地图](maps/overview.md)
  - [项目 Alpha](projects/alpha.md)
<!-- kb-nav:children:end -->
"@
    Write-Utf8 (Join-Path $content 'index.md') $nestedIndex
    $mdFilesNested = @(Get-ChildItem -LiteralPath $content -Recurse -File -Filter "*.md" | Sort-Object FullName)
    $navModelNested = Get-KbStaticNavigationModel -MarkdownFiles $mdFilesNested -ContentRoot $content -EntrySourcePath $entrypointFull
    $graphResultNested = Get-KbGraphModel -ContentRoot $content -Navigation $navModelNested -MarkdownFiles $mdFilesNested
    $gdNested = $graphResultNested.GraphData
    $edgeMapNested = @{}
    foreach ($e in $gdNested.edges) { $edgeMapNested[$e.id] = $e }

    Assert-True ($edgeMapNested.ContainsKey("edge:collects:page:path:index.md->page:id:kb-20260910-0002")) "Index -> Overview collects edge exists"
    Assert-True (-not $edgeMapNested.ContainsKey("edge:collects:page:path:index.md->page:id:kb-20260910-0001")) "Indented Project Alpha under Overview is NOT collected directly by Index"

    Write-Utf8 (Join-Path $content 'index.md') $origIndex

    Write-Output "PASS: all kb-static-graph unit and integration tests passed successfully"
}
finally {
    if (Test-Path -LiteralPath $testRoot) {
        Remove-Item -LiteralPath $testRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
