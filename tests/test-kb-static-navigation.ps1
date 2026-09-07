#Requires -Version 7.0
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$builder = Join-Path $projectRoot 'knowledge-base-manager/scripts/kb-build-static.ps1'
$shell = (Get-Command pwsh -ErrorAction Stop).Source
$tempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\', '/')
$testRoot = [IO.Path]::GetFullPath((Join-Path $tempBase ('kb-navigation-tests-' + [guid]::NewGuid().ToString('N'))))

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw "Assertion failed: $Message" }
}
function Write-Utf8([string]$Path, [string]$Text) {
    New-Item -ItemType Directory -Path (Split-Path -Parent $Path) -Force | Out-Null
    [IO.File]::WriteAllText($Path, $Text, [Text.UTF8Encoding]::new($false))
}
function Invoke-Builder([string]$Root, [string]$Destination) {
    $raw = & $shell -NoProfile -File $builder -Root $Root -Destination $Destination -KatexAssetsRoot $script:assets
    $exitCode = $LASTEXITCODE
    return [pscustomobject]@{ ExitCode = $exitCode; Data = (($raw -join "`n") | ConvertFrom-Json); Raw = ($raw -join "`n") }
}
function Read-Manifest([string]$Destination) {
    return Get-Content -LiteralPath (Join-Path $Destination '.kb-static-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
}
function Read-Html([string]$Destination, [string]$Relative) {
    return Get-Content -LiteralPath (Join-Path $Destination $Relative) -Raw -Encoding UTF8
}
function Nav-Block([string]$Links) {
    return "<!-- kb-nav:children:start -->`n$Links`n<!-- kb-nav:children:end -->"
}
function Write-Kb([string]$Root, [string]$HomeText) {
    Write-Utf8 (Join-Path $Root 'kb.yaml') "schema_version: 1`ncontent_dir: content`nentrypoint: content/首页.md`n"
    Write-Utf8 (Join-Path $Root 'content/首页.md') $HomeText
}
function Assert-Success($Result, [string]$Label) {
    Assert-True ($Result.ExitCode -eq 0 -and $Result.Data.status -eq 'success') "$Label`: $($Result.Raw)"
}

try {
    $assets = Join-Path $testRoot 'assets'
    foreach ($asset in @('katex.min.js', 'katex.min.css', 'contrib/auto-render.min.js', 'fonts/KaTeX_Main-Regular.woff2')) {
        Write-Utf8 (Join-Path $assets $asset) 'disposable fake asset'
    }
    $kb = Join-Path $testRoot 'kb'
    $destination = Join-Path $testRoot 'output'
    $homeText = "# 我的首页`n`n" + (Nav-Block '- [主题](集合/主题.md)')
    Write-Kb $kb $homeText
    $mapText = "---`ntype: map`n---`n# 主题 H1`n`n" + (Nav-Block '- [工程](../项目/工程.md)')
    Write-Utf8 (Join-Path $kb 'content/集合/主题.md') $mapText
    $projectText = "---`ntype: project`n---`n# 工程 H1`n`n" + (Nav-Block @'
- [条目](<../笔记/条目 中文.md>)
- [重复条目](<../笔记/条目 中文.md>)

```markdown
- [不存在](missing.md)
<!-- kb-nav:children:start -->
<!-- kb-nav:children:end -->
```
'@)
    Write-Utf8 (Join-Path $kb 'content/项目/工程.md') $projectText
    $leafPath = Join-Path $kb 'content/笔记/条目 中文.md'
    Write-Utf8 $leafPath "---`ntype: concept`n---`n# 条目 H1`n`n正文 A。`n"
    Write-Utf8 (Join-Path $kb 'content/笔记/孤立.md') "# 未声明归属的笔记`n"
    Write-Utf8 (Join-Path $kb 'content/projects/展示 空格.md') "---`ntype: project`n---`n# 展示项目标题`n"
    Write-Utf8 (Join-Path $kb 'content/knowledge/子目录/知识 空格.md') "---`ntype: concept`n---`n# 知识标题 & 内容`n"
    $first = Invoke-Builder $kb $destination
    Assert-Success $first 'explicit root-map-project-leaf build, without root frontmatter'
    $manifest = Read-Manifest $destination
    Assert-True ($manifest.navigation_digest -match '^[0-9a-f]{64}$') 'manifest stores a navigation digest'
    $digest = $manifest.navigation_digest
    $leafHtml = Read-Html $destination '笔记/条目 中文.html'
    $breadcrumb = [regex]::Match($leafHtml, '(?s)<nav class="kb-breadcrumb".*?</nav>').Value
    Assert-True ($breadcrumb -match '我的首页.*主题 H1.*工程 H1.*条目 H1') 'unique collection ancestry renders the full ordered chain using H1 titles'
    Assert-True ($breadcrumb -match 'href="\.\./(?:%E9%A6%96%E9%A1%B5|首页)\.html"') 'non-index entrypoint is linked as the actual homepage'
    Assert-True ($breadcrumb -notmatch '目录|kb-directory') 'filesystem directories are not collection parents'
    $projectsIndex = Read-Html $destination 'projects/index.html'
    $knowledgeIndex = Read-Html $destination 'knowledge/index.html'
    Assert-True ($projectsIndex -match '全部项目' -and $projectsIndex -match '展示项目标题') 'project auxiliary index uses Chinese label and H1 title'
    Assert-True ($knowledgeIndex -match '全部知识条目' -and $knowledgeIndex -match '知识标题 &amp; 内容') 'knowledge auxiliary index recursively lists encoded H1 text'
    Assert-True ($knowledgeIndex -match 'href="[^"]*%20[^"]*\.html"') 'auxiliary index safely encodes a path containing spaces'
    $indexedLeaf = Read-Html $destination 'knowledge/子目录/知识 空格.html'
    Assert-True ($indexedLeaf -match 'kb-uncollected') 'auxiliary index does not establish collection membership'
    $indexedCrumb = [regex]::Match($indexedLeaf, '(?s)<nav class="kb-breadcrumb".*?</nav>').Value
    Assert-True ($indexedCrumb -notmatch '全部知识条目|子目录') 'auxiliary directory hierarchy is excluded from semantic ancestry'

    $same = Invoke-Builder $kb $destination
    Assert-Success $same 'unchanged rebuild'
    Assert-True ($same.Data.generated -eq 0) 'unchanged navigation and bodies skip all pages'
    Assert-True ((Read-Manifest $destination).navigation_digest -eq $digest) 'navigation digest is deterministic'
    Write-Utf8 $leafPath "---`ntype: concept`n---`n# 条目 H1`n`n正文 B，只有正文变化。`n"
    $bodyOnly = Invoke-Builder $kb $destination
    Assert-Success $bodyOnly 'body-only rebuild'
    Assert-True ($bodyOnly.Data.generated -eq 1) 'body-only change rebuilds exactly its page'
    Assert-True ((Read-Manifest $destination).navigation_digest -eq $digest) 'body changes do not alter navigation digest'

    $renamedMapText = $mapText.Replace('# 主题 H1', '# 新主题标题')
    Write-Utf8 (Join-Path $kb 'content/集合/主题.md') $renamedMapText
    $labelChange = Invoke-Builder $kb $destination
    Assert-Success $labelChange 'navigation title change'
    Assert-True ((Read-Manifest $destination).navigation_digest -ne $digest) 'collection title change invalidates navigation digest'
    Assert-True ($labelChange.Data.generated -gt 1) 'collection title change rebuilds dependent navigation'
    Assert-True ((Read-Html $destination '笔记/条目 中文.html') -match '新主题标题') 'descendant receives changed ancestor label'

    Write-Utf8 (Join-Path $kb 'content/项目/第二工程.md') ("---`ntype: project`n---`n# 第二工程 H1`n" + (Nav-Block '- [条目](<../笔记/条目 中文.md>)'))
    Write-Utf8 (Join-Path $kb 'content/首页.md') ("# 我的首页`n" + (Nav-Block "- [主题](集合/主题.md)`n- [第二工程](项目/第二工程.md)"))
    $multi = Invoke-Builder $kb $destination
    Assert-Success $multi 'multiple collection parents'
    $multiHtml = Read-Html $destination '笔记/条目 中文.html'
    $collections = [regex]::Match($multiHtml, '(?s)<nav class="kb-collections".*?</nav>').Value
    Assert-True ($collections -match '工程 H1' -and $collections -match '第二工程 H1') 'all direct collection parents are exposed'
    Assert-True ([regex]::Matches($collections, '<a\s').Count -eq 2) 'duplicate declared links do not duplicate parent entries'
    $multiCrumb = [regex]::Match($multiHtml, '(?s)<nav class="kb-breadcrumb".*?</nav>').Value
    Assert-True ($multiCrumb -notmatch '新主题标题|工程 H1') 'ambiguous ancestry does not arbitrarily choose a parent chain'
    $orphanHtml = Read-Html $destination '笔记/孤立.html'
    Assert-True ($orphanHtml -match 'kb-uncollected' -and $orphanHtml -match '尚未被项目或主题收录') 'directory membership does not create semantic parentage'

    # Change only collection edges: page paths, types and titles stay identical.
    $beforeEdgeChange = (Read-Manifest $destination).navigation_digest
    Write-Utf8 (Join-Path $kb 'content/项目/工程.md') "---`ntype: project`n---`n# 工程 H1`n"
    $edgeChange = Invoke-Builder $kb $destination
    Assert-Success $edgeChange 'edge-only change'
    Assert-True ((Read-Manifest $destination).navigation_digest -ne $beforeEdgeChange -and $edgeChange.Data.generated -gt 1) 'edge-only edit must invalidate descendant navigation'
    $singleCrumb = [regex]::Match((Read-Html $destination '笔记/条目 中文.html'), '(?s)<nav class="kb-breadcrumb".*?</nav>').Value
    Assert-True ($singleCrumb -match '我的首页.*第二工程 H1.*条目 H1') 'removing an alternate edge restores the unique remaining ancestry'

    $beforeRename = (Read-Manifest $destination).navigation_digest
    $renamedLeaf = Join-Path $kb 'content/笔记/重命名 中文.md'
    Move-Item -LiteralPath $leafPath -Destination $renamedLeaf
    Write-Utf8 (Join-Path $kb 'content/项目/工程.md') $projectText.Replace('条目 中文.md', '重命名 中文.md')
    Write-Utf8 (Join-Path $kb 'content/项目/第二工程.md') ("---`ntype: project`n---`n# 第二工程 H1`n" + (Nav-Block '- [条目](<../笔记/重命名 中文.md>)'))
    $rename = Invoke-Builder $kb $destination
    Assert-Success $rename 'renamed child with updated edges'
    Assert-True ((Read-Manifest $destination).navigation_digest -ne $beforeRename) 'renamed child updates navigation digest'
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $destination '笔记/条目 中文.html'))) 'renamed source removes obsolete generated page'
    Assert-True (Test-Path -LiteralPath (Join-Path $destination '笔记/重命名 中文.html')) 'renamed source generates new page'

    $beforeDelete = (Read-Manifest $destination).navigation_digest
    Remove-Item -LiteralPath $renamedLeaf
    Write-Utf8 (Join-Path $kb 'content/项目/工程.md') "---`ntype: project`n---`n# 工程 H1`n"
    Write-Utf8 (Join-Path $kb 'content/项目/第二工程.md') "---`ntype: project`n---`n# 第二工程 H1`n"
    $delete = Invoke-Builder $kb $destination
    Assert-Success $delete 'deleted child with removed edges'
    Assert-True ((Read-Manifest $destination).navigation_digest -ne $beforeDelete) 'deleted child changes navigation digest'
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $destination '笔记/重命名 中文.html'))) 'deleted source removes its generated page'

    $oldManifest = Read-Manifest $destination
    $oldManifest.PSObject.Properties.Remove('navigation_digest')
    Write-Utf8 (Join-Path $destination '.kb-static-manifest.json') ($oldManifest | ConvertTo-Json -Depth 50)
    $upgrade = Invoke-Builder $kb $destination
    Assert-Success $upgrade 'pre-navigation manifest upgrade'
    Assert-True ($upgrade.Data.generated -gt 1) 'missing old navigation digest triggers rebuild'
    Assert-True ((Read-Manifest $destination).navigation_digest -match '^[0-9a-f]{64}$') 'upgrade restores navigation digest'

    $legacyKb = Join-Path $testRoot 'legacy'
    $legacyDestination = Join-Path $testRoot 'legacy-output'
    Write-Kb $legacyKb "# 旧首页`n- [普通链接](leaf.md)`n"
    Write-Utf8 (Join-Path $legacyKb 'content/leaf.md') "# 旧条目`n"
    $legacy = Invoke-Builder $legacyKb $legacyDestination
    Assert-Success $legacy 'legacy knowledge base without declarations'
    Assert-True ((Read-Html $legacyDestination 'leaf.html') -match 'kb-uncollected') 'ordinary links do not silently establish collection ownership'

    # Each invalid graph gets a new destination; validation must precede any write.
    $cases = @(
        @{ Name = 'self'; Home = '# 首页' + "`n" + (Nav-Block '- [自己](首页.md)') },
        @{ Name = 'missing'; Home = '# 首页' + "`n" + (Nav-Block '- [缺失](missing.md)') },
        @{ Name = 'external'; Home = '# 首页' + "`n" + (Nav-Block '- [外部](https://example.com/x.md)') },
        @{ Name = 'outside'; Home = '# 首页' + "`n" + (Nav-Block '- [越界](../outside.md)') },
        @{ Name = 'unclosed'; Home = "# 首页`n<!-- kb-nav:children:start -->`n- [页](leaf.md)" },
        @{ Name = 'cycle'; Home = '# 首页' + "`n" + (Nav-Block '- [映射](leaf.md)'); Leaf = "---`ntype: map`n---`n# 映射`n" + (Nav-Block '- [首页](首页.md)') },
        @{ Name = 'leaf-declaration'; Home = '# 首页'; Leaf = "---`ntype: concept`n---`n# 普通条目`n" + (Nav-Block '- [首页](首页.md)') }
    )
    foreach ($case in $cases) {
        $badKb = Join-Path $testRoot ('bad-' + $case.Name)
        $badDestination = Join-Path $testRoot ('bad-output-' + $case.Name)
        Write-Kb $badKb $case.Home
        $leafText = if ($case.ContainsKey('Leaf')) { $case.Leaf } else { '# Leaf' }
        Write-Utf8 (Join-Path $badKb 'content/leaf.md') $leafText
        Write-Utf8 (Join-Path $badKb 'outside.md') '# Exists outside content'
        $bad = Invoke-Builder $badKb $badDestination
        Assert-True ($bad.ExitCode -ne 0) "$($case.Name) must block: $($bad.Raw)"
        Assert-True (-not (Test-Path -LiteralPath $badDestination)) "$($case.Name) must fail before creating destination"
    }
    Write-Output 'PASS: explicit static navigation integration'
}
finally {
    # This exact generated absolute directory is the only recursive-delete target.
    Assert-True ([IO.Path]::IsPathFullyQualified($testRoot) -and
        $testRoot.StartsWith($tempBase + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase) -and
        (Split-Path -Leaf $testRoot) -match '^kb-navigation-tests-[0-9a-f]{32}$') 'cleanup target stays inside the temporary directory'
    if (Test-Path -LiteralPath $testRoot) { Remove-Item -LiteralPath $testRoot -Recurse -Force }
}
