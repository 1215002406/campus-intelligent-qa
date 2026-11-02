#Requires -Version 5.1
[CmdletBinding()]
param()

. (Join-Path $PSScriptRoot 'Common.ps1')

try {
    $python = Get-ProjectPython
    $npm = Get-ProjectNpm
    Ensure-ProjectMySQL
    Push-Location $ProjectRoot
    try {
        Invoke-Checked $python @('-m', 'pytest', 'backend/tests')
        Push-Location (Join-Path $ProjectRoot 'frontend')
        try {
            Invoke-Checked $npm @('run', 'build')
        } finally {
            Pop-Location
        }
        Write-Host 'Backend tests and frontend production build passed.'
    } finally {
        Pop-Location
    }
} catch {
    Write-Error $_ -ErrorAction Continue
    exit 1
}
