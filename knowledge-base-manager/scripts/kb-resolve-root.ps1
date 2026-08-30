#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [Alias('RequestedRoot')]
    [string]$RequestedPath,

    [string]$ProjectRoot = (Get-Location).Path,

    [string[]]$SourceRoot = @(),

    [ValidateRange(0, 8)]
    [int]$SearchDepth = 2,

    [switch]$AllowMissing
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'kb-path-safety.ps1')

function Get-CanonicalPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$BasePath
    )

    $combined = if ([System.IO.Path]::IsPathRooted($Path)) {
        $Path
    } else {
        Join-Path -Path $BasePath -ChildPath $Path
    }

    return [System.IO.Path]::GetFullPath($combined).TrimEnd('\', '/')
}

function Write-Result {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Status,

        [AllowNull()]
        [string]$ResolvedRoot,

        [Parameter(Mandatory = $true)]
        [bool]$Exists,

        [string[]]$Candidates = @(),

        [string[]]$SearchedRoots = @(),

        [Parameter(Mandatory = $true)]
        [string]$Reason,

        [Parameter(Mandatory = $true)]
        [int]$ExitCode
    )

    [pscustomobject]@{
        status = $Status
        resolved_root = $ResolvedRoot
        exists = $Exists
        candidates = @($Candidates)
        searched_roots = @($SearchedRoots)
        reason = $Reason
    } | ConvertTo-Json -Depth 4
    exit $ExitCode
}

$requested = $RequestedPath.Trim()
if ([string]::IsNullOrWhiteSpace($requested)) {
    Write-Result -Status 'invalid' -ResolvedRoot $null -Exists $false -Reason 'RequestedPath is empty.' -ExitCode 4
}

$project = Get-CanonicalPath -Path $ProjectRoot -BasePath (Get-Location).Path
if (-not (Test-Path -LiteralPath $project -PathType Container)) {
    Write-Result -Status 'invalid' -ResolvedRoot $null -Exists $false -Reason "ProjectRoot is not a directory: $project" -ExitCode 4
}
try { Assert-KbNoRedirectingReparsePoint -Path $project -Label 'ProjectRoot' | Out-Null }
catch { Write-Result -Status 'invalid' -ResolvedRoot $null -Exists $false -Reason $_.Exception.Message -ExitCode 4 }

$isAbsolute = [System.IO.Path]::IsPathRooted($requested)
$hasSeparator = $requested.Contains('\') -or $requested.Contains('/')
$isBareName = -not $isAbsolute -and -not $hasSeparator

if (-not $isBareName) {
    $exact = Get-CanonicalPath -Path $requested -BasePath $project
    if (Test-Path -LiteralPath $exact -PathType Container) {
        try { Assert-KbNoRedirectingReparsePoint -Path $exact -Label 'requested path' | Out-Null }
        catch { Write-Result -Status 'invalid' -ResolvedRoot $null -Exists $false -Candidates @($exact) -Reason $_.Exception.Message -ExitCode 4 }
        Write-Result -Status 'resolved' -ResolvedRoot $exact -Exists $true -Candidates @($exact) -Reason 'Resolved exact path.' -ExitCode 0
    }
    if (Test-Path -LiteralPath $exact) {
        Write-Result -Status 'invalid' -ResolvedRoot $null -Exists $false -Candidates @($exact) -Reason 'The exact target exists but is not a directory.' -ExitCode 4
    }
    if ($AllowMissing) {
        try { Assert-KbNoRedirectingReparsePoint -Path $exact -Label 'requested path' | Out-Null }
        catch { Write-Result -Status 'invalid' -ResolvedRoot $null -Exists $false -Candidates @($exact) -Reason $_.Exception.Message -ExitCode 4 }
        Write-Result -Status 'resolved_missing' -ResolvedRoot $exact -Exists $false -Candidates @($exact) -Reason 'Missing exact path resolved; creation still requires authorization.' -ExitCode 0
    }
    Write-Result -Status 'not_found' -ResolvedRoot $null -Exists $false -Candidates @($exact) -Reason 'The exact path does not exist.' -ExitCode 3
}

$rootsToSearch = if ($SourceRoot.Count -gt 0) { @($SourceRoot) } else { @($project) }
$searched = [System.Collections.Generic.List[string]]::new()
$matches = [System.Collections.Generic.List[string]]::new()
$visited = @{}
$matchKeys = @{}

foreach ($root in $rootsToSearch) {
    if ([string]::IsNullOrWhiteSpace($root)) {
        continue
    }

    $source = Get-CanonicalPath -Path $root -BasePath $project
    if (-not (Test-Path -LiteralPath $source -PathType Container)) {
        continue
    }
    try { Assert-KbNoRedirectingReparsePoint -Path $source -Label 'SourceRoot' | Out-Null }
    catch { continue }

    if (-not $searched.Contains($source)) {
        $searched.Add($source)
    }

    $queue = [System.Collections.Generic.Queue[object]]::new()
    $queue.Enqueue([pscustomobject]@{ Path = $source; Depth = 0 })
    while ($queue.Count -gt 0) {
        $node = $queue.Dequeue()
        $current = [string]$node.Path
        $depth = [int]$node.Depth
        $currentKey = $current.ToLowerInvariant()
        if ($visited.ContainsKey($currentKey)) {
            continue
        }
        $visited[$currentKey] = $true

        $currentItem = Get-Item -LiteralPath $current -Force
        $currentRedirects = Test-KbRedirectingReparsePoint $currentItem
        if (-not $currentRedirects -and (Split-Path -Leaf $current) -ieq $requested -and -not $matchKeys.ContainsKey($currentKey)) {
            $matchKeys[$currentKey] = $true
            $matches.Add($current)
        }

        if ($depth -ge $SearchDepth) {
            continue
        }

        $children = @(Get-ChildItem -LiteralPath $current -Directory -Force -ErrorAction SilentlyContinue)
        foreach ($child in $children) {
            $childPath = $child.FullName.TrimEnd('\', '/')
            $childKey = $childPath.ToLowerInvariant()
            $childRedirects = Test-KbRedirectingReparsePoint $child
            if (-not $childRedirects -and $child.Name -ieq $requested -and -not $matchKeys.ContainsKey($childKey)) {
                $matchKeys[$childKey] = $true
                $matches.Add($childPath)
            }
            if (-not $childRedirects) {
                $queue.Enqueue([pscustomobject]@{ Path = $childPath; Depth = ($depth + 1) })
            }
        }
    }
}

$reason = if ($matches.Count -eq 0) {
    'No exact directory-name match was found in the project source folders; confirm an absolute path before continuing.'
} else {
    "Found $($matches.Count) exact directory-name match(es); confirm one absolute path before continuing."
}

Write-Result -Status 'confirmation_required' -ResolvedRoot $null -Exists ($matches.Count -gt 0) -Candidates $matches.ToArray() -SearchedRoots $searched.ToArray() -Reason $reason -ExitCode 2
