[CmdletBinding()]
param(
    [string]$OutputDirectory = (Join-Path (Split-Path $PSScriptRoot -Parent) 'release\INDRA-Windows-x64'),
    [string]$InstallerExecutable = (Join-Path $env:TEMP 'indra-gnullvm-host-target\release\INDRA-Setup.exe')
)

$ErrorActionPreference = 'Stop'
$sourceRoot = (Resolve-Path (Split-Path $PSScriptRoot -Parent)).Path
$installer = (Resolve-Path $InstallerExecutable).Path
$output = [System.IO.Path]::GetFullPath($OutputDirectory)
$payload = Join-Path $output 'payload'

if (-not (Test-Path (Join-Path $sourceRoot 'pyproject.toml'))) {
    throw "Source root is invalid: $sourceRoot"
}
if ($output -eq $sourceRoot) {
    throw 'Output directory cannot be the repository root.'
}

New-Item -ItemType Directory -Force -Path $payload | Out-Null
Copy-Item -LiteralPath $installer -Destination (Join-Path $output 'INDRA-Setup.exe') -Force

$excludedDirectories = @(
    '.git', '.build-tools', '.pytest_cache', '.ruff_cache', '.mypy_cache',
    '__pycache__', 'node_modules', 'target', 'venv', '.venv', 'release'
)
$excludedFiles = @('.env', '.env.local', '.env.production')

function Test-ExcludedPath([string]$relativePath) {
    $parts = $relativePath -split '[\\/]'
    foreach ($part in $parts) {
        if ($excludedDirectories -contains $part) { return $true }
    }
    $leaf = $parts[-1]
    if ($excludedFiles -contains $leaf) { return $true }
    if ($leaf -match '\.(pyc|pyo|log|db-shm|db-wal)$') { return $true }
    return $false
}

$sourceDrive = [System.IO.Path]::GetPathRoot($sourceRoot)
$outputDrive = [System.IO.Path]::GetPathRoot($output)
$canHardLink = $sourceDrive -ieq $outputDrive
$fileCount = 0
$totalBytes = [int64]0

Get-ChildItem -LiteralPath $sourceRoot -File -Recurse -Force | ForEach-Object {
    $sourceFile = $_
    $relative = $sourceFile.FullName.Substring($sourceRoot.Length).TrimStart('\', '/')
    if (Test-ExcludedPath $relative) { return }

    $destination = Join-Path $payload $relative
    $destinationParent = Split-Path $destination -Parent
    if (-not (Test-Path -LiteralPath $destinationParent)) {
        New-Item -ItemType Directory -Force -Path $destinationParent | Out-Null
    }

    if (Test-Path -LiteralPath $destination) {
        Remove-Item -LiteralPath $destination -Force
    }

    if ($canHardLink) {
        try {
            New-Item -ItemType HardLink -Path $destination -Target $sourceFile.FullName | Out-Null
        } catch {
            Copy-Item -LiteralPath $sourceFile.FullName -Destination $destination -Force
        }
    } else {
        Copy-Item -LiteralPath $sourceFile.FullName -Destination $destination -Force
    }
    $fileCount++
    $totalBytes += $sourceFile.Length
}

$readme = @"
INDRA WINDOWS OFFLINE RELEASE
=============================

Keep INDRA-Setup.exe and the payload folder together.
Double-click INDRA-Setup.exe and follow the setup screen.

Minimum requirements
--------------------
- Windows 10 or Windows 11, 64-bit
- 16 GB RAM minimum; 32 GB recommended for local models
- 30 GB free disk space minimum (more for additional models)
- WebView2 Runtime (included with current Windows 10/11 updates)
- No pre-existing Python virtual environment is required
- Internet access during first-time setup for Python, Node/Electron, and
  Python/JavaScript package dependencies. This build is not yet a fully
  disconnected installer; provision through an approved network channel.

Security behavior
-----------------
- Python environments are created fresh on the destination computer.
- Personal .env files, logs, databases, caches, and old virtual environments
  are not included in this release.
- The installer uses the adjacent local application/model payload and fails
  closed if it is missing or incomplete.
- Runtime network restrictions must be enforced separately by deployment
  policy and firewall rules. Do not assume this installer enforces air gap.
- Approved Artifactory endpoints can be configured separately for controlled
  package/model retrieval.

This executable is not code-signed. Windows may show a publisher warning.
Validate SHA256SUMS.txt before transferring or running the release.
Perform a clean-machine installation test before distributing to users.

Release contents: $fileCount files, $([math]::Round($totalBytes / 1GB, 2)) GB
"@
Set-Content -LiteralPath (Join-Path $output 'README-FIRST.txt') -Value $readme -Encoding UTF8

$checksums = Get-ChildItem -LiteralPath $output -File | Where-Object Name -ne 'SHA256SUMS.txt' | ForEach-Object {
    $hash = Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName
    "$($hash.Hash.ToLowerInvariant())  $($_.Name)"
}
Set-Content -LiteralPath (Join-Path $output 'SHA256SUMS.txt') -Value $checksums -Encoding ASCII

Write-Host "INDRA release ready: $output"
Write-Host "Payload: $fileCount files, $([math]::Round($totalBytes / 1GB, 2)) GB"
