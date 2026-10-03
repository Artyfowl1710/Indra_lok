<#
.SYNOPSIS
Single command to start the entire INDRA ecosystem.

.DESCRIPTION
This script will:
1. Auto-configure the model settings based on the GGUFs in the models folder.
2. Start the backend services (llama-swap and workbench) using start-backend.ps1.
3. Launch the frontend indra dashboard and open the browser.
#>

$ErrorActionPreference = 'Stop'
$rootDir = $PSScriptRoot
$backendDir = "$rootDir\SIH-26\hermes-agent\backend"
$indraExe = "$rootDir\venv\Scripts\indra.exe"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "           STARTING INDRA SYSTEM          " -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# 1. Run Auto-Configure
Write-Host "`n[1/3] Auto-configuring models..." -ForegroundColor Yellow
if (Test-Path "$backendDir\venv\Scripts\python.exe") {
    & "$backendDir\venv\Scripts\python.exe" "$backendDir\auto-configure-models.py"
} else {
    Write-Host "Backend venv not found. Please ensure setup is complete." -ForegroundColor Red
    exit 1
}

# 2. Start Backend using official script
Write-Host "`n[2/3] Starting Backend Services (llama-swap and workbench)..." -ForegroundColor Yellow
# Run start-backend.ps1 which handles logging and port checking safely
& "$backendDir\start-backend.ps1"
& "$backendDir\venv\Scripts\python.exe" "$backendDir\register_models.py"

Write-Host "Services are UP!" -ForegroundColor Green

# 3. Launch Dashboard
Write-Host "`n[3/3] Launching INDRA Dashboard..." -ForegroundColor Yellow

# Ensure CUDA runtime DLLs (cublas64_12.dll etc.) are findable by faster-whisper / ctranslate2
$cudaBinDir = "$backendDir\bin"
if (Test-Path $cudaBinDir) {
    $env:PATH = "$cudaBinDir;$env:PATH"
    Write-Host "CUDA runtime DLLs added to PATH from $cudaBinDir" -ForegroundColor DarkGray
}

if (Test-Path $indraExe) {
    Write-Host "Opening Dashboard in default browser..." -ForegroundColor Green
    Start-Job -ScriptBlock { Start-Sleep -Seconds 3; Start-Process "http://127.0.0.1:9119" } | Out-Null
    & $indraExe dashboard
} else {
    Write-Host "Frontend CLI (indra.exe) not found in $rootDir\venv\Scripts." -ForegroundColor Red
    exit 1
}
