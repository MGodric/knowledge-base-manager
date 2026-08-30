#Requires -Version 7.0
Set-StrictMode -Version Latest

$script:KbIsWindows = [Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([Runtime.InteropServices.OSPlatform]::Windows)
if ($script:KbIsWindows -and $null -eq ('KnowledgeBaseManager.NativePathSafety' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace KnowledgeBaseManager {
    public static class NativePathSafety {
        [StructLayout(LayoutKind.Sequential)]
        private struct FileAttributeTagInfo {
            public uint FileAttributes;
            public uint ReparseTag;
        }

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern SafeFileHandle CreateFileW(
            string fileName, uint desiredAccess, uint shareMode, IntPtr securityAttributes,
            uint creationDisposition, uint flagsAndAttributes, IntPtr templateFile);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool GetFileInformationByHandleEx(
            SafeFileHandle file, int fileInformationClass,
            out FileAttributeTagInfo fileInformation, uint bufferSize);

        public static uint GetReparseTag(string path) {
            const uint ShareReadWriteDelete = 0x00000007;
            const uint OpenExisting = 3;
            const uint OpenReparsePoint = 0x00200000;
            const uint BackupSemantics = 0x02000000;
            using (SafeFileHandle handle = CreateFileW(
                path, 0, ShareReadWriteDelete, IntPtr.Zero, OpenExisting,
                OpenReparsePoint | BackupSemantics, IntPtr.Zero)) {
                if (handle.IsInvalid) throw new Win32Exception(Marshal.GetLastWin32Error());
                FileAttributeTagInfo info;
                if (!GetFileInformationByHandleEx(
                    handle, 9, out info, (uint)Marshal.SizeOf(typeof(FileAttributeTagInfo)))) {
                    throw new Win32Exception(Marshal.GetLastWin32Error());
                }
                return info.ReparseTag;
            }
        }
    }
}
'@
}

function Test-KbRedirectingReparsePoint {
    param([Parameter(Mandatory)][System.IO.FileSystemInfo]$Item)

    if (($Item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -eq 0) { return $false }

    if ($script:KbIsWindows) {
        # Windows marks path-redirection reparses (symlinks, junctions, mount
        # points, and compatible third-party name surrogates) with bit 29.
        # Cloud hydration and compression reparses do not use that bit.
        $tag = [KnowledgeBaseManager.NativePathSafety]::GetReparseTag($Item.FullName)
        if (($tag -band [uint32]0x20000000) -ne 0) { return $true }
        return $false
    }

    # On non-Windows platforms reject identified links and fail closed on an
    # opaque reparse because no portable tag distinction is available here.
    $linkType = $Item.PSObject.Properties['LinkType']
    if ($null -ne $linkType -and -not [string]::IsNullOrWhiteSpace([string]$linkType.Value)) { return $true }
    $target = $Item.PSObject.Properties['Target']
    if ($null -ne $target -and $null -ne $target.Value -and @($target.Value).Count -gt 0) { return $true }
    try {
        if ($null -ne $Item.ResolveLinkTarget($false)) { return $true }
    }
    catch {
        # Some non-link reparse providers do not support ResolveLinkTarget.
    }
    return $true
}

function Assert-KbNoRedirectingReparsePoint {
    param(
        [Parameter(Mandatory)][string]$Path,
        [string]$Label = 'path'
    )

    $full = [System.IO.Path]::GetFullPath($Path)
    $cursor = $full
    while (-not (Test-Path -LiteralPath $cursor)) {
        $parent = Split-Path -Parent $cursor
        if ([string]::IsNullOrWhiteSpace($parent) -or $parent -eq $cursor) { break }
        $cursor = $parent
    }
    while (-not [string]::IsNullOrWhiteSpace($cursor)) {
        if (Test-Path -LiteralPath $cursor) {
            $item = Get-Item -LiteralPath $cursor -Force -ErrorAction Stop
            if (Test-KbRedirectingReparsePoint $item) {
                throw "BLOCKER: $Label contains a junction or symbolic link: $cursor"
            }
        }
        $parent = Split-Path -Parent $cursor
        if ([string]::IsNullOrWhiteSpace($parent) -or $parent -eq $cursor) { break }
        $cursor = $parent
    }
    return $full
}

function Get-KbSafeTreeFiles {
    param(
        [Parameter(Mandatory)][string]$Root,
        [string]$Label = 'tree'
    )

    $rootFull = Assert-KbNoRedirectingReparsePoint -Path $Root -Label $Label
    if (-not (Test-Path -LiteralPath $rootFull -PathType Container)) {
        throw "BLOCKER: $Label is not a directory: $rootFull"
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
