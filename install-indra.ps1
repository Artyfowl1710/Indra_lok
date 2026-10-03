<#
.SYNOPSIS
Master Setup Wizard for INDRA

.DESCRIPTION
This script sets up the virtual environments, installs all dependencies, configures the environment securely (embedding keys), and runs the model downloader. It also creates a Desktop shortcut for easy access.
#>

$ErrorActionPreference = 'Stop'
$rootDir = $PSScriptRoot
$backendDir = "$rootDir\SIH-26\hermes-agent\backend"
$agentDir = "$rootDir\SIH-26\hermes-agent"
$envFile = "$rootDir\SIH-26\.env"
$runtimeDir = "$rootDir\.indra-runtime"
$pythonInstallDir = "$runtimeDir\python"

function Get-Download($Uri, $Destination) {
    Write-Host "Downloading $Uri" -ForegroundColor DarkGray
    & curl.exe -L --fail --retry 3 --output $Destination $Uri
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $Destination) -or
        (Get-Item -LiteralPath $Destination).Length -eq 0) {
        throw "Download failed: $Uri"
    }
}

function Install-LlamaServer {
    $server = "$backendDir\bin\llama-server.exe"
    if (Test-Path $server) { return }
    Write-Host "Installing the official llama.cpp Windows CUDA 13 runtime..." -ForegroundColor Yellow
    $releases = Invoke-RestMethod -Headers @{ 'User-Agent' = 'Indra-Installer' } -Uri 'https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=10'
    $release = $releases | Where-Object {
        ($_.assets.name -match '^llama-.*-bin-win-cuda-13\..*-x64\.zip$') -and
        ($_.assets.name -match '^cudart-llama-bin-win-cuda-13\..*-x64\.zip$')
    } | Select-Object -First 1
    if (-not $release) { throw 'Could not find a complete Windows x64 CUDA 13 llama.cpp release.' }
    $asset = $release.assets | Where-Object { $_.name -match '^llama-.*-bin-win-cuda-13\..*-x64\.zip$' } | Select-Object -First 1
    $cudaAsset = $release.assets | Where-Object { $_.name -match '^cudart-llama-bin-win-cuda-13\..*-x64\.zip$' } | Select-Object -First 1
    $archive = "$runtimeDir\llama.cpp.zip"
    $cudaArchive = "$runtimeDir\llama.cpp-cuda.zip"
    $extract = "$runtimeDir\llama.cpp"
    Get-Download $asset.browser_download_url $archive
    Get-Download $cudaAsset.browser_download_url $cudaArchive
    if (Test-Path $extract) { Remove-Item -LiteralPath $extract -Recurse -Force }
    Expand-Archive -LiteralPath $archive -DestinationPath $extract
    Expand-Archive -LiteralPath $cudaArchive -DestinationPath $extract -Force
    Get-ChildItem -LiteralPath $extract -Recurse -File | Copy-Item -Destination "$backendDir\bin" -Force
    if (-not (Test-Path $server)) { throw 'llama-server.exe was not present in the downloaded archive.' }
}

function Install-WebDashboard {
    $nodeHome = "$runtimeDir\node-v24.11.0-win-x64"
    $nodeExe = "$nodeHome\node.exe"
    if (-not (Test-Path $nodeExe)) {
        $nodeArchive = "$runtimeDir\node.zip"
        Get-Download 'https://nodejs.org/dist/v24.11.0/node-v24.11.0-win-x64.zip' $nodeArchive
        Expand-Archive -LiteralPath $nodeArchive -DestinationPath $runtimeDir -Force
    }
    $oldPath = $env:Path
    try {
        $env:Path = "$nodeHome;$env:Path"
        Push-Location $agentDir
        try {
            & "$nodeHome\npm.cmd" install --workspace web
            if ($LASTEXITCODE -ne 0) { throw 'Web dependency installation failed.' }
            & "$nodeHome\npm.cmd" install --workspace ui-tui
            if ($LASTEXITCODE -ne 0) { throw 'Command Center dependency installation failed.' }
            & "$nodeHome\npm.cmd" run build -w web
            if ($LASTEXITCODE -ne 0) { throw 'Web dashboard build failed.' }
            & "$nodeHome\npm.cmd" run build -w ui-tui
            if ($LASTEXITCODE -ne 0) { throw 'Command Center build failed.' }
            New-Item -ItemType Directory -Force -Path "$agentDir\hermes_cli\tui_dist" | Out-Null
            Copy-Item -LiteralPath "$agentDir\ui-tui\dist\entry.js" -Destination "$agentDir\hermes_cli\tui_dist\entry.js" -Force
        } finally {
            Pop-Location
        }
    } finally {
        $env:Path = $oldPath
    }
}

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "       INDRA 2.0 INSTALLATION WIZARD      " -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# 1. Install a project-local Python toolchain
Write-Host "`n[1/9] Preparing project-local Python..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
$uvExe = "$runtimeDir\uv\uv.exe"
if (-not (Test-Path $uvExe)) {
    $uvArchive = "$runtimeDir\uv.zip"
    Get-Download 'https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip' $uvArchive
    Expand-Archive -LiteralPath $uvArchive -DestinationPath "$runtimeDir\uv" -Force
}
$env:UV_PYTHON_INSTALL_DIR = $pythonInstallDir
& $uvExe python install 3.12
if ($LASTEXITCODE -ne 0) { throw 'Project-local Python installation failed.' }

# 2. Setup Frontend Venv
Write-Host "`n[2/9] Setting up CLI environment..." -ForegroundColor Yellow
if (!(Test-Path "$rootDir\venv")) {
    & $uvExe venv --python 3.12 "$rootDir\venv"
}
& $uvExe pip install --python "$rootDir\venv\Scripts\python.exe" -e "$agentDir"

# Ensure the indra.exe binary exists for branding
if (Test-Path "$rootDir\venv\Scripts\hermes.exe") {
    Copy-Item "$rootDir\venv\Scripts\hermes.exe" "$rootDir\venv\Scripts\indra.exe" -Force
}

# 3. Setup Backend Venv
Write-Host "`n[3/9] Setting up Backend environment..." -ForegroundColor Yellow
if (!(Test-Path "$backendDir\venv")) {
    & $uvExe venv --python 3.12 "$backendDir\venv"
}
if (Test-Path "$backendDir\requirements.txt") {
    & $uvExe pip install --python "$backendDir\venv\Scripts\python.exe" -r "$backendDir\requirements.txt"
}

# 4. Native inference runtime
Write-Host "`n[4/9] Checking local inference runtime..." -ForegroundColor Yellow
Install-LlamaServer

# 4. Generate .env file dynamically
Write-Host "`n[5/9] Configuring Security & Environment..." -ForegroundColor Yellow
$vaultPath = "$rootDir\MyVault"
if (!(Test-Path $vaultPath)) {
    New-Item -ItemType Directory -Path $vaultPath | Out-Null
}

$envContent = @"
WORKBENCH_API_KEY=wb_live_1234567890abcdef1234567890abcdef
TERMINAL_ENV=local
OBSIDIAN_VAULT_PATH=$vaultPath
"@
Set-Content -Path $envFile -Value $envContent -Encoding utf8
Set-Content -Path "$backendDir\.env" -Value $envContent -Encoding utf8
Push-Location $backendDir
try { & "$backendDir\venv\Scripts\python.exe" "$backendDir\setup_local_admin.py" }
finally { Pop-Location }
Write-Host "Environment configured securely. Keys embedded." -ForegroundColor Green

# 5. Run Model Downloader
Write-Host "`n[6/9] Verifying local models..." -ForegroundColor Yellow
& "$rootDir\venv\Scripts\python.exe" "$rootDir\download_models.py"

# 7. Generate a location-correct model configuration
Write-Host "`n[7/9] Configuring local models..." -ForegroundColor Yellow
& "$backendDir\venv\Scripts\python.exe" "$backendDir\auto-configure-models.py"

Write-Host "`n[8/9] Building web dashboard..." -ForegroundColor Yellow
Install-WebDashboard

# 6. Create Desktop Shortcut
Write-Host "`n[9/9] Installing the Indra command and Desktop shortcut..." -ForegroundColor Yellow
$commandDir = Join-Path $env:LOCALAPPDATA 'Indra\bin'
New-Item -ItemType Directory -Force -Path $commandDir | Out-Null
$commandTarget = Join-Path $commandDir 'indra.cmd'
Set-Content -Path $commandTarget -Encoding ascii -Value "@echo off`r`ncall `"$rootDir\indra.cmd`" %*"
$legacyCommandDir = Join-Path $env:LOCALAPPDATA 'hermes\bin'
New-Item -ItemType Directory -Force -Path $legacyCommandDir | Out-Null
Set-Content -Path (Join-Path $legacyCommandDir 'indra.cmd') -Encoding ascii -Value "@echo off`r`ncall `"$rootDir\indra.cmd`" %*"
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
$pathParts = @($userPath -split ';' | Where-Object { $_ })
if ($pathParts -notcontains $commandDir) {
    [Environment]::SetEnvironmentVariable('Path', (($pathParts + $commandDir) -join ';'), 'User')
}
$wshShell = New-Object -ComObject WScript.Shell
$desktopPath = [System.Environment]::GetFolderPath('Desktop')
$shortcut = $wshShell.CreateShortcut("$desktopPath\INDRA Dashboard.lnk")
$shortcut.TargetPath = "powershell.exe"
$shortcut.Arguments = "-ExecutionPolicy Bypass -NoExit -File `"$rootDir\start-indra.ps1`""
$shortcut.IconLocation = "$rootDir\venv\Scripts\python.exe,0" # Default python icon
$shortcut.WorkingDirectory = $rootDir
$shortcut.Save()

Write-Host "`n==========================================" -ForegroundColor Green
Write-Host " INSTALLATION COMPLETE! " -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host "You can now start INDRA by double-clicking the 'INDRA Dashboard' shortcut on your Desktop." -ForegroundColor Cyan
