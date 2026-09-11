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
    [string]$KatexAssetsRoot,
    [string]$GraphAssetsRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'kb-path-safety.ps1')
. (Join-Path $PSScriptRoot 'kb-static-navigation.ps1')
. (Join-Path $PSScriptRoot 'kb-static-graph.ps1')

# Bump either value when generated page markup or its common template changes.
$generatorVersion = '1.2.0'
$templateVersion = '9'
$manifestName = '.kb-static-manifest.json'
$katexAssetVersion = '0.18.1'
$graphAssetVersion = '1.0.0'

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

function Get-KbStaticGraphPrefix {
    param([Parameter(Mandatory)][string]$OutputRelative)

    $directory = Split-Path -Parent ($OutputRelative.Replace('/', [IO.Path]::DirectorySeparatorChar))
    if ([string]::IsNullOrWhiteSpace($directory) -or $directory -eq '.') { return './_assets/graph' }
    $levels = @($directory -split '[\\/]+' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }).Count
    return (('../' * $levels) + '_assets/graph')
}

function Get-KbStaticOutputBaseUrl {
    param([Parameter(Mandatory)][string]$OutputRelative)

    $directory = Split-Path -Parent ($OutputRelative.Replace('/', [IO.Path]::DirectorySeparatorChar))
    if ([string]::IsNullOrWhiteSpace($directory) -or $directory -eq '.') { return '.' }
    $levels = @($directory -split '[\\/]+' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }).Count
    return (('../' * ($levels - 1)) + '..')
}

function New-KbStaticBreadcrumb {
    param(
        [Parameter(Mandatory)][string]$Title,
        [Parameter(Mandatory)][string]$OutputRelative,
        [Parameter(Mandatory)]$Navigation,
        [string]$SourceRelative = '',
        [switch]$IsHome,
        [int]$InboxCount = 0
    )

    $rootPage = $Navigation.Pages[$Navigation.EntrySource]
    $items = [System.Collections.Generic.List[string]]::new()
    $chain = [Collections.Generic.List[string]]::new()
    $connected = $false
    $page = if ($SourceRelative -and $Navigation.Pages.ContainsKey($SourceRelative)) { $Navigation.Pages[$SourceRelative] } else { $null }
    if ($null -ne $page -and $SourceRelative -ne $Navigation.EntrySource) {
        $cursor = $page
        while ($cursor.Parents.Count -eq 1) {
            $parentSource = $cursor.Parents[0]
            if ($parentSource -eq $Navigation.EntrySource) { $connected = $true; break }
            $chain.Add($parentSource)
            $cursor = $Navigation.Pages[$parentSource]
        }
    }
    if ($SourceRelative -ne $Navigation.EntrySource) {
        $href = [System.Net.WebUtility]::HtmlEncode((Get-KbStaticNavigationHref -FromOutput $OutputRelative -ToOutput $rootPage.Output))
        $items.Add('<li><a href="' + $href + '">' + [System.Net.WebUtility]::HtmlEncode($rootPage.Title) + '</a></li>')
        if ($connected) {
            for ($index = $chain.Count - 1; $index -ge 0; $index--) {
                $ancestor = $Navigation.Pages[$chain[$index]]
                $href = [System.Net.WebUtility]::HtmlEncode((Get-KbStaticNavigationHref -FromOutput $OutputRelative -ToOutput $ancestor.Output))
                $items.Add('<li><a href="' + $href + '">' + [System.Net.WebUtility]::HtmlEncode($ancestor.Title) + '</a></li>')
            }
        }
    }
    $items.Add('<li><span aria-current="page">' + [System.Net.WebUtility]::HtmlEncode($Title) + '</span></li>')
    $navHtml = '<nav class="kb-breadcrumb" aria-label="面包屑"><ol>' + ($items -join '') + '</ol></nav>'
    $badgeClass = if ($InboxCount -gt 0) { 'kb-inbox-badge-active' } else { 'kb-inbox-badge-empty' }
    $inboxLink = if ($IsHome.IsPresent) {
        $inboxHref = [System.Net.WebUtility]::HtmlEncode((Get-KbStaticNavigationHref -FromOutput $OutputRelative -ToOutput 'inbox/index.html'))
        '<a href="' + $inboxHref + '" class="kb-inbox-trigger-btn" id="kb-inbox-trigger" aria-label="查看收件箱"><span>收件箱</span><span class="kb-inbox-badge ' + $badgeClass + '">' + $InboxCount + '</span></a>'
    } else { '' }
    $actionsHtml = '<div class="kb-nav-actions"><button type="button" class="kb-graph-trigger-btn" id="kb-graph-trigger" aria-label="打开关系图谱">关系图谱</button>' + $inboxLink + '</div>'
    $html = '<div class="kb-nav-header">' + $navHtml + $actionsHtml + '</div>'
    if ($null -ne $page -and $SourceRelative -ne $Navigation.EntrySource -and -not $connected) {
        if ($page.Parents.Count -eq 0) { $html += '<p class="kb-uncollected">尚未被项目或主题收录</p>' }
        else {
            $links = foreach ($parentSource in $page.Parents) {
                $parent = $Navigation.Pages[$parentSource]
                $href = [System.Net.WebUtility]::HtmlEncode((Get-KbStaticNavigationHref -FromOutput $OutputRelative -ToOutput $parent.Output))
                '<li><a href="' + $href + '">' + [System.Net.WebUtility]::HtmlEncode($parent.Title) + '</a></li>'
            }
            $html += '<nav class="kb-collections" aria-label="收录入口"><p>收录入口</p><ul>' + ($links -join '') + '</ul></nav>'
        }
    }
    return $html
}

function New-KbStaticHtmlDocument {
    param(
        [Parameter(Mandatory)][string]$Title,
        [Parameter(Mandatory)][string]$BodyHtml,
        [Parameter(Mandatory)][string]$OutputRelative,
        [Parameter(Mandatory)]$Navigation,
        [string]$SourceRelative = '',
        [switch]$IsHome,
        [string]$PageNodeId = '',
        [int]$InboxCount = 0
    )
    $safeTitle = [System.Net.WebUtility]::HtmlEncode($Title)
    $katexPrefix = Get-KbStaticKatexPrefix -OutputRelative $OutputRelative
    $graphPrefix = Get-KbStaticGraphPrefix -OutputRelative $OutputRelative
    $outputBaseUrl = Get-KbStaticOutputBaseUrl -OutputRelative $OutputRelative
    $breadcrumb = New-KbStaticBreadcrumb -Title $Title -OutputRelative $OutputRelative -Navigation $Navigation -SourceRelative $SourceRelative -IsHome:$IsHome.IsPresent -InboxCount $InboxCount

    $inlineGraphHtml = if ($IsHome.IsPresent) {
        @'
<section id="kb-graph-inline" class="kb-graph-inline kb-graph-inline-section" aria-label="知识关系图谱">
  <div class="kb-graph-inline-header" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.75rem;">
    <h2 style="margin:0;border-bottom:none;padding-bottom:0;font-size:1.15rem;">知识关系图谱</h2>
    <button type="button" class="kb-graph-trigger-btn" id="kb-graph-trigger-inline" aria-label="弹出大窗口浏览关系图谱" title="弹出大窗口浏览">⛶ 全屏大窗口</button>
  </div>
  <div id="kb-graph-app" class="kb-graph-app kb-graph-inline-container"></div>
</section>
'@
    } else { '' }

    $escapedNodeId = [System.Net.WebUtility]::HtmlEncode($PageNodeId)
    $graphScript = if ($IsHome.IsPresent) {
        [string]::Format(@'
<script id="kb-graph-inline-script" defer>
document.addEventListener('DOMContentLoaded', function () {{
    var container = document.getElementById('kb-graph-app') || document.getElementById('kb-graph-container');
    var inlineGraph = null;
    if (container && window.mountKbGraph) {{
        inlineGraph = window.mountKbGraph(container, {{
            mode: 'inline',
            outputBaseUrl: '{0}',
            initialPageId: '{1}'
        }});
    }}
    function openOverlay() {{
        if (window.mountKbGraph && !document.querySelector('.kb-graph-mode-overlay')) {{
            var state = (inlineGraph && typeof inlineGraph.getState === 'function') ? inlineGraph.getState() : null;
            window.mountKbGraph(document.body, {{
                mode: 'overlay',
                outputBaseUrl: '{0}',
                initialPageId: (state && state.focusedId) ? state.focusedId : '{1}',
                initialExpanded: state ? state.expanded : null,
                initialEgoFocusId: state ? state.egoFocusId : null,
                onClose: function (finalState) {{
                    if (inlineGraph && finalState && typeof inlineGraph.setState === 'function') {{
                        inlineGraph.setState(finalState);
                    }}
                }}
            }});
        }}
    }}
    var trigger = document.getElementById('kb-graph-trigger');
    if (trigger) {{
        trigger.addEventListener('click', openOverlay);
    }}
    var inlineTrigger = document.getElementById('kb-graph-trigger-inline');
    if (inlineTrigger) {{
        inlineTrigger.addEventListener('click', openOverlay);
    }}
}});
</script>
'@, $outputBaseUrl, $escapedNodeId)
    } else {
        [string]::Format(@'
<script id="kb-graph-overlay-script" defer>
document.addEventListener('DOMContentLoaded', function () {{
    var trigger = document.getElementById('kb-graph-trigger');
    if (trigger) {{
        trigger.addEventListener('click', function () {{
            if (window.mountKbGraph && !document.querySelector('.kb-graph-mode-overlay')) {{
                window.mountKbGraph(document.body, {{
                    mode: 'overlay',
                    outputBaseUrl: '{0}',
                    initialPageId: '{1}'
                }});
            }}
        }});
    }}
}});
</script>
'@, $outputBaseUrl, $escapedNodeId)
    }

    $template = @'
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{0}</title>
<style id="kb-theme">
:root{{color-scheme:light;font-family:"Segoe UI","Microsoft YaHei","PingFang SC",sans-serif;font-size:16px;color:#25384a;background:#edf4fa}}
*{{box-sizing:border-box}} html{{scroll-padding-top:2rem}}
body{{max-width:1040px;margin:2.5rem auto;padding:0 2rem;background:#edf4fa;line-height:1.85}}
.kb-paper{{min-width:0;background:#fff;border:1px solid #d6e3ee;border-radius:14px;box-shadow:0 8px 30px #284d7210;padding:2rem 3.25rem 2.5rem}}
.kb-content{{min-width:0;overflow-wrap:anywhere}} .kb-content>:last-child{{margin-bottom:0}}
a{{color:#176bb0;text-underline-offset:.2em;text-decoration-thickness:1px}} a:hover{{color:#105184}} :focus-visible{{outline:3px solid #176bb0;outline-offset:4px}}
h1,h2,h3,h4,h5,h6{{line-height:1.45;color:#1d4c71;scroll-margin-top:2rem}} h1{{font-size:clamp(1.75rem,3vw,2.25rem);letter-spacing:-.025em;margin:1.5rem 0;color:#163d5e}} .kb-content>h1:first-child{{margin:0 0 1.5rem;padding:1.25rem 1.5rem;border:1px solid #dce7f0;border-radius:8px;background:linear-gradient(135deg,#f0f8ff 0%,#fff 85%)}}
h2{{margin:2.25rem 0 1rem;padding-bottom:.6rem;border-bottom:1px solid #dce7f0;font-size:1.3rem}} h3{{font-size:1.08rem;margin:1.6rem 0 .6rem}} p{{margin:.9rem 0}}
pre{{overflow:auto;max-width:100%;margin:1.25rem 0;padding:1.25rem 1.4rem;background:#f1f6fb;border:1px solid #d6e5f1;border-radius:8px;line-height:1.7;tab-size:4;color:#274963}} pre code{{padding:0;background:transparent;border:0;font-size:1em;overflow-wrap:normal}}
code,pre{{font-family:Consolas,"Cascadia Code","SFMono-Regular",monospace;font-size:.88em}} :not(pre)>code{{background:#edf4fa;padding:.15em .4em;border:1px solid #e0eaf3;border-radius:4px;color:#1c5c8d}}
table{{display:block;max-width:100%;width:max-content;overflow-x:auto;border-collapse:collapse;margin:1.25rem 0;font-size:.9rem}} th,td{{border:1px solid #dce7f0;padding:.7rem .9rem;text-align:left;vertical-align:top}} th{{background:#edf5fc;color:#2a5b80;font-weight:650}} tr:nth-child(even) td{{background:#f9fbfd}} caption{{text-align:left;color:#60758a;padding:.5rem 0}}
ul,ol{{padding-left:1.6rem}} li+li{{margin-top:.3rem}} li>ul,li>ol{{margin:.2rem 0 .1rem}} li::marker{{color:#4388bb}}
ul.task-list,ul.contains-task-list{{list-style:none;padding-left:.25rem}} .task-list-item{{display:flex;align-items:baseline;gap:.45rem}} .task-list-item>input[type="checkbox"]{{margin:0;flex:0 0 auto}}
blockquote{{margin:1.4rem 0;padding:.15rem 1.25rem;border-left:.2rem solid #65a9dc;background:#f3f8fd;color:#466278;border-radius:0 7px 7px 0}} blockquote>:first-child{{margin-top:.55rem}} blockquote>:last-child{{margin-bottom:.55rem}}
.markdown-alert{{margin:1rem 0;padding:.1rem 1rem;border-left:.28rem solid #60a5fa;background:#eff6ff}} .markdown-alert-title{{font-weight:700}} .markdown-alert-warning{{border-color:#f59e0b;background:#fffbeb}} .markdown-alert-important{{border-color:#a855f7;background:#faf5ff}} .markdown-alert-caution{{border-color:#ef4444;background:#fef2f2}}
.footnotes{{font-size:.92em;border-top:1px solid #dce7f0;margin-top:2rem;color:#60758a}} .footnote-ref{{text-decoration:none}}
hr{{border:0;border-top:1px solid #dce7f0;margin:2rem 0}} del{{color:#60758a}} img{{max-width:100%;height:auto}} .katex-display{{max-width:100%;overflow-x:auto;overflow-y:hidden;padding:.25rem 0}}
.kb-nav-header{{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:.5rem;margin:0 0 1.5rem}}
.kb-nav-header .kb-breadcrumb{{margin:0}}
.kb-nav-header .kb-breadcrumb ol{{display:flex;flex-wrap:wrap;gap:.4rem;list-style:none;padding:0;margin:0;font-size:.85rem;color:#60758a}}
.kb-breadcrumb ol{{display:flex;flex-wrap:wrap;gap:.4rem;list-style:none;padding:0;margin:0 0 1.5rem;font-size:.85rem;color:#60758a}} .kb-breadcrumb li{{min-width:0;overflow-wrap:anywhere}} .kb-breadcrumb li+li{{margin:0}} .kb-breadcrumb li+li::before{{content:'/';margin-right:.4rem;color:#94a3b8}} .kb-breadcrumb [aria-current]{{color:#466278;overflow-wrap:anywhere}}
.kb-nav-actions{{display:flex;align-items:center;gap:.6rem}}
.kb-graph-trigger-btn{{font:inherit;font-size:.85rem;padding:.2rem .65rem;color:#176bb0;background:#eff6ff;border:1px solid #b5d7f0;border-radius:5px;cursor:pointer;touch-action:manipulation;white-space:nowrap}}
.kb-graph-trigger-btn:hover{{background:#dbeafe;border-color:#388bc9}}
.kb-inbox-trigger-btn{{position:relative;display:inline-flex;align-items:center;font:inherit;font-size:.85rem;padding:.2rem .7rem;color:#176bb0;background:#eff6ff;border:1px solid #b5d7f0;border-radius:5px;cursor:pointer;text-decoration:none;touch-action:manipulation;white-space:nowrap}}
.kb-inbox-trigger-btn:hover{{background:#dbeafe;border-color:#388bc9;text-decoration:none}}
.kb-inbox-badge{{position:absolute;top:-6px;right:-6px;display:flex;align-items:center;justify-content:center;min-width:16px;height:16px;padding:0 3px;border-radius:50%;font-size:10px;font-weight:700;line-height:1;box-shadow:0 0 0 1.5px #fff}}
.kb-inbox-badge-empty{{background:#94a3b8;color:#ffffff}}
.kb-inbox-badge-active{{background:#ef4444;color:#ffffff}}
.kb-graph-inline-section{{margin-top:2.5rem;padding-top:1.5rem;border-top:1px solid #dce7f0}}
.kb-collections,.kb-uncollected{{font-size:.85rem;color:#60758a;margin:0 0 1.5rem}} .kb-collections p{{margin:0}} .kb-collections ul{{display:flex;flex-wrap:wrap;gap:.4rem 1rem;list-style:none;padding:0;margin:.3rem 0}} .kb-collections li+li{{margin:0}}
details{{margin:1.4rem 0;padding:.75rem 1.1rem;border:1px solid #dce7f0;border-radius:8px;background:#fbfdff}} summary{{cursor:pointer;font-weight:650;color:#285d86}} details[open]>summary{{margin-bottom:.65rem}}
.kb-code-tools{{display:flex;align-items:center;flex-wrap:wrap;gap:.65rem;margin:1rem 0 -.7rem}} .kb-code-tools button{{font:inherit;font-size:.85rem;padding:.25rem .65rem;color:#176bb0;background:#eff6ff;border:1px solid #b5d7f0;border-radius:5px;cursor:pointer}} .kb-code-tools button:hover{{background:#dbeafe}} .kb-code-tools button:disabled{{cursor:wait;opacity:.65}} .kb-copy-status{{font-size:.85rem;color:#60758a}}
.kb-toc{{min-width:0;font-size:.85rem;color:#60758a}} .kb-toc-title{{margin:0 0 .75rem;font-size:.9rem;color:#285d86;font-weight:650}} .kb-toc ol{{list-style:none;margin:0;padding:0}} .kb-toc li+li{{margin-top:.15rem}} .kb-toc a{{display:block;padding:.35rem .6rem;border-left:1px solid #cdddea;text-decoration:none;overflow-wrap:anywhere}} .kb-toc a:hover{{background:#e2eef8;border-color:#388bc9}} .kb-toc .kb-toc-level-3 a{{padding-left:1.3rem}} .kb-toc .kb-toc-level-4 a{{padding-left:2rem}}
@media (min-width:1100px){{body.kb-has-toc{{max-width:1320px;display:grid;grid-template-columns:minmax(0,1fr) 200px;gap:2rem;align-items:start}} .kb-toc{{position:sticky;top:2rem;max-height:calc(100vh - 4rem);overflow-y:auto;padding:.75rem .25rem}}}}
@media (max-width:1099px){{body.kb-has-toc{{display:flex;flex-direction:column}} .kb-toc{{order:-1;width:100%;margin:0 0 1rem;padding:1rem;background:#f3f8fd;border:1px solid #d6e3ee;border-radius:8px}} .kb-paper{{width:100%}}}}
@media (max-width:600px){{body{{margin:1rem auto;padding:0 .75rem}} .kb-paper{{padding:1.25rem 1.1rem 1.5rem;border-radius:10px}} .kb-content>h1:first-child{{padding:1rem}} pre{{padding:.9rem}} th,td{{padding:.5rem .65rem}}}}
@media print{{:root{{font-size:11pt;background:#fff;color:#000}} body,body.kb-has-toc{{display:block;max-width:none;margin:0;padding:0;background:#fff;color:#000}} .kb-paper{{padding:0;border:0;border-radius:0;box-shadow:none}} .kb-code-tools,.kb-toc,.kb-graph-trigger-btn,.kb-inbox-trigger-btn,.kb-graph-inline-section,.kb-graph-root{{display:none}} .kb-content>h1:first-child{{padding:0;border:0;background:#fff}} h1,h2,h3{{break-after:avoid}} pre{{white-space:pre-wrap;overflow-wrap:anywhere}} pre code{{overflow-wrap:anywhere}} table{{display:table;width:100%;overflow:visible}} tr,blockquote{{break-inside:avoid}} a{{color:inherit}}}}
</style>
<link rel="stylesheet" href="{2}/katex.min.css">
<script defer src="{2}/katex.min.js"></script>
<script defer src="{2}/contrib/auto-render.min.js"></script>
<script defer>document.addEventListener('DOMContentLoaded',function(){{renderMathInElement(document.body,{{delimiters:[{{left:'\\(',right:'\\)',display:false}},{{left:'\\[',right:'\\]',display:true}}],throwOnError:false}});}});</script>
<link rel="stylesheet" href="{4}/graph.css">
<script defer src="{4}/graph-data.js"></script>
<script defer src="{4}/graph-previews.js"></script>
<script defer src="{4}/graph.js"></script>
{5}
<script id="kb-toc-script">
document.addEventListener('DOMContentLoaded', function () {{
    var toc = document.getElementById('kb-toc');
    var list = document.createElement('ol');
    var nextId = 1;
    document.querySelectorAll('.kb-content h2, .kb-content h3, .kb-content h4').forEach(function (heading) {{
        if (heading.closest('pre, code')) return;
        if (!heading.id) {{
            var candidate;
            do {{ candidate = 'kb-heading-' + nextId++; }} while (document.getElementById(candidate));
            heading.id = candidate;
        }}
        var item = document.createElement('li');
        item.className = 'kb-toc-level-' + heading.tagName.substring(1);
        var link = document.createElement('a');
        link.textContent = heading.textContent;
        link.setAttribute('href', '#' + encodeURIComponent(heading.id));
        link.addEventListener('click', function () {{
            var ancestor = heading.parentElement;
            while (ancestor) {{
                if (ancestor.tagName === 'DETAILS') ancestor.open = true;
                ancestor = ancestor.parentElement;
            }}
        }});
        item.appendChild(link);
        list.appendChild(item);
    }});
    if (!list.children.length) return;
    toc.appendChild(list);
    toc.hidden = false;
    document.body.classList.add('kb-has-toc');
}});
</script>
<script id="kb-i18n-script">
(function () {{
    var isZh = (function () {{
        if (typeof window !== 'undefined' && window.location && window.location.search) {{
            try {{
                var params = new URLSearchParams(window.location.search);
                var q = params.get('lang');
                if (q === 'en') return false;
                if (q === 'zh') return true;
            }} catch (e) {{}}
        }}
        var nav = (typeof navigator !== 'undefined' && ((navigator.languages && navigator.languages[0]) || navigator.language || navigator.userLanguage)) || '';
        return nav.toLowerCase().startsWith('zh');
    }})();
    window.__KB_IS_ZH__ = isZh;
    if (!isZh) {{
        document.documentElement.lang = 'en';
        document.addEventListener('DOMContentLoaded', function () {{
            var bc = document.querySelector('.kb-breadcrumb');
            if (bc) bc.setAttribute('aria-label', 'Breadcrumbs');
            var tr = document.getElementById('kb-graph-trigger');
            if (tr) {{
                tr.textContent = 'Graph View';
                tr.setAttribute('aria-label', 'Open Knowledge Graph');
            }}
            var inb = document.getElementById('kb-inbox-trigger');
            if (inb) {{
                var inbSpan = inb.querySelector('span:first-child');
                if (inbSpan) inbSpan.textContent = 'Inbox';
                inb.setAttribute('aria-label', 'View Inbox');
            }}
            var trIn = document.getElementById('kb-graph-trigger-inline');
            if (trIn) {{
                trIn.textContent = '⛶ Fullscreen';
                trIn.setAttribute('aria-label', 'Open Knowledge Graph in fullscreen');
                trIn.setAttribute('title', 'Open fullscreen');
            }}
            var inSec = document.getElementById('kb-graph-inline');
            if (inSec) {{
                inSec.setAttribute('aria-label', 'Knowledge Graph');
                var h2 = inSec.querySelector('h2');
                if (h2) h2.textContent = 'Knowledge Graph';
            }}
            var uncoll = document.querySelector('.kb-uncollected');
            if (uncoll) uncoll.textContent = 'Not yet collected into any project or topic';
            var colls = document.querySelector('.kb-collections');
            if (colls) {{
                colls.setAttribute('aria-label', 'Collection Entries');
                var p = colls.querySelector('p');
                if (p) p.textContent = 'Collection Entries';
            }}
            var toc = document.getElementById('kb-toc');
            if (toc) toc.setAttribute('aria-label', 'Table of Contents');
            var tocTitle = document.querySelector('.kb-toc-title');
            if (tocTitle) tocTitle.textContent = 'Table of Contents';
        }});
    }}
}})();
</script>
<script id="kb-copy-script">
document.addEventListener('DOMContentLoaded', function () {{
    var isZh = window.__KB_IS_ZH__ !== false;
    document.querySelectorAll('pre > code').forEach(function (code) {{
        var pre = code.parentElement;
        var controls = document.createElement('div');
        controls.className = 'kb-code-tools';
        var button = document.createElement('button');
        button.type = 'button';
        button.textContent = isZh ? '复制代码' : 'Copy Code';
        var status = document.createElement('span');
        status.className = 'kb-copy-status';
        status.setAttribute('role', 'status');
        status.setAttribute('aria-live', 'polite');
        controls.appendChild(button);
        controls.appendChild(status);
        pre.parentNode.insertBefore(controls, pre);
        function selectForManualCopy() {{
            try {{
                var selection = window.getSelection();
                if (!selection) throw new Error('Selection unavailable');
                var range = document.createRange();
                range.selectNodeContents(code);
                selection.removeAllRanges();
                selection.addRange(range);
                status.textContent = isZh ? '未自动复制；已选中代码，请按 Ctrl+C / Command+C 复制。' : 'Not copied automatically; text selected, press Ctrl+C / Command+C to copy.';
            }} catch (error) {{
                status.textContent = isZh ? '未自动复制，请手动选中代码并按 Ctrl+C / Command+C。' : 'Not copied automatically; please manually select code and press Ctrl+C / Command+C.';
            }}
        }}
        button.addEventListener('click', async function () {{
            button.disabled = true;
            status.textContent = '';
            try {{
                if (!navigator.clipboard || typeof navigator.clipboard.writeText !== 'function') {{
                    selectForManualCopy();
                    return;
                }}
                await navigator.clipboard.writeText(code.textContent);
                status.textContent = isZh ? '已复制代码。' : 'Code copied.';
            }} catch (error) {{
                selectForManualCopy();
            }} finally {{
                button.disabled = false;
            }}
        }});
    }});
}});
</script>
</head>
<body>
<main class="kb-paper">
{3}
<div class="kb-content">
{1}
</div>
{6}
</main>
<aside id="kb-toc" class="kb-toc" aria-label="文章目录" hidden><p class="kb-toc-title">文章目录</p></aside>
</body>
</html>
'@
    return [string]::Format($template, $safeTitle, $BodyHtml, $katexPrefix, $breadcrumb, $graphPrefix, $graphScript, $inlineGraphHtml)
}

function New-KbStaticNavigationPageHtml {
    return @'
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>知识库全景导航</title>
<link rel="stylesheet" href="./_assets/graph/graph.css">
<style>
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; width: 100%; height: 100%; overflow: hidden; background: #f3f8fc; }
#kb-nav-app { width: 100%; height: 100%; }
</style>
<script id="kb-nav-i18n">
(function () {
    var isZh = (function () {
        if (typeof window !== 'undefined' && window.location && window.location.search) {
            try {
                var params = new URLSearchParams(window.location.search);
                var q = params.get('lang');
                if (q === 'en') return false;
                if (q === 'zh') return true;
            } catch (e) {}
        }
        var nav = (typeof navigator !== 'undefined' && ((navigator.languages && navigator.languages[0]) || navigator.language || navigator.userLanguage)) || '';
        return nav.toLowerCase().startsWith('zh');
    })();
    if (!isZh) {
        document.documentElement.lang = 'en';
        document.title = 'Knowledge Base Panoramic Navigation';
    }
})();
</script>
<script defer src="./_assets/graph/graph-data.js"></script>
<script defer src="./_assets/graph/graph-previews.js"></script>
<script defer src="./_assets/graph/graph.js"></script>
<script defer>
document.addEventListener('DOMContentLoaded', function () {
    var container = document.getElementById('kb-nav-app');
    if (container && window.mountKbGraph) {
        window.mountKbGraph(container, {
            mode: 'standalone',
            outputBaseUrl: '.'
        });
    }
});
</script>
</head>
<body>
<div id="kb-nav-app"></div>
</body>
</html>
'@
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

function Get-KbStaticGraphAssetRecords {
    param([Parameter(Mandatory)][string]$AssetsRoot)

    $assetsFull = [IO.Path]::GetFullPath($AssetsRoot)
    $files = @(Get-KbStaticSafeAssetFiles -Root $assetsFull -Label 'bundled Graph assets')
    foreach ($required in @('graph.css', 'graph.js')) {
        $requiredPath = Join-Path $assetsFull ($required.Replace('/', [IO.Path]::DirectorySeparatorChar))
        if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) { throw "BLOCKER: bundled Graph asset is missing: $required" }
    }
    return @($files | Sort-Object FullName | ForEach-Object {
        $relative = Get-KbStaticRelativePath -Base $assetsFull -Path $_.FullName
        [pscustomobject][ordered]@{
            source_path = 'assets/graph/' + $relative
            source_relative_path = $relative
            output_path = '_assets/graph/' + $relative
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

    $defaultGraphAssetsRoot = Join-Path (Split-Path -Parent $PSScriptRoot) 'assets\graph'
    $effectiveGraphAssetsRoot = if ([string]::IsNullOrWhiteSpace($GraphAssetsRoot)) { $defaultGraphAssetsRoot } else { $GraphAssetsRoot }
    $graphAssets = @(Get-KbStaticGraphAssetRecords -AssetsRoot $effectiveGraphAssetsRoot)

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
    $markdownFiles = @($contentFiles | Where-Object { $_.Extension -ieq '.md' } | Sort-Object FullName)
    $inboxCount = @($contentFiles | Where-Object { $_.Extension -ieq '.md' -and ((Get-KbStaticRelativePath -Base $contentRoot -Path $_.FullName) -match '(?i)^inbox[\\/]') }).Count
    # Validate the complete navigation graph before any destination creation or copying.
    $navigation = Get-KbStaticNavigationModel -MarkdownFiles $markdownFiles -ContentRoot $contentRoot -EntrySourcePath $entrypointFull

    # Extract whole-KB GraphData and PreviewData
    $graphModel = Get-KbGraphModel -ContentRoot $contentRoot -Navigation $navigation -MarkdownFiles $markdownFiles
    $pageNodeIds = @{}
    foreach ($node in $graphModel.GraphData.nodes) {
        if ($node.kind -eq 'page') {
            $pageNodeIds[[string]$node.page.source_path] = [string]$node.id
        }
    }

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
    $previousGraphAssets = @{}
    $previousGraphDataAssets = @{}
    $previousGraph = $null
    if ($null -ne $previous) {
        foreach ($page in @($previous.pages)) { $previousPages[[string]$page.source_path] = $page }
        foreach ($directory in @($previous.directories)) { $previousDirectories[[string]$directory.output_path] = $directory }
        if ($null -ne $previous.PSObject.Properties['katex']) {
            foreach ($asset in @($previous.katex.assets)) { $previousKatexAssets[[string]$asset.source_path] = $asset }
        }
        if ($null -ne $previous.PSObject.Properties['graph']) {
            $previousGraph = $previous.graph
            if ($null -ne $previousGraph.PSObject.Properties['assets']) {
                foreach ($asset in @($previousGraph.assets)) { $previousGraphAssets[[string]$asset.source_path] = $asset }
            }
            if ($null -ne $previousGraph.PSObject.Properties['data_assets']) {
                foreach ($asset in @($previousGraph.data_assets)) { $previousGraphDataAssets[[string]$asset.output_path] = $asset }
            }
        }
    }
    $stateMatches = $null -ne $previous -and $previous.generator_version -eq $generatorVersion -and $previous.template_version -eq $templateVersion -and $null -ne $previous.PSObject.Properties['navigation_digest'] -and $previous.navigation_digest -eq $navigation.Digest
    $katexStateMatches = $null -ne $previous -and $null -ne $previous.PSObject.Properties['katex'] -and $previous.katex.asset_version -eq $katexAssetVersion
    $graphStateMatches = $null -ne $previousGraph -and $previousGraph.asset_version -eq $graphAssetVersion

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
    if ($currentOutputPaths.ContainsKey('kb-navigation.html')) {
        throw 'BLOCKER: source contains reserved navigation page name: kb-navigation.html'
    }
    $currentOutputPaths['kb-navigation.html'] = $true

    $previousOwnedOutputs = @{}
    $previousRecordsToCheck = @($previousPages.Values) + @($previousDirectories.Values) + @($previousKatexAssets.Values) + @($previousGraphAssets.Values) + @($previousGraphDataAssets.Values)
    if ($null -ne $previousGraph -and $null -ne $previousGraph.PSObject.Properties['navigation_page'] -and $null -ne $previousGraph.navigation_page.output_path) {
        $previousRecordsToCheck += $previousGraph.navigation_page
    }
    foreach ($record in $previousRecordsToCheck) {
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
    $graphPreflightPaths = @()
    foreach ($asset in $graphAssets) { $graphPreflightPaths += $asset.output_path }
    $graphPreflightPaths += '_assets/graph/graph-data.js'
    $graphPreflightPaths += '_assets/graph/graph-previews.js'
    foreach ($relative in $graphPreflightPaths) {
        $candidate = [IO.Path]::GetFullPath((Join-Path $destinationFull ($relative.Replace('/', [IO.Path]::DirectorySeparatorChar))))
        if (-not (Test-KbStaticPathInside -Candidate $candidate -Base $destinationFull)) { throw "BLOCKER: Graph asset output path escapes destination: $relative" }
        if (Test-Path -LiteralPath $candidate -PathType Container) { throw "BLOCKER: Graph asset output is an existing directory: $relative" }
        if ((Test-Path -LiteralPath $candidate -PathType Leaf) -and -not $previousOwnedOutputs.ContainsKey($relative)) {
            throw "BLOCKER: refusing to overwrite destination file not owned by a prior static-site manifest: $relative"
        }
    }

    $generated = [Collections.Generic.List[string]]::new()
    $skipped = [Collections.Generic.List[string]]::new()
    $removed = [Collections.Generic.List[string]]::new()
    $assetGenerated = [Collections.Generic.List[string]]::new()
    $assetSkipped = [Collections.Generic.List[string]]::new()
    $assetRecords = [Collections.Generic.List[object]]::new()
    $graphAssetGenerated = [Collections.Generic.List[string]]::new()
    $graphAssetSkipped = [Collections.Generic.List[string]]::new()
    $graphAssetRecords = [Collections.Generic.List[object]]::new()
    $graphDataAssetRecords = [Collections.Generic.List[object]]::new()

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

    foreach ($asset in $graphAssets) {
        $outputPath = Join-Path $destinationFull ($asset.output_path.Replace('/', [IO.Path]::DirectorySeparatorChar))
        $old = if ($previousGraphAssets.ContainsKey($asset.source_path)) { $previousGraphAssets[$asset.source_path] } else { $null }
        $canSkip = -not $Force.IsPresent -and $graphStateMatches -and $null -ne $old -and $old.sha256 -eq $asset.sha256 -and $old.output_path -eq $asset.output_path -and (Test-Path -LiteralPath $outputPath -PathType Leaf)
        if ($canSkip -and $null -ne $old.PSObject.Properties['output_sha256']) {
            $canSkip = ([string]$old.output_sha256 -eq (Get-KbStaticSha256 -Path $outputPath))
        }
        if ($canSkip) {
            $outputHash = Get-KbStaticSha256 -Path $outputPath
            $graphAssetSkipped.Add($asset.output_path)
        }
        else {
            $parent = Split-Path -Parent $outputPath
            if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
            [IO.File]::Copy($asset.full_path, $outputPath, $true)
            $outputHash = Get-KbStaticSha256 -Path $outputPath
            if ($outputHash -ne $asset.sha256) { throw "BLOCKER: copied Graph asset hash does not match source: $($asset.source_path)" }
            $graphAssetGenerated.Add($asset.output_path)
        }
        $graphAssetRecords.Add([pscustomobject][ordered]@{ source_path = $asset.source_path; output_path = $asset.output_path; sha256 = $asset.sha256; output_sha256 = $outputHash })
    }

    # Generate or skip _assets/graph/graph-data.js
    $graphDataOutputPath = '_assets/graph/graph-data.js'
    $graphDataFullPath = Join-Path $destinationFull ($graphDataOutputPath.Replace('/', [IO.Path]::DirectorySeparatorChar))
    $oldGraphData = if ($previousGraphDataAssets.ContainsKey($graphDataOutputPath)) { $previousGraphDataAssets[$graphDataOutputPath] } else { $null }
    $canSkipGraphData = -not $Force.IsPresent -and $null -ne $previousGraph -and $previousGraph.graph_digest -eq $graphModel.GraphData.graph_digest -and (Test-Path -LiteralPath $graphDataFullPath -PathType Leaf)
    if ($canSkipGraphData -and $null -ne $oldGraphData -and $null -ne $oldGraphData.PSObject.Properties['output_sha256']) {
        $canSkipGraphData = ([string]$oldGraphData.output_sha256 -eq (Get-KbStaticSha256 -Path $graphDataFullPath))
    }
    if ($canSkipGraphData) {
        $graphDataOutputHash = Get-KbStaticSha256 -Path $graphDataFullPath
        $graphAssetSkipped.Add($graphDataOutputPath)
    }
    else {
        $parent = Split-Path -Parent $graphDataFullPath
        if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
        $graphDataJs = ConvertTo-KbGraphJavaScript -GraphData $graphModel.GraphData
        [IO.File]::WriteAllText($graphDataFullPath, $graphDataJs, [Text.UTF8Encoding]::new($false))
        $graphDataOutputHash = Get-KbStaticSha256 -Path $graphDataFullPath
        $graphAssetGenerated.Add($graphDataOutputPath)
    }
    $graphDataAssetRecords.Add([pscustomobject][ordered]@{
        source_path = 'generated:graph-data.js'
        output_path = $graphDataOutputPath
        output_sha256 = $graphDataOutputHash
    })

    # Generate or skip _assets/graph/graph-previews.js
    $graphPreviewsOutputPath = '_assets/graph/graph-previews.js'
    $graphPreviewsFullPath = Join-Path $destinationFull ($graphPreviewsOutputPath.Replace('/', [IO.Path]::DirectorySeparatorChar))
    $oldGraphPreviews = if ($previousGraphDataAssets.ContainsKey($graphPreviewsOutputPath)) { $previousGraphDataAssets[$graphPreviewsOutputPath] } else { $null }
    $canSkipGraphPreviews = -not $Force.IsPresent -and $null -ne $previousGraph -and $previousGraph.preview_digest -eq $graphModel.PreviewData.preview_digest -and (Test-Path -LiteralPath $graphPreviewsFullPath -PathType Leaf)
    if ($canSkipGraphPreviews -and $null -ne $oldGraphPreviews -and $null -ne $oldGraphPreviews.PSObject.Properties['output_sha256']) {
        $canSkipGraphPreviews = ([string]$oldGraphPreviews.output_sha256 -eq (Get-KbStaticSha256 -Path $graphPreviewsFullPath))
    }
    if ($canSkipGraphPreviews) {
        $graphPreviewsOutputHash = Get-KbStaticSha256 -Path $graphPreviewsFullPath
        $graphAssetSkipped.Add($graphPreviewsOutputPath)
    }
    else {
        $parent = Split-Path -Parent $graphPreviewsFullPath
        if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
        $graphPreviewsJs = ConvertTo-KbGraphPreviewsJavaScript -PreviewData $graphModel.PreviewData
        [IO.File]::WriteAllText($graphPreviewsFullPath, $graphPreviewsJs, [Text.UTF8Encoding]::new($false))
        $graphPreviewsOutputHash = Get-KbStaticSha256 -Path $graphPreviewsFullPath
        $graphAssetGenerated.Add($graphPreviewsOutputPath)
    }
    $graphDataAssetRecords.Add([pscustomobject][ordered]@{
        source_path = 'generated:graph-previews.js'
        output_path = $graphPreviewsOutputPath
        output_sha256 = $graphPreviewsOutputHash
    })

    # Generate or skip kb-navigation.html
    $navPageOutputPath = 'kb-navigation.html'
    $navPageFullPath = Join-Path $destinationFull $navPageOutputPath
    $oldNavPage = if ($null -ne $previousGraph -and $null -ne $previousGraph.PSObject.Properties['navigation_page']) { $previousGraph.navigation_page } else { $null }
    $canSkipNavPage = -not $Force.IsPresent -and $stateMatches -and $null -ne $oldNavPage -and $oldNavPage.output_path -eq $navPageOutputPath -and (Test-Path -LiteralPath $navPageFullPath -PathType Leaf)
    if ($canSkipNavPage -and $null -ne $oldNavPage.PSObject.Properties['output_sha256']) {
        $canSkipNavPage = ([string]$oldNavPage.output_sha256 -eq (Get-KbStaticSha256 -Path $navPageFullPath))
    }
    if ($canSkipNavPage) {
        $navPageOutputHash = Get-KbStaticSha256 -Path $navPageFullPath
        $skipped.Add($navPageOutputPath)
    }
    else {
        $navPageHtml = New-KbStaticNavigationPageHtml
        [IO.File]::WriteAllText($navPageFullPath, $navPageHtml, [Text.UTF8Encoding]::new($false))
        $navPageOutputHash = Get-KbStaticSha256 -Path $navPageFullPath
        $generated.Add($navPageOutputPath)
    }
    $navigationPageRecord = [pscustomobject][ordered]@{
        output_path = $navPageOutputPath
        output_sha256 = $navPageOutputHash
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
            $ownerPageId = if ($pageNodeIds.ContainsKey($sourceRelative)) { $pageNodeIds[$sourceRelative] } else { '' }
            $anchorResult = Update-KbHeadingAnchors -Html $rendered.Html -OwnerPageId $ownerPageId -SourcePath $sourceRelative
            $isHome = ($sourceRelative -eq $entrypointRelative)
            $title = $navigation.Pages[$sourceRelative].Title
            $html = New-KbStaticHtmlDocument -Title $title -BodyHtml $anchorResult.Html -OutputRelative $outputRelative -Navigation $navigation -SourceRelative $sourceRelative -IsHome:$isHome -PageNodeId $ownerPageId -InboxCount $inboxCount
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
            $directoryTitles = @{ projects = '全部项目'; maps = '全部主题'; knowledge = '全部知识条目'; sources = '全部来源'; decisions = '全部决策'; inbox = '收件箱'; archive = '归档'; assets = '附件' }
            $isTypeDirectory = $directoryTitles.ContainsKey($directoryRelative)
            $children = if ($isTypeDirectory) {
                @(Get-ChildItem -LiteralPath $directory -Recurse -File -Force | Where-Object { $_.Extension -ieq '.md' } | Sort-Object FullName)
            } else {
                @(Get-ChildItem -LiteralPath $directory -Force | Sort-Object @{ Expression = { -not $_.PSIsContainer } }, Name)
            }
            foreach ($child in $children) {
                $childRelative = Get-KbStaticRelativePath -Base $contentRoot -Path $child.FullName
                if ($child.PSIsContainer) {
                    $href = Get-KbStaticNavigationHref -FromOutput $outputRelative -ToOutput ($childRelative + '/index.html')
                    $label = if ($directoryTitles.ContainsKey($childRelative)) { $directoryTitles[$childRelative] } else { $child.Name + '/' }
                }
                elseif ($child.Extension -ieq '.md') {
                    $href = Get-KbStaticNavigationHref -FromOutput $outputRelative -ToOutput $navigation.Pages[$childRelative].Output
                    $label = $navigation.Pages[$childRelative].Title
                }
                else { continue }
                $items.Add('<li><a href="' + [System.Net.WebUtility]::HtmlEncode($href) + '">' + [System.Net.WebUtility]::HtmlEncode($label) + '</a></li>')
            }
            $heading = if ([string]::IsNullOrEmpty($directoryRelative) -or $directoryRelative -eq '.') { '文件目录' } elseif ($isTypeDirectory) { $directoryTitles[$directoryRelative] } else { Split-Path -Leaf $directory }
            $bodyContent = if ($isTypeDirectory -and $directoryRelative -eq 'inbox' -and $items.Count -eq 0) {
                '<h1>' + [System.Net.WebUtility]::HtmlEncode($heading) + '</h1><p class="kb-inbox-empty" style="color:#60758a;margin:1.5rem 0;">收件箱为空，暂无待整理笔记。</p>'
            } else {
                '<h1>' + [System.Net.WebUtility]::HtmlEncode($heading) + '</h1><ul>' + ($items -join "`n") + '</ul>'
            }
            $html = New-KbStaticHtmlDocument -Title $heading -BodyHtml $bodyContent -OutputRelative $outputRelative -Navigation $navigation -IsHome:$false -PageNodeId ''
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

    $currentGraphSources = @{}
    foreach ($asset in $graphAssets) { $currentGraphSources[$asset.source_path] = $true }
    foreach ($oldAsset in $previousGraphAssets.Values) {
        if ($currentGraphSources.ContainsKey([string]$oldAsset.source_path)) { continue }
        $relative = [string]$oldAsset.output_path
        if ([string]::IsNullOrWhiteSpace($relative) -or $relative -notmatch '^_assets/graph(?:/|$)' -or [IO.Path]::IsPathRooted($relative) -or $relative -match '(^|[\\/])\.\.([\\/]|$)') { continue }
        $candidate = [IO.Path]::GetFullPath((Join-Path $destinationFull ($relative.Replace('/', [IO.Path]::DirectorySeparatorChar))))
        if (-not (Test-KbStaticPathInside -Candidate $candidate -Base $destinationFull) -or -not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        if ($null -eq $oldAsset.PSObject.Properties['output_sha256'] -or [string]::IsNullOrWhiteSpace([string]$oldAsset.output_sha256)) { continue }
        if ((Get-KbStaticSha256 -Path $candidate) -ne [string]$oldAsset.output_sha256) { continue }
        Remove-Item -LiteralPath $candidate -Force
        $removed.Add($relative)
    }

    $newManifest = [pscustomobject][ordered]@{
        schema = 'knowledge-base-static-site'
        schema_version = 1
        generator_version = $generatorVersion
        template_version = $templateVersion
        navigation_digest = $navigation.Digest
        root_content_dir = $contentRoot
        entry_source_path = $entrypointRelative
        entry_output_path = $entryOutputRelative
        generated_utc = [DateTime]::UtcNow.ToString('o')
        katex = [pscustomobject][ordered]@{
            asset_version = $katexAssetVersion
            assets = @($assetRecords | Sort-Object source_path)
        }
        graph = [pscustomobject][ordered]@{
            asset_version = $graphAssetVersion
            graph_digest = $graphModel.GraphData.graph_digest
            preview_digest = $graphModel.PreviewData.preview_digest
            navigation_page = $navigationPageRecord
            assets = @($graphAssetRecords | Sort-Object source_path)
            data_assets = @($graphDataAssetRecords | Sort-Object output_path)
        }
        pages = @($pageRecords | Sort-Object source_path)
        directories = @($directoryRecords | Sort-Object output_path)
    }
    $newManifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding UTF8 -NoNewline
    [pscustomobject][ordered]@{
        status = 'success'; root = $rootFull; destination = $destinationFull; manifest = $manifestName; entry_page = (Join-Path $destinationFull ($entryOutputRelative.Replace('/', [IO.Path]::DirectorySeparatorChar)))
        generator_version = $generatorVersion; template_version = $templateVersion
        force_rebuild = [bool]$Force.IsPresent
        generated = $generated.Count; generated_paths = @($generated); skipped = $skipped.Count; skipped_paths = @($skipped); removed = $removed.Count; removed_paths = @($removed)
        assets_generated = $assetGenerated.Count; assets_generated_paths = @($assetGenerated); assets_skipped = $assetSkipped.Count; assets_skipped_paths = @($assetSkipped)
        graph_assets_generated = $graphAssetGenerated.Count; graph_assets_generated_paths = @($graphAssetGenerated); graph_assets_skipped = $graphAssetSkipped.Count; graph_assets_skipped_paths = @($graphAssetSkipped)
    } | ConvertTo-Json -Depth 6
}
catch {
    [pscustomobject][ordered]@{ status = 'blocked'; message = $_.Exception.Message } | ConvertTo-Json -Depth 4
    exit 2
}
