#Requires -Version 5.1
[CmdletBinding()]
param()

. (Join-Path $PSScriptRoot 'Common.ps1')

try {
    $npm = Get-ProjectNpm
    Push-Location (Join-Path $ProjectRoot 'frontend')
    try {
        Invoke-Checked $npm @('run', 'dev', '--', '--host', '127.0.0.1', '--port', '5173', '--strictPort')
    } finally {
        Pop-Location
    }
} catch {
    Write-Error $_ -ErrorAction Continue
    exit 1
}
