<#
.SYNOPSIS
One-click bootstrap to set up local Summertime GPU Backend for single-box all-in-one mode.

.DESCRIPTION
Clones the official Summertime-Server repository (https://github.com/Artyfowl1710/Summertime-server)
into this directory, configures the Python virtual environment, and prepares model directories.
#>

$ErrorActionPreference = 'Stop'
$backendDir = $PSScriptRoot

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "      INDRA All-In-One Local Backend Setup Utility       " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$serverRepo = "https://github.com/Artyfowl1710/Summertime-server.git"
$tempClone = Join-Path $backendDir "temp_summertime"

Write-Host "`n[1/3] Cloning Summertime-Server from $serverRepo..." -ForegroundColor Yellow
if (Test-Path $tempClone) { Remove-Item -Recurse -Force $tempClone }
git clone $serverRepo $tempClone

Write-Host "`n[2/3] Merging backend files into $backendDir..." -ForegroundColor Yellow
Get-ChildItem -Path $tempClone -Exclude .git | ForEach-Object {
    Copy-Item -Path $_.FullName -Destination $backendDir -Recurse -Force
}
Remove-Item -Recurse -Force $tempClone

# Ensure models and bin directories exist
New-Item -ItemType Directory -Force -Path (Join-Path $backendDir "models") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $backendDir "bin") | Out-Null

Write-Host "`n[3/3] Setting up Python virtual environment..." -ForegroundColor Yellow
$venvDir = Join-Path $backendDir "venv"
if (-not (Test-Path $venvDir)) {
    python -m venv $venvDir
}

$venvPython = Join-Path $venvDir "Scripts\python.exe"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r (Join-Path $backendDir "requirements.txt")

Write-Host "`n[SUCCESS] Local GPU backend initialized successfully!" -ForegroundColor Green
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Place GGUF model files into: $backendDir\models" -ForegroundColor White
Write-Host "  2. Start backend services: powershell -ExecutionPolicy Bypass -File .\start-backend.ps1" -ForegroundColor White
