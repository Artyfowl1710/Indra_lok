$ErrorActionPreference = 'Stop'
$rootDir = $PSScriptRoot
$backendDir = Join-Path $rootDir 'SIH-26\hermes-agent\backend'

function Test-LocalPort([int]$Port) {
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $task = $client.ConnectAsync('127.0.0.1', $Port)
        if (-not $task.Wait(500)) { return $false }
        return $client.Connected
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

if ((Test-LocalPort 8000) -and (Test-LocalPort 8100)) {
    exit 0
}

Write-Host 'Starting INDRA local inference backend...' -ForegroundColor Yellow
& (Join-Path $backendDir 'start-backend.ps1')

if (-not ((Test-LocalPort 8000) -and (Test-LocalPort 8100))) {
    throw 'INDRA backend did not become ready on ports 8000 and 8100.'
}

$registerScript = Join-Path $backendDir 'register_models.py'
$backendPython = Join-Path $backendDir 'venv\Scripts\python.exe'
if ((Test-Path -LiteralPath $registerScript) -and (Test-Path -LiteralPath $backendPython)) {
    & $backendPython $registerScript
    if ($LASTEXITCODE -ne 0) { throw 'INDRA model registration failed.' }
}

Write-Host 'INDRA backend is ready.' -ForegroundColor Green
