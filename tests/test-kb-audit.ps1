[CmdletBinding()]
param(
    [string]$PythonExecutable = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$auditScript = Join-Path $projectRoot 'knowledge-base-manager\scripts\kb-audit.ps1'
$shellPath = (Get-Command pwsh -ErrorAction Stop).Source
$testRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("knowledge-base-manager-tests-" + [guid]::NewGuid().ToString('N'))

function Write-Utf8File {
    param([string]$Path, [string]$Content)

    $parent = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    Set-Content -LiteralPath $Path -Value $Content -Encoding UTF8 -NoNewline
}

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) {
        throw "Assertion failed: $Message"
    }
}

function Invoke-AuditJson {
    param([string]$Root)

    if (-not [string]::IsNullOrWhiteSpace($PythonExecutable)) {
        $kbScript = Join-Path $projectRoot 'knowledge-base-manager\scripts\kb.py'
        $output = & $PythonExecutable -B -X utf8 $kbScript --format json audit --root $Root --profile legacy
        $exitCode = $LASTEXITCODE
        $env = (($output -join [Environment]::NewLine) | ConvertFrom-Json)
        if ($null -eq $env -or $env.schema_version -ne 1 -or $env.command -ne 'audit') {
            throw "Invalid Python audit envelope: $output"
        }
        return [pscustomobject]@{
            ExitCode = $exitCode
            Data     = $env.data
        }
    }

    $output = & $shellPath -NoProfile -File $auditScript -Root $Root -Format Json
    $exitCode = $LASTEXITCODE
    return [pscustomobject]@{
        ExitCode = $exitCode
        Data     = (($output -join [Environment]::NewLine) | ConvertFrom-Json)
    }
}

try {
    $validRoot = Join-Path $testRoot 'valid'
    $externalSource = Join-Path $testRoot 'project\evidence.md'
    Write-Utf8File $externalSource @'
# External project evidence
'@
    $externalSourceUri = $externalSource.Replace('\', '/')
    Write-Utf8File (Join-Path $validRoot 'kb.yaml') @'
schema_version: 1
content_dir: content
entrypoint: content/index.md
'@
    Write-Utf8File (Join-Path $validRoot 'content\index.md') @'
# Knowledge Base

- [Unicode entry](knowledge/多言語 note.md)

Valid math: $\mathrm{GF}(2^8)$ and $\tau_x = \alpha x$.
'@
    Write-Utf8File (Join-Path $validRoot 'content\knowledge\多言語 note.md') @"
---
id: kb-20260830-a1b2
type: concept
status: draft
created: 2026-08-30
updated: 2026-08-30
---
# 多言語 note

Valid content. [External source](https://example.com/reference).

External local source (outside knowledge base; machine-specific) <!-- kb-external-local -->: [evidence.md]($externalSourceUri); verified: 2026-08-30; version-state: unversioned.
"@

    $valid = Invoke-AuditJson -Root $validRoot
    Assert-True ($valid.ExitCode -eq 0) "valid fixture should exit 0, got $($valid.ExitCode)"
    Assert-True ($valid.Data.errors -eq 0) 'valid fixture should have no errors'
    Assert-True ($valid.Data.warnings -eq 0) 'a complete labeled external local source should not produce a warning'

    # The configured homepage may expose real top-level type inventories without
    # turning directory links in other contexts into collection membership.
    $directoryRoot = Join-Path $testRoot 'homepage-directories'
    Write-Utf8File (Join-Path $directoryRoot 'kb.yaml') "schema_version: 1`ncontent_dir: content`nentrypoint: content/home/start.md`n"
    $typeNames = @('projects','maps','knowledge','sources','decisions','inbox','archive','assets')
    foreach ($name in $typeNames) { New-Item -ItemType Directory -Path (Join-Path $directoryRoot "content/$name") -Force | Out-Null }
    $homepagePath = Join-Path $directoryRoot 'content/home/start.md'
    $typeLinks = ($typeNames | ForEach-Object { "- [Type](../$_/)" }) -join "`n"
    $homepageText = "# Home`n`n$typeLinks`n"
    Write-Utf8File $homepagePath $homepageText
    $allowedDirectories = Invoke-AuditJson $directoryRoot
    Assert-True ($allowedDirectories.ExitCode -eq 0 -and $allowedDirectories.Data.warnings -eq 0) 'existing type directories outside collections on a nested configured homepage are permitted'

    New-Item -ItemType Directory -Path (Join-Path $directoryRoot 'content/misc') -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $directoryRoot 'content/knowledge/sub') -Force | Out-Null
    Write-Utf8File (Join-Path $directoryRoot 'content/knowledge/uncollected.md') @'
---
id: kb-20260908-a123
type: concept
status: draft
created: 2026-09-08
updated: 2026-09-08
---
# Uncollected
'@
    Write-Utf8File (Join-Path $directoryRoot 'content/inbox/note.md') "# Inbox note`n[Directory](../knowledge/)`n"
    $restrictedLinks = @'

<!-- kb-nav:children:start -->
- [Not a collection child](../knowledge/)
<!-- kb-nav:children:end -->

- [Unknown directory](../misc/)
- [Subdirectory](../knowledge/sub/)
- [Query](../projects/?q=1)
- [Fragment](../projects/#part)
- [Root path](/projects/)
- ![Image](../assets/)
'@
    Write-Utf8File $homepagePath ($homepageText + $restrictedLinks)
    $restrictedDirectories = Invoke-AuditJson $directoryRoot
    $directoryIssues = @($restrictedDirectories.Data.issues | Where-Object code -eq 'DIRECTORY_LINK')
    Assert-True ($restrictedDirectories.Data.errors -eq 0 -and $directoryIssues.Count -eq 8) 'collection, other-page, unknown, nested, query, fragment, root-path and image directories retain warnings'
    Assert-True (@($directoryIssues | Where-Object file -eq 'inbox/note.md').Count -eq 1) 'a non-homepage directory link is never exempt'
    Assert-True (@($restrictedDirectories.Data.issues | Where-Object { $_.code -eq 'ORPHAN_ENTRY' -and $_.file -eq 'knowledge/uncollected.md' }).Count -eq 1) 'homepage type-directory links must not hide orphan entries'

    # Markers in fenced examples do not hide a later real homepage type link.
    $fencedExample = @'
# Home

````markdown
<!-- kb-nav:children:start -->
```
[Example only](../misc/)
<!-- kb-nav:children:end -->
````

[Real type link](../knowledge/)
'@
    Write-Utf8File $homepagePath $fencedExample
    $fencedDirectories = Invoke-AuditJson $directoryRoot
    Assert-True (@($fencedDirectories.Data.issues | Where-Object { $_.file -eq 'home/start.md' -and $_.code -eq 'DIRECTORY_LINK' }).Count -eq 0) 'nested fence-like text and sample markers must not change the real link context'

    foreach ($badMarkers in @(
        "<!-- kb-nav:children:start -->`n",
        "<!-- kb-nav:children:end -->`n",
        "<!-- kb-nav:children:start -->`n<!-- kb-nav:children:start -->`n<!-- kb-nav:children:end -->`n<!-- kb-nav:children:end -->`n",
        "<!-- kb-nav:children:start -->`n<!-- kb-nav:children:end -->`n<!-- kb-nav:children:start -->`n<!-- kb-nav:children:end -->`n"
    )) {
        Write-Utf8File $homepagePath ("# Home`n[Before](../knowledge/)`n" + $badMarkers + "`n[After](../projects/)`n")
        $malformedDirectories = Invoke-AuditJson $directoryRoot
        Assert-True (@($malformedDirectories.Data.issues | Where-Object { $_.file -eq 'home/start.md' -and $_.code -eq 'DIRECTORY_LINK' }).Count -eq 2) 'malformed declarations disable the homepage exception conservatively'
    }
    # Existence checks run before the exception, including recognized type names.
    Remove-Item -LiteralPath (Join-Path $directoryRoot 'content/maps')
    Write-Utf8File $homepagePath "# Home`n[Missing type](../maps/)`n[Outside](../../outside/)`n"
    $missingDirectories = Invoke-AuditJson $directoryRoot
    Assert-True (@($missingDirectories.Data.issues | Where-Object code -eq 'LINK_BROKEN').Count -eq 1) 'missing known type directory remains a broken link'
    Assert-True (@($missingDirectories.Data.issues | Where-Object code -eq 'LINK_ESCAPES_CONTENT').Count -eq 1) 'escaping directory remains an error'

    $invalidRoot = Join-Path $testRoot 'invalid'
    Write-Utf8File (Join-Path $invalidRoot 'kb.yaml') @'
schema_version: 1
content_dir: content
entrypoint: content/index.md
'@
    Write-Utf8File (Join-Path $invalidRoot 'content\index.md') @'
# Knowledge Base

- [First](knowledge/first.md)
- [Second](knowledge/second.md)
- [Missing fields](knowledge/missing-fields.md)
'@
    Write-Utf8File (Join-Path $invalidRoot 'content\knowledge\first.md') @'
---
id: kb-20260830-dead
type: concept
status: draft
created: 2026-08-30
updated: 2026-08-30
---
# First

[Broken](does-not-exist.md)

[Unlabeled local source](C:/project/evidence.md)
'@
    Write-Utf8File (Join-Path $invalidRoot 'content\knowledge\second.md') @'
---
id: kb-20260830-dead
type: method
status: draft
created: 2026-08-30
updated: 2026-08-30
---
# Second
'@
    Write-Utf8File (Join-Path $invalidRoot 'content\knowledge\missing-fields.md') @'
# Missing fields
'@
    Write-Utf8File (Join-Path $invalidRoot 'content\inbox\draft conflicted copy.md') @'
# Conflicted capture
'@

    $invalid = Invoke-AuditJson -Root $invalidRoot
    $codes = @($invalid.Data.issues | ForEach-Object code)
    Assert-True ($invalid.ExitCode -eq 2) "invalid fixture should exit 2, got $($invalid.ExitCode)"
    Assert-True ($codes -contains 'ID_DUPLICATE') 'duplicate ID should be detected'
    Assert-True ($codes -contains 'LINK_BROKEN') 'broken link should be detected'
    Assert-True ($codes -contains 'FRONT_MATTER_MISSING') 'missing front matter should be detected'
    Assert-True ($codes -contains 'SYNC_CONFLICT_COPY') 'sync conflict copy should be detected'
    Assert-True ($codes -contains 'ABSOLUTE_LOCAL_LINK') 'unlabeled local absolute link should be detected'

    $provenanceRoot = Join-Path $testRoot 'provenance'
    Write-Utf8File (Join-Path $provenanceRoot 'kb.yaml') @'
schema_version: 1
content_dir: content
entrypoint: content/index.md
'@
    Write-Utf8File (Join-Path $provenanceRoot 'content\index.md') @'
# Knowledge Base

- [Provenance](knowledge/provenance.md)
'@
    Write-Utf8File (Join-Path $provenanceRoot 'content\knowledge\provenance.md') @'
---
id: kb-20260830-cafe
type: source
status: draft
created: 2026-08-30
updated: 2026-08-30
---
# Provenance

External local source (outside knowledge base; machine-specific) <!-- kb-external-local -->: [missing date](C:/project/missing-date.md); version-state: unknown.

External local source (outside knowledge base; machine-specific) <!-- kb-external-local -->: [bad date](C:/project/bad-date.md); verified: 2026-02-30.
'@

    $provenance = Invoke-AuditJson -Root $provenanceRoot
    $provenanceCodes = @($provenance.Data.issues | ForEach-Object code)
    Assert-True ($provenance.ExitCode -eq 0) 'provenance metadata findings should remain warnings'
    Assert-True ($provenanceCodes -contains 'SOURCE_VERIFIED_DATE_MISSING') 'missing source verification date should be detected'
    Assert-True ($provenanceCodes -contains 'SOURCE_VERIFIED_DATE_INVALID') 'invalid source verification date should be detected'
    Assert-True ($provenanceCodes -contains 'SOURCE_VERSION_STATE_MISSING') 'missing source revision or version state should be detected'
    Assert-True ($provenanceCodes -notcontains 'ABSOLUTE_LOCAL_LINK') 'explicitly labeled external local links should not be treated as accidental absolute links'

    $mathRoot = Join-Path $testRoot 'math-code-spans'
    Write-Utf8File (Join-Path $mathRoot 'kb.yaml') @'
schema_version: 1
content_dir: content
entrypoint: content/index.md
'@
    Write-Utf8File (Join-Path $mathRoot 'content\index.md') @'
# Knowledge Base

- [Math misuse](knowledge/math-misuse.md)
'@
    Write-Utf8File (Join-Path $mathRoot 'content\knowledge\math-misuse.md') @'
---
id: kb-20260831-c0de
type: concept
status: draft
created: 2026-08-31
updated: 2026-08-31
---
# Math misuse

`GF(2^8)`

`tau_x = alpha*x`

`delta(x)`

`P(X=x | accepted)`

`\alpha + \beta`

`x ∈ GF(2^8)`

Benign literal spans: `identifier`, `LITERATURE`, `d-SNI`, `Get-Item`, `C:\temp\file.txt`, and `foo()`.

Intentional literal math-like code: `GF(2^8)` <!-- kb-literal-code -->

```text
`tau_x = alpha*x`
```
'@

    $mathAudit = Invoke-AuditJson -Root $mathRoot
    $mathIssues = @($mathAudit.Data.issues | Where-Object code -eq 'MATH_CODE_SPAN')
    Assert-True ($mathAudit.ExitCode -eq 2) "math code-span fixture should exit 2, got $($mathAudit.ExitCode)"
    Assert-True ($mathIssues.Count -eq 6) "the six high-confidence math code spans should be detected exactly once; found $($mathIssues.Count)"
    Assert-True ((@($mathIssues | ForEach-Object target) -join "`n") -match 'GF\(2\^8\)') 'GF(2^8) code-span misuse should be detected'
    Assert-True ((@($mathIssues | ForEach-Object target) -join "`n") -match 'tau_x = alpha\*x') 'subscript equation code-span misuse should be detected'
    Assert-True ((@($mathIssues | ForEach-Object target) -join "`n") -match 'delta\(x\)') 'mathematical delta function code-span misuse should be detected'
    Assert-True ((@($mathIssues | ForEach-Object target) -join "`n") -match 'P\(X=x \| accepted\)') 'conditional probability code-span misuse should be detected'
    Assert-True ((@($mathIssues | ForEach-Object target) -join "`n") -match '\\alpha') 'LaTeX command code-span misuse should be detected'
    Assert-True ((@($mathIssues | ForEach-Object target) -join "`n") -match '∈') 'Unicode math-symbol code-span misuse should be detected'

    $escapeRoot = Join-Path $testRoot 'escape'
    Write-Utf8File (Join-Path $escapeRoot 'kb.yaml') @'
schema_version: 1
content_dir: ../outside
entrypoint: ../outside/index.md
'@
    Write-Utf8File (Join-Path $testRoot 'outside\index.md') @'
# Outside
'@

    $escape = Invoke-AuditJson -Root $escapeRoot
    $escapeCodes = @($escape.Data.issues | ForEach-Object code)
    Assert-True ($escape.ExitCode -eq 3) "root-escaping fixture should exit 3, got $($escape.ExitCode)"
    Assert-True ($escapeCodes -contains 'CONTENT_DIR_ESCAPES_ROOT') 'escaping content_dir should be rejected'

    $junctionRoot = Join-Path $testRoot 'junction-kb'
    $junctionContent = Join-Path $testRoot 'junction-content'
    Write-Utf8File (Join-Path $junctionRoot 'kb.yaml') @'
schema_version: 1
content_dir: content
entrypoint: content/index.md
'@
    Write-Utf8File (Join-Path $junctionContent 'index.md') '# Redirected content'
    $contentJunction = Join-Path $junctionRoot 'content'
    New-Item -ItemType Junction -Path $contentJunction -Target $junctionContent | Out-Null
    $junctionAudit = Invoke-AuditJson -Root $junctionRoot
    Assert-True ($junctionAudit.ExitCode -eq 3) 'audit must reject a junction-backed content tree'
    Assert-True ((@($junctionAudit.Data.issues | ForEach-Object message) -join ' ') -match 'junction|symbolic link') 'junction rejection must explain the unsafe path'
    Remove-Item -LiteralPath $contentJunction -Force

    $manifestLinkRoot = Join-Path $testRoot 'manifest-link-kb'
    $manifestTarget = Join-Path $testRoot 'outside-kb.yaml'
    New-Item -ItemType Directory -Path $manifestLinkRoot -Force | Out-Null
    Write-Utf8File $manifestTarget "schema_version: 1`ncontent_dir: content`nentrypoint: content/index.md`n"
    $manifestLink = Join-Path $manifestLinkRoot 'kb.yaml'
    $createdManifestLink = $false
    try {
        New-Item -ItemType SymbolicLink -Path $manifestLink -Target $manifestTarget -ErrorAction Stop | Out-Null
        $createdManifestLink = $true
        $manifestLinkAudit = Invoke-AuditJson -Root $manifestLinkRoot
        Assert-True ($manifestLinkAudit.ExitCode -eq 3) 'audit must reject a symlinked kb.yaml before reading it'
        Assert-True ((@($manifestLinkAudit.Data.issues | ForEach-Object message) -join ' ') -match 'junction|symbolic link') 'symlinked manifest rejection must explain the unsafe path'
    }
    catch {
        if ($createdManifestLink) { throw }
        Write-Verbose 'File-symlink creation is unavailable; junction reparse coverage remains mandatory.'
    }
    finally {
        if ($createdManifestLink -and (Test-Path -LiteralPath $manifestLink)) { Remove-Item -LiteralPath $manifestLink -Force }
    }

    Write-Output 'kb-audit tests passed.'
    $global:LASTEXITCODE = 0
}
finally {
    if (Test-Path -LiteralPath $testRoot) {
        Remove-Item -LiteralPath $testRoot -Recurse -Force
    }
}
