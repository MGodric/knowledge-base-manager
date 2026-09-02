#Requires -Version 7.0
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$builder = Join-Path $projectRoot 'knowledge-base-manager\scripts\kb-build-static.ps1'
$shell = (Get-Command pwsh -ErrorAction Stop).Source
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('kb-static-tests-' + [guid]::NewGuid().ToString('N'))

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw "Assertion failed: $Message" }
}

function Write-Utf8 {
    param([string]$Path, [string]$Text)
    New-Item -ItemType Directory -Path (Split-Path -Parent $Path) -Force | Out-Null
    [IO.File]::WriteAllText($Path, $Text, [Text.UTF8Encoding]::new($false))
}

function New-FakeKatexAssets {
    param([string]$Root)
    Write-Utf8 (Join-Path $Root 'katex.min.js') 'fake katex javascript'
    Write-Utf8 (Join-Path $Root 'katex.min.css') 'fake katex stylesheet'
    Write-Utf8 (Join-Path $Root 'contrib\auto-render.min.js') 'fake auto render javascript'
    Write-Utf8 (Join-Path $Root 'fonts\KaTeX_Main-Regular.woff2') 'fake font'
}

function Invoke-Builder {
    param(
        [string]$Root,
        [string]$Destination,
        [string]$KatexAssets,
        [string]$Builder = $script:builder,
        [switch]$Force
    )
    $arguments = @('-NoProfile', '-File', $Builder, '-Root', $Root, '-Destination', $Destination)
    if (-not [string]::IsNullOrWhiteSpace($KatexAssets)) { $arguments += @('-KatexAssetsRoot', $KatexAssets) }
    if ($Force.IsPresent) { $arguments += '-Force' }
    $raw = & $shell @arguments
    return [pscustomobject]@{ ExitCode = $LASTEXITCODE; Data = (($raw -join "`n") | ConvertFrom-Json); Raw = $raw }
}

try {
    Assert-True ($PSVersionTable.PSVersion.Major -ge 7) 'static build tests require PowerShell 7+'
    Assert-True ((Get-Content -LiteralPath $builder -TotalCount 1 -Encoding UTF8) -eq '#Requires -Version 7.0') 'builder must require PowerShell 7+'

    $kb = Join-Path $testRoot '知识库 空格'
    $destination = Join-Path $testRoot '静态 页面 空格'
    $katexAssets = Join-Path $testRoot 'fake katex assets'
    New-FakeKatexAssets -Root $katexAssets
    Write-Utf8 (Join-Path $kb 'kb.yaml') "schema_version: 1`ncontent_dir: content`nentrypoint: content/index.md`n"
    Write-Utf8 (Join-Path $kb 'content\index.md') @'
---
id: kb-20260831-index
type: map
---
# 首页

- [中文条目](<资料 空格/条目 中文.md#小节>)
- [资料目录](<资料 空格/>)
'@
    $entryPath = Join-Path $kb 'content\资料 空格\条目 中文.md'
    Write-Utf8 $entryPath @'
---
id: kb-20260831-entry
type: concept
---
# 中文条目

Alpha.

行内公式：$P(X=x \mid accepted)$。

$$
R_K = ARK_{K_1} \circ SR
$$

| 项目 | 状态 |
| :--- | ---: |
| [返回首页](../index.md) | ~~旧状态~~ |

- [x] 已检查的 gate
- [ ] 待检查的 gate

1. 外层步骤
   - 内层条件

> 边界：这是一项静态阅读器可见的警告。

> [!NOTE]
> 这是一项 renderer profile 已验证的提示。

保留可追溯说明[^render-profile]。

[^render-profile]: 脚注保留在静态页面中。

```powershell
Get-Item
```

## 小节

[返回](../index.md)
'@
    $sourceBefore = [IO.File]::ReadAllBytes($entryPath)

    $first = Invoke-Builder -Root $kb -Destination $destination -KatexAssets $katexAssets
    Assert-True ($first.ExitCode -eq 0 -and $first.Data.status -eq 'success' -and -not $first.Data.force_rebuild) "first build should succeed: $($first.Raw -join ' ')"
    Assert-True ($first.Data.generated -ge 3) 'first build should generate Markdown pages and a directory index'
    Assert-True ((Test-Path -LiteralPath (Join-Path $destination '.kb-static-manifest.json') -PathType Leaf)) 'destination must contain its fixed machine-readable manifest'
    $manifest = Get-Content -LiteralPath (Join-Path $destination '.kb-static-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-True ($manifest.schema -eq 'knowledge-base-static-site' -and $manifest.schema_version -eq 1) 'manifest must expose a stable schema/version'
    Assert-True ($manifest.template_version -eq '3') 'manifest must identify the structured-Markdown CSS template version'
    Assert-True ($manifest.entry_output_path -eq 'index.html' -and $first.Data.entry_page -eq (Join-Path $destination 'index.html')) 'result and manifest must identify the generated entry page'
    Assert-True (@($manifest.pages).Count -eq 2) 'manifest must record every Markdown source recursively'
    Assert-True ($manifest.katex.asset_version -eq '0.18.1' -and @($manifest.katex.assets).Count -eq 4) 'manifest must record the fixed KaTeX version and every copied asset'
    Assert-True ((@($manifest.katex.assets | Where-Object output_path -eq '_assets/katex/fonts/KaTeX_Main-Regular.woff2')[0].sha256 -match '^[0-9a-f]{64}$')) 'KaTeX asset records must include source SHA-256'
    Assert-True ((@($manifest.katex.assets | Where-Object source_path -eq 'assets/katex/katex.min.js')[0].output_path -eq '_assets/katex/katex.min.js') -and (@($manifest.katex.assets | Where-Object source_path -eq 'assets/katex/katex.min.js')[0].source_path -notmatch '^[A-Za-z]:') ) 'KaTeX manifest paths must be portable relative source and output paths'
    Assert-True ((@($manifest.pages | Where-Object source_path -eq '资料 空格/条目 中文.md')[0].sha256 -match '^[0-9a-f]{64}$')) 'page records must include source SHA-256'
    Assert-True ((@($manifest.pages | Where-Object source_path -eq '资料 空格/条目 中文.md')[0].output_sha256 -match '^[0-9a-f]{64}$')) 'page records must include output SHA-256'
    $indexHtml = Get-Content -LiteralPath (Join-Path $destination 'index.html') -Raw -Encoding UTF8
    $entryHtmlPath = Join-Path $destination '资料 空格\条目 中文.html'
    $entryHtml = Get-Content -LiteralPath $entryHtmlPath -Raw -Encoding UTF8
    Assert-True ($indexHtml -match '(?i)^<!doctype html>' -and $indexHtml -match '<html') 'output must be a complete directly browsable HTML page'
    Assert-True ($indexHtml -match 'href="[^"]+\.html#' -and $indexHtml -notmatch '\.md(?:[?#\"])') 'ordinary relative Markdown links must be rewritten to HTML links'
    Assert-True ($indexHtml -match 'href="[^"]+index\.html"') 'directory links must resolve to a generated directory index'
    Assert-True ($entryHtml -match '<h1[^>]*>中文条目</h1>' -and $entryHtml -notmatch 'kb-20260831-entry') 'opening YAML front matter must not be rendered'
    Assert-True ($entryHtml -match 'href="\.\./index\.html"') 'nested relative Markdown links must be rewritten'
    Assert-True ($entryHtml -match '(?is)<table.*?<thead>.*?<th[^>]*style="text-align: left;"[^>]*>项目</th>.*?<th[^>]*style="text-align: right;"[^>]*>状态</th>.*?<tbody>.*?</table>') 'aligned Markdown tables must render as semantic table HTML'
    Assert-True ($entryHtml -match '(?is)<table.*?href="\.\./index\.html".*?</table>' -and $entryHtml -notmatch '(?is)<table.*?\.md.*?</table>') 'inline internal Markdown links inside tables must be rewritten to HTML links'
    Assert-True ($entryHtml -match '(?is)<ul class="contains-task-list">.*?<input[^>]*disabled="disabled"[^>]*type="checkbox".*?</ul>') 'task lists must render as disabled semantic checklists'
    Assert-True ($entryHtml -match '(?is)<ol>.*?<ul>.*?</ul>.*?</ol>') 'nested lists must retain their semantic nesting'
    Assert-True ($entryHtml -match '(?is)<blockquote>.*?静态阅读器可见的警告.*?</blockquote>') 'blockquotes must render as semantic blockquote HTML'
    Assert-True ($entryHtml -match '(?is)<div class="markdown-alert markdown-alert-note">.*?<p class="markdown-alert-title"[^>]*>.*?Note</p>.*?renderer profile 已验证的提示.*?</div>') 'GitHub alerts must render as semantic markdown-alert HTML'
    Assert-True ($entryHtml -match '<del>旧状态</del>') 'strikethrough must render as semantic del HTML'
    Assert-True ($entryHtml -match '(?is)<a[^>]*class="footnote-ref"[^>]*><sup>1</sup></a>.*?<div class="footnotes">') 'footnotes must render with semantic reference and footnote sections'
    Assert-True ($entryHtml -match '(?is)<pre><code class="language-powershell">Get-Item.*?</code></pre>') 'fenced code must render as a language-marked code block'
    foreach ($cssToken in @('table{{display:block', 'th,td{{border:', 'ul.contains-task-list', '.task-list-item', 'blockquote{{', '.markdown-alert{{', '.markdown-alert-title{{', '.footnotes{{', 'hr{{', 'del{{', 'pre{{', 'img{{max-width:100%')) {
        Assert-True ($entryHtml.Contains($cssToken.Replace('{{', '{'))) "static template must contain structured-Markdown CSS token: $cssToken"
    }
    Assert-True ($indexHtml -match 'href="\./_assets/katex/katex\.min\.css"' -and $indexHtml -match 'src="\./_assets/katex/katex\.min\.js"') 'root pages must use directly browsable relative KaTeX paths'
    Assert-True ($entryHtml -match 'href="\.\./_assets/katex/katex\.min\.css"' -and $entryHtml -match 'src="\.\./_assets/katex/contrib/auto-render\.min\.js"') 'nested pages must use depth-correct relative KaTeX paths'
    Assert-True ($entryHtml -match 'class="math"' -and $entryHtml.Contains('\(') -and $entryHtml.Contains('\[')) 'PowerShell Markdown math markers must remain available to KaTeX auto-render'
    Assert-True ($entryHtml.Contains('throwOnError:false') -and $entryHtml.Contains("left:'\\('") -and $entryHtml.Contains("left:'\\['")) 'auto-render must use only the Markdown renderer math delimiters and tolerate errors'
    Assert-True ((Get-Content -LiteralPath (Join-Path $destination '_assets\katex\katex.min.js') -Raw -Encoding UTF8) -eq 'fake katex javascript') 'KaTeX assets must be copied into the static output'
    $sourceAfter = [IO.File]::ReadAllBytes($entryPath)
    Assert-True ($sourceBefore.Length -eq $sourceAfter.Length -and -not (Compare-Object $sourceBefore $sourceAfter)) 'source Markdown must remain byte-identical'

    $second = Invoke-Builder -Root $kb -Destination $destination -KatexAssets $katexAssets
    Assert-True ($second.ExitCode -eq 0 -and -not $second.Data.force_rebuild -and $second.Data.generated -eq 0 -and $second.Data.skipped -ge 3 -and $second.Data.assets_generated -eq 0 -and $second.Data.assets_skipped -eq 4) 'unchanged pages and intact KaTeX assets must be skipped'

    $forceExtra = Join-Path $destination 'force-preserve.txt'
    Write-Utf8 $forceExtra 'unrelated destination file'
    $forced = Invoke-Builder -Root $kb -Destination $destination -KatexAssets $katexAssets -Force
    $managedPageCount = @($manifest.pages).Count + @($manifest.directories).Count
    Assert-True ($forced.ExitCode -eq 0 -and $forced.Data.force_rebuild -and $forced.Data.generated -eq $managedPageCount -and $forced.Data.skipped -eq 0) '-Force must regenerate every managed Markdown and directory page'
    Assert-True ($forced.Data.assets_generated -eq 4 -and $forced.Data.assets_skipped -eq 0) '-Force must recopy every current KaTeX asset'
    Assert-True ((Test-Path -LiteralPath $forceExtra -PathType Leaf) -and (Get-Content -LiteralPath $forceExtra -Raw -Encoding UTF8) -eq 'unrelated destination file') '-Force must preserve unrelated destination files'

    Remove-Item -LiteralPath (Join-Path $destination '_assets\katex\fonts\KaTeX_Main-Regular.woff2') -Force
    [IO.File]::WriteAllText((Join-Path $destination '_assets\katex\katex.min.js'), 'tampered KaTeX asset', [Text.UTF8Encoding]::new($false))
    $assetRepair = Invoke-Builder -Root $kb -Destination $destination -KatexAssets $katexAssets
    Assert-True ($assetRepair.ExitCode -eq 0 -and $assetRepair.Data.assets_generated -eq 2 -and $assetRepair.Data.generated -eq 0) 'missing or tampered KaTeX assets must be recopied without regenerating unchanged pages'

    $obsoleteSource = Join-Path $katexAssets 'contrib\obsolete.txt'
    $obsoleteOutput = Join-Path $destination '_assets\katex\contrib\obsolete.txt'
    Write-Utf8 $obsoleteSource 'obsolete bundled asset'
    $addObsolete = Invoke-Builder -Root $kb -Destination $destination -KatexAssets $katexAssets
    Assert-True ($addObsolete.ExitCode -eq 0 -and ($addObsolete.Data.assets_generated_paths -contains '_assets/katex/contrib/obsolete.txt')) 'new bundled KaTeX assets must be copied and recorded'
    Remove-Item -LiteralPath $obsoleteSource -Force
    Write-Utf8 $obsoleteOutput 'user replacement must survive'
    $preserveReplacement = Invoke-Builder -Root $kb -Destination $destination -KatexAssets $katexAssets
    Assert-True ($preserveReplacement.ExitCode -eq 0 -and (Test-Path -LiteralPath $obsoleteOutput -PathType Leaf) -and (Get-Content -LiteralPath $obsoleteOutput -Raw -Encoding UTF8) -eq 'user replacement must survive') 'stale KaTeX output with a changed hash must not be cleaned up'

    $oldTemplateManifest = Get-Content -LiteralPath (Join-Path $destination '.kb-static-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $oldTemplateManifest.template_version = 'obsolete-template'
    $oldTemplateManifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $destination '.kb-static-manifest.json') -Encoding UTF8 -NoNewline
    $templateChanged = Invoke-Builder -Root $kb -Destination $destination -KatexAssets $katexAssets
    Assert-True ($templateChanged.ExitCode -eq 0 -and $templateChanged.Data.generated -ge 3) 'template-version state changes must rebuild all generated pages'

    [IO.File]::WriteAllText($entryHtmlPath, 'tampered', [Text.UTF8Encoding]::new($false))
    $tampered = Invoke-Builder -Root $kb -Destination $destination -KatexAssets $katexAssets
    Assert-True ($tampered.ExitCode -eq 0 -and $tampered.Data.generated -eq 1 -and ($tampered.Data.generated_paths -contains '资料 空格/条目 中文.html')) 'tampered generated output must be rebuilt even when Markdown is unchanged'

    $entryItem = Get-Item -LiteralPath $entryPath
    $originalMtime = $entryItem.LastWriteTimeUtc
    $original = Get-Content -LiteralPath $entryPath -Raw -Encoding UTF8
    [IO.File]::WriteAllText($entryPath, $original.Replace('Alpha', 'Bravo'), [Text.UTF8Encoding]::new($false))
    (Get-Item -LiteralPath $entryPath).LastWriteTimeUtc = $originalMtime
    $hashChanged = Invoke-Builder -Root $kb -Destination $destination -KatexAssets $katexAssets
    Assert-True ($hashChanged.ExitCode -eq 0 -and $hashChanged.Data.generated -eq 1 -and ($hashChanged.Data.generated_paths -contains '资料 空格/条目 中文.html')) 'same-size, same-mtime Markdown content changes must rebuild by SHA-256'

    $newPath = Join-Path $kb 'content\资料 空格\新建.md'
    Write-Utf8 $newPath "# 新建`n"
    $newBuild = Invoke-Builder -Root $kb -Destination $destination -KatexAssets $katexAssets
    Assert-True ($newBuild.ExitCode -eq 0 -and ($newBuild.Data.generated_paths -contains '资料 空格/新建.html')) 'new Markdown files must be generated recursively'
    $extra = Join-Path $destination 'user-extra.txt'
    Write-Utf8 $extra 'must survive'
    Remove-Item -LiteralPath $entryPath -Force
    $removedBuild = Invoke-Builder -Root $kb -Destination $destination -KatexAssets $katexAssets
    Assert-True ($removedBuild.ExitCode -eq 0 -and ($removedBuild.Data.removed_paths -contains '资料 空格/条目 中文.html')) 'deleted Markdown must remove only its previously manifest-owned output'
    Assert-True (-not (Test-Path -LiteralPath $entryHtmlPath) -and (Test-Path -LiteralPath $extra -PathType Leaf)) 'source deletion must preserve user-owned destination files'
    Remove-Item -LiteralPath $newPath -Force
    Remove-Item -LiteralPath (Split-Path -Parent $newPath) -Force
    $removedDirectory = Invoke-Builder -Root $kb -Destination $destination -KatexAssets $katexAssets
    Assert-True ($removedDirectory.ExitCode -eq 0 -and ($removedDirectory.Data.removed_paths -contains '资料 空格/index.html')) 'deleting a directory without index.md must remove its prior manifest-owned directory index'

    $conflictKb = Join-Path $testRoot 'conflict kb'
    $conflictDestination = Join-Path $testRoot 'conflict destination'
    Write-Utf8 (Join-Path $conflictKb 'kb.yaml') "schema_version: 1`ncontent_dir: content`nentrypoint: content/index.md`n"
    Write-Utf8 (Join-Path $conflictKb 'content\index.md') '# Conflict'
    $conflictingOutput = Join-Path $conflictDestination 'index.html'
    Write-Utf8 $conflictingOutput 'user-owned output'
    $conflict = Invoke-Builder -Root $conflictKb -Destination $conflictDestination -KatexAssets $katexAssets
    Assert-True ($conflict.ExitCode -eq 2 -and $conflict.Data.status -eq 'blocked' -and (Get-Content -LiteralPath $conflictingOutput -Raw -Encoding UTF8) -eq 'user-owned output') 'first build must not overwrite output lacking prior manifest ownership'
    $forcedConflict = Invoke-Builder -Root $conflictKb -Destination $conflictDestination -KatexAssets $katexAssets -Force
    Assert-True ($forcedConflict.ExitCode -eq 2 -and $forcedConflict.Data.status -eq 'blocked' -and (Get-Content -LiteralPath $conflictingOutput -Raw -Encoding UTF8) -eq 'user-owned output') '-Force must not overwrite output lacking prior manifest ownership'

    $assetConflictDestination = Join-Path $testRoot 'asset conflict destination'
    $conflictingAsset = Join-Path $assetConflictDestination '_assets\katex\katex.min.js'
    Write-Utf8 $conflictingAsset 'user-owned KaTeX asset'
    $assetConflict = Invoke-Builder -Root $conflictKb -Destination $assetConflictDestination -KatexAssets $katexAssets
    Assert-True ($assetConflict.ExitCode -eq 2 -and $assetConflict.Data.status -eq 'blocked' -and (Get-Content -LiteralPath $conflictingAsset -Raw -Encoding UTF8) -eq 'user-owned KaTeX asset') 'first build must reject an unowned KaTeX asset path conflict'

    $inside = Invoke-Builder -Root $kb -Destination (Join-Path $kb 'static') -KatexAssets $katexAssets
    Assert-True ($inside.ExitCode -eq 2 -and $inside.Data.status -eq 'blocked') 'destination inside the knowledge base must be rejected'
    $contains = Invoke-Builder -Root $kb -Destination $testRoot -KatexAssets $katexAssets
    Assert-True ($contains.ExitCode -eq 2 -and $contains.Data.status -eq 'blocked') 'destination containing the knowledge base must be rejected'

    $linkTarget = Join-Path $testRoot 'junction target'
    $linkDestination = Join-Path $testRoot 'junction destination'
    New-Item -ItemType Directory -Path $linkTarget -Force | Out-Null
    $junctionCreated = $false
    try {
        New-Item -ItemType Junction -Path $linkDestination -Target $linkTarget -ErrorAction Stop | Out-Null
        $junctionCreated = $true
        $junction = Invoke-Builder -Root $kb -Destination $linkDestination -KatexAssets $katexAssets
        Assert-True ($junction.ExitCode -eq 2 -and (($junction.Raw -join ' ') -match 'junction|symbolic link')) 'junction destination must be rejected'
    }
    catch {
        if ($junctionCreated) { throw }
        Write-Verbose 'Junction creation unavailable; reparse-point coverage skipped.'
    }
    finally {
        if ($junctionCreated -and (Test-Path -LiteralPath $linkDestination)) { Remove-Item -LiteralPath $linkDestination -Force }
    }

    $assetLinkTarget = Join-Path $testRoot 'asset junction target'
    $assetLink = Join-Path $katexAssets 'internal junction'
    New-Item -ItemType Directory -Path $assetLinkTarget -Force | Out-Null
    Write-Utf8 (Join-Path $assetLinkTarget 'redirected.txt') 'must not be traversed'
    $assetJunctionCreated = $false
    try {
        New-Item -ItemType Junction -Path $assetLink -Target $assetLinkTarget -ErrorAction Stop | Out-Null
        $assetJunctionCreated = $true
        $assetJunction = Invoke-Builder -Root $kb -Destination $destination -KatexAssets $katexAssets
        Assert-True ($assetJunction.ExitCode -eq 2 -and (($assetJunction.Raw -join ' ') -match 'junction|symbolic link')) 'junctions inside the bundled asset tree must remain blocked'
    }
    catch {
        if ($assetJunctionCreated) { throw }
        Write-Verbose 'Asset junction creation unavailable; internal asset reparse-point coverage skipped.'
    }
    finally {
        if ($assetJunctionCreated -and (Test-Path -LiteralPath $assetLink)) { Remove-Item -LiteralPath $assetLink -Force }
    }

    $installedSkill = Join-Path $testRoot 'installed skill junction'
    $installedDestination = Join-Path $testRoot 'installed junction output'
    $installJunctionCreated = $false
    try {
        New-Item -ItemType Junction -Path $installedSkill -Target (Join-Path $projectRoot 'knowledge-base-manager') -ErrorAction Stop | Out-Null
        $installJunctionCreated = $true
        $installedBuilder = Join-Path $installedSkill 'scripts\kb-build-static.ps1'
        $installedBuild = Invoke-Builder -Root $kb -Destination $installedDestination -Builder $installedBuilder
        Assert-True ($installedBuild.ExitCode -eq 0 -and $installedBuild.Data.status -eq 'success') "builder invoked through an installed Skill junction must accept its bundled assets: $($installedBuild.Raw -join ' ')"
        Assert-True ((Test-Path -LiteralPath (Join-Path $installedDestination '_assets\katex\katex.min.js') -PathType Leaf)) 'installed Skill junction build must copy the default bundled KaTeX assets'
    }
    catch {
        if ($installJunctionCreated) { throw }
        Write-Verbose 'Skill installation junction creation unavailable; installed-path regression coverage skipped.'
    }
    finally {
        if ($installJunctionCreated -and (Test-Path -LiteralPath $installedSkill)) { Remove-Item -LiteralPath $installedSkill -Force }
    }

    Write-Output 'kb-build-static tests passed.'
    $global:LASTEXITCODE = 0
}
finally {
    if (Test-Path -LiteralPath $testRoot) { Remove-Item -LiteralPath $testRoot -Recurse -Force }
}
