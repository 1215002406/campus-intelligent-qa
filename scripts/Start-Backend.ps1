#Requires -Version 5.1
[CmdletBinding()]
param()

. (Join-Path $PSScriptRoot 'Common.ps1')

try {
    $python = Get-ProjectPython
    Ensure-ProjectMySQL
    if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot 'backend\.env') -PathType Leaf)) {
        throw 'backend/.env is missing. Run scripts/Configure.ps1 first.'
    }
    Push-Location $ProjectRoot
    try {
        Invoke-Checked $python @('-m', 'uvicorn', 'app.main:app', '--app-dir', 'backend', '--host', '127.0.0.1', '--port', '8000', '--workers', '1')
    } finally {
        Pop-Location
    }
} catch {
    Write-Error $_ -ErrorAction Continue
    exit 1
}
