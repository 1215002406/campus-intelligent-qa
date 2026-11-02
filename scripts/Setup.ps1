#Requires -Version 5.1
[CmdletBinding()]
param([string]$PythonPath)

. (Join-Path $PSScriptRoot 'Common.ps1')

try {
    Push-Location $ProjectRoot
    try {
        $node = Get-Command node -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $node) {
            throw 'Node.js 20.19 or newer is required. Install it and reopen PowerShell.'
        }
        Ensure-ProjectMySQL
        $nodeVersion = & $node.Source --version
        $nodeVersionValid = $nodeVersion -match '^v(\d+)\.(\d+)\.'
        if ($LASTEXITCODE -ne 0 -or -not $nodeVersionValid -or
            [int]$Matches[1] -lt 20 -or ([int]$Matches[1] -eq 20 -and [int]$Matches[2] -lt 19)) {
            throw "Node.js 20.19 or newer is required; found $nodeVersion."
        }
        $npm = Get-ProjectNpm

        $venvDirectory = Join-Path $ProjectRoot '.venv'
        $venvPython = Join-Path $venvDirectory 'Scripts\python.exe'
        if (Test-Path -LiteralPath $venvDirectory) {
            if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
                throw 'An incomplete .venv already exists. Move it aside before running setup again.'
            }
        } else {
            $pythonArguments = @()
            if ($PythonPath) {
                $pythonCommand = Get-Command $PythonPath -ErrorAction Stop | Select-Object -First 1
            } else {
                $pythonCommand = Get-Command py -ErrorAction SilentlyContinue | Select-Object -First 1
                if ($pythonCommand) {
                    $pythonArguments = @('-3.11')
                } else {
                    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue | Select-Object -First 1
                }
            }
            if (-not $pythonCommand) {
                throw 'Python 3.11 is required. Install it or pass -PythonPath C:\path\python.exe.'
            }
            Invoke-Checked $pythonCommand.Source ($pythonArguments + @('-c', 'import sys; assert sys.version_info[:2] == (3, 11), "Python 3.11 is required"'))
            Invoke-Checked $pythonCommand.Source ($pythonArguments + @('-m', 'venv', $venvDirectory))
        }
        Invoke-Checked $venvPython @('-c', 'import sys; assert sys.version_info[:2] == (3, 11), "Existing .venv must use Python 3.11"')
        Invoke-Checked $venvPython @('-m', 'pip', 'install', '-r', (Join-Path $ProjectRoot 'backend\requirements.txt'))

        Push-Location (Join-Path $ProjectRoot 'frontend')
        try {
            Invoke-Checked $npm @('ci')
        } finally {
            Pop-Location
        }

        foreach ($directory in @('data', 'uploads')) {
            $path = Join-Path $ProjectRoot $directory
            if (-not (Test-Path -LiteralPath $path)) {
                New-Item -ItemType Directory -Path $path | Out-Null
            }
        }
        $environmentFile = Join-Path $ProjectRoot 'backend\.env'
        if (-not (Test-Path -LiteralPath $environmentFile)) {
            Copy-Item -LiteralPath (Join-Path $ProjectRoot 'backend\.env.example') -Destination $environmentFile
        }
        Write-Host 'Dependencies installed. Run scripts/Configure.ps1, then start each service in its own terminal.'
    } finally {
        Pop-Location
    }
} catch {
    Write-Error $_ -ErrorAction Continue
    exit 1
}
