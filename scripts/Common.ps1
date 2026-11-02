#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$ArgumentList = @()
    )
    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed (exit $LASTEXITCODE): $FilePath"
    }
}

function Get-ProjectPython {
    $python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw 'Project Python is missing. Run scripts/Setup.ps1 first.'
    }
    return $python
}

function Get-ProjectNpm {
    if ($env:CAMPUS_NPM_PATH) {
        if (-not (Test-Path -LiteralPath $env:CAMPUS_NPM_PATH -PathType Leaf)) {
            throw 'CAMPUS_NPM_PATH does not point to an npm executable.'
        }
        return $env:CAMPUS_NPM_PATH
    }
    foreach ($name in @('npm.cmd', 'npm')) {
        $command = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($command) {
            return $command.Source
        }
    }
    $node = Get-Command node -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($node) {
        $siblingNpm = Join-Path (Split-Path $node.Source -Parent) 'npm.cmd'
        if (Test-Path -LiteralPath $siblingNpm -PathType Leaf) {
            return $siblingNpm
        }
    }
    throw 'npm was not found. Install Node.js 20 LTS, or set CAMPUS_NPM_PATH to npm.cmd.'
}

function Ensure-ProjectMySQL {
    if (Get-NetTCPConnection -State Listen -LocalPort 3306 -ErrorAction SilentlyContinue) {
        return
    }

    foreach ($serviceName in @('MySQL84', 'MySQL', 'MariaDB')) {
        $service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
        if ($service) {
            try {
                Start-Service -Name $serviceName -ErrorAction Stop
            } catch {
                # A local process is sufficient when service control is unavailable.
            }
            break
        }
    }

    $deadline = (Get-Date).AddSeconds(20)
    do {
        if (Get-NetTCPConnection -State Listen -LocalPort 3306 -ErrorAction SilentlyContinue) {
            return
        }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $deadline)

    $mysqld = $env:CAMPUS_MYSQLD_PATH
    if (-not $mysqld) {
        $mysqld = 'C:\MySQL\mysql-8.4.9-winx64\bin\mysqld.exe'
    }
    if (-not (Test-Path -LiteralPath $mysqld -PathType Leaf)) {
        $command = Get-Command mysqld -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($command) {
            $mysqld = $command.Source
        }
    }
    if (-not (Test-Path -LiteralPath $mysqld -PathType Leaf)) {
        throw 'MySQL is not running and mysqld was not found. Set CAMPUS_MYSQLD_PATH to mysqld.exe.'
    }

    $config = $env:CAMPUS_MYSQL_CONFIG_PATH
    if (-not $config) {
        $config = 'C:\MySQL\my.ini'
    }
    if (-not (Test-Path -LiteralPath $config -PathType Leaf)) {
        throw 'MySQL configuration file was not found. Set CAMPUS_MYSQL_CONFIG_PATH to my.ini.'
    }

    Start-Process -FilePath $mysqld -ArgumentList @("--defaults-file=$config") -WindowStyle Hidden | Out-Null
    $deadline = (Get-Date).AddSeconds(20)
    do {
        if (Get-NetTCPConnection -State Listen -LocalPort 3306 -ErrorAction SilentlyContinue) {
            return
        }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $deadline)
    throw 'MySQL did not start on 127.0.0.1:3306.'
}
