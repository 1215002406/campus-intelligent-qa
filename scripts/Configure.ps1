#Requires -Version 5.1
[CmdletBinding()]
param(
    [switch]$Force,
    [string]$DatabaseHost = '127.0.0.1',
    [ValidateRange(1, 65535)]
    [int]$DatabasePort = 3306,
    [string]$DatabaseName = 'campus_qa',
    [string]$DatabaseUser = 'campus_app'
)

. (Join-Path $PSScriptRoot 'Common.ps1')

function Read-LocalUsername {
    param([string]$Prompt)
    while ($true) {
        $username = (Read-Host $Prompt).Trim()
        if ($username.Length -ge 1 -and $username.Length -le 80) {
            return $username
        }
        Write-Host 'Use a username with 1 to 80 characters.'
    }
}

function Read-LocalPassword {
    param([string]$Prompt)
    while ($true) {
        $secure = Read-Host $Prompt -AsSecureString
        $pointer = [IntPtr]::Zero
        try {
            $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
            $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
            if ($password.Length -ge 1) {
                return $password
            }
            Write-Host 'Use a non-empty password.'
        } finally {
            if ($pointer -ne [IntPtr]::Zero) {
                [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
            }
            $secure.Dispose()
        }
    }
}

function ConvertTo-DotenvValue {
    param([string]$Value)
    return (ConvertTo-Json -InputObject $Value -Compress)
}

try {
    $environmentFile = Join-Path $ProjectRoot 'backend\.env'
    $exampleFile = Join-Path $ProjectRoot 'backend\.env.example'
    if (Test-Path -LiteralPath $environmentFile -PathType Leaf) {
        $existingLines = @([IO.File]::ReadAllLines($environmentFile))
    } else {
        $existingLines = @([IO.File]::ReadAllLines($exampleFile))
    }
    $existingDatabaseUrl = $null
    foreach ($line in $existingLines) {
        if ($line -match '^\s*(?:export\s+)?DATABASE_URL\s*=\s*(.*)$') {
            $databaseUrlValue = $Matches[1].Trim()
            if ($databaseUrlValue.Length -ge 2 -and
                (($databaseUrlValue.StartsWith('"') -and $databaseUrlValue.EndsWith('"')) -or
                 ($databaseUrlValue.StartsWith("'") -and $databaseUrlValue.EndsWith("'")))) {
                $databaseUrlValue = $databaseUrlValue.Substring(1, $databaseUrlValue.Length - 2)
            }
            if ($databaseUrlValue) {
                $existingDatabaseUrl = $databaseUrlValue
            }
        }
    }
    $credentialNames = 'ADMIN_USERNAME|ADMIN_PASSWORD|JWT_SECRET_KEY'
    foreach ($line in $existingLines) {
        if ($line -match "^\s*(?:export\s+)?(?:$credentialNames)\s*=\s*(.*)$") {
            $currentValue = $Matches[1].Trim()
            if ($currentValue -and $currentValue -notmatch '^(?:""|[\x27]{2})\s*(?:#.*)?$' -and $currentValue -notmatch '^#') {
                if (-not $Force) {
                    throw 'Credentials are already configured. Keep this file, or use Configure.ps1 -Force to replace credentials deliberately.'
                }
            }
        }
    }

    $adminUsername = Read-LocalUsername 'Administrator username'
    $adminPassword = Read-LocalPassword 'Administrator password (hidden, any non-empty length)'
    if ($existingDatabaseUrl) {
        $databaseUrl = $existingDatabaseUrl
    } else {
        $databasePassword = Read-LocalPassword 'MySQL application password (hidden)'
        $encodedUser = [Uri]::EscapeDataString($DatabaseUser)
        $encodedPassword = [Uri]::EscapeDataString($databasePassword)
        $databaseUrl = "mysql+pymysql://${encodedUser}:${encodedPassword}@${DatabaseHost}:${DatabasePort}/${DatabaseName}?charset=utf8mb4"
    }

    $random = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $secretBytes = New-Object byte[] 48
        $random.GetBytes($secretBytes)
        $secret = [Convert]::ToBase64String($secretBytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
    } finally {
        $random.Dispose()
    }

    $updatedNames = "$credentialNames|DATABASE_URL"
    $lines = @($existingLines | Where-Object { $_ -notmatch "^\s*(?:export\s+)?(?:$updatedNames)\s*=" })
    $lines += @(
        '',
        '# Local accounts and JWT key. Never commit this file.',
        ('ADMIN_USERNAME=' + (ConvertTo-DotenvValue $adminUsername)),
        ('ADMIN_PASSWORD=' + (ConvertTo-DotenvValue $adminPassword)),
        ('JWT_SECRET_KEY=' + (ConvertTo-DotenvValue $secret)),
        ('DATABASE_URL=' + (ConvertTo-DotenvValue $databaseUrl))
    )
    $temporaryFile = $environmentFile + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
    try {
        [IO.File]::WriteAllText($temporaryFile, ($lines -join "`n") + "`n", (New-Object Text.UTF8Encoding $false))
        Move-Item -LiteralPath $temporaryFile -Destination $environmentFile -Force
    } finally {
        if (Test-Path -LiteralPath $temporaryFile) {
            Remove-Item -LiteralPath $temporaryFile
        }
    }
    Write-Host 'Saved backend/.env. No passwords or JWT keys were printed. Restart the backend to apply configuration.'
} catch {
    Write-Error $_ -ErrorAction Continue
    exit 1
} finally {
    $adminPassword = $null
    $databasePassword = $null
    $databaseUrl = $null
    $secret = $null
    $secretBytes = $null
}
