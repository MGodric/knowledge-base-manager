$ErrorActionPreference = 'Stop'

$scriptPath = Join-Path $PSScriptRoot '..\knowledge-base-manager\scripts\kb-resolve-root.ps1'
$fixture = Join-Path ([System.IO.Path]::GetTempPath()) ("kb-resolve-" + [guid]::NewGuid().ToString('N'))
$project = Join-Path $fixture 'project'
$name = '00_knowledge_base'

function Invoke-Resolver {
    param(
        [string]$RequestedPath,
        [string]$ProjectRoot,
        [string[]]$SourceRoot = @(),
        [int]$SearchDepth = 2,
        [switch]$AllowMissing
    )

    $arguments = @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', $scriptPath,
        '-RequestedPath', $RequestedPath,
        '-ProjectRoot', $ProjectRoot,
        '-SearchDepth', $SearchDepth
    )
    if ($SourceRoot.Count -gt 0) {
        $arguments += '-SourceRoot'
        $arguments += $SourceRoot
    }
    if ($AllowMissing) {
        $arguments += '-AllowMissing'
    }

    $output = & (Get-Command pwsh -ErrorAction Stop).Source @arguments
    $exitCode = $LASTEXITCODE
    return [pscustomobject]@{
        ExitCode = $exitCode
        Result = ($output | Out-String | ConvertFrom-Json)
    }
}

try {
    New-Item -ItemType Directory -Path $project -Force | Out-Null
    $sibling = Join-Path $fixture $name
    New-Item -ItemType Directory -Path $sibling -Force | Out-Null

    $unique = Invoke-Resolver -RequestedPath $name -ProjectRoot $project -SourceRoot $fixture
    if ($unique.ExitCode -ne 2 -or $unique.Result.status -ne 'confirmation_required' -or $unique.Result.candidates.Count -ne 1 -or $unique.Result.candidates[0] -ne $sibling) {
        throw 'A unique bare-name match did not require confirmation.'
    }

    $inside = Join-Path $project $name
    New-Item -ItemType Directory -Path $inside -Force | Out-Null
    $multiple = Invoke-Resolver -RequestedPath $name -ProjectRoot $project -SourceRoot $fixture
    if ($multiple.ExitCode -ne 2 -or $multiple.Result.status -ne 'confirmation_required' -or $multiple.Result.candidates.Count -ne 2) {
        throw 'Multiple bare-name matches did not require confirmation.'
    }

    Remove-Item -LiteralPath $sibling -Recurse -Force
    Remove-Item -LiteralPath $inside -Recurse -Force
    $missing = Invoke-Resolver -RequestedPath $name -ProjectRoot $project -SourceRoot $fixture
    if ($missing.ExitCode -ne 2 -or $missing.Result.status -ne 'confirmation_required' -or $missing.Result.candidates.Count -ne 0 -or (Test-Path -LiteralPath $inside)) {
        throw 'A missing bare name did not require confirmation or was created.'
    }

    $tooDeep = Join-Path (Join-Path (Join-Path $fixture 'level1') 'level2') $name
    New-Item -ItemType Directory -Path $tooDeep -Force | Out-Null
    $bounded = Invoke-Resolver -RequestedPath $name -ProjectRoot $project -SourceRoot $fixture -SearchDepth 2
    if ($bounded.ExitCode -ne 2 -or $bounded.Result.candidates.Count -ne 0) {
        throw 'Bare-name search exceeded its configured depth.'
    }

    $expanded = Invoke-Resolver -RequestedPath $name -ProjectRoot $project -SourceRoot $fixture -SearchDepth 3
    if ($expanded.ExitCode -ne 2 -or $expanded.Result.candidates.Count -ne 1 -or $expanded.Result.candidates[0] -ne $tooDeep) {
        throw 'Bare-name search did not honor an explicitly expanded depth.'
    }

    $exactMissing = Invoke-Resolver -RequestedPath $sibling -ProjectRoot $project -AllowMissing
    if ($exactMissing.ExitCode -ne 0 -or $exactMissing.Result.status -ne 'resolved_missing' -or $exactMissing.Result.resolved_root -ne $sibling) {
        throw 'An explicitly authorized missing absolute path was not resolved correctly.'
    }

    $redirectTarget = Join-Path $fixture 'redirect-target'
    $redirect = Join-Path $fixture 'redirected-kb'
    New-Item -ItemType Directory -Path $redirectTarget -Force | Out-Null
    New-Item -ItemType Junction -Path $redirect -Target $redirectTarget | Out-Null
    $redirectSearch = Invoke-Resolver -RequestedPath 'redirected-kb' -ProjectRoot $project -SourceRoot $fixture
    if ($redirectSearch.ExitCode -ne 2 -or $redirectSearch.Result.candidates.Count -ne 0) {
        throw 'Bare-name discovery exposed a directory junction as a knowledge-base candidate.'
    }
    $redirectExact = Invoke-Resolver -RequestedPath $redirect -ProjectRoot $project
    if ($redirectExact.ExitCode -ne 4 -or $redirectExact.Result.status -ne 'invalid' -or $redirectExact.Result.reason -notmatch 'junction|symbolic link') {
        throw 'Exact resolution did not reject a directory junction.'
    }
    Remove-Item -LiteralPath $redirect -Force

    Write-Output 'kb-resolve-root tests passed.'
    $global:LASTEXITCODE = 0
} finally {
    if (Test-Path -LiteralPath $fixture) {
        Remove-Item -LiteralPath $fixture -Recurse -Force
    }
}
