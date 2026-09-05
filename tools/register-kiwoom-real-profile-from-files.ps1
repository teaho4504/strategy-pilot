[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$AppKeyFile,

    [Parameter(Mandatory = $true)]
    [string]$SecretKeyFile,

    [string]$Alias = "real-account"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$cliPath = Join-Path $HOME ".local\bin\kiwoomcli.exe"

function Read-KiwoomCredentialFile {
    param([string]$Path, [string]$Label)

    $resolved = Resolve-Path -LiteralPath $Path -ErrorAction Stop
    $value = (Get-Content -Raw -LiteralPath $resolved.Path -Encoding UTF8).Trim()
    if (-not $value) {
        throw "$Label file is empty."
    }
    if ($value.Contains("`r") -or $value.Contains("`n")) {
        throw "$Label file must contain exactly one credential value."
    }
    return $value
}

if (-not (Test-Path -LiteralPath $cliPath -PathType Leaf)) {
    throw "kiwoomcli.exe was not found at $cliPath"
}

$appKey = Read-KiwoomCredentialFile -Path $AppKeyFile -Label "App Key"
$secretKey = Read-KiwoomCredentialFile -Path $SecretKeyFile -Label "Secret Key"
if ($appKey -eq $secretKey) {
    throw "App Key and Secret Key files contain the same value."
}

$previousAppKey = $env:APP_KEY
$previousAppSecret = $env:APP_SECRET
try {
    $env:APP_KEY = $appKey
    $env:APP_SECRET = $secretKey
    Write-Output "Credential files loaded securely. Values will not be displayed."
    & $cliPath auth login --alias $Alias --mode real
    if ($LASTEXITCODE -ne 0) {
        throw "Kiwoom CLI verification failed with exit code $LASTEXITCODE."
    }
} finally {
    if ($null -eq $previousAppKey) {
        Remove-Item Env:APP_KEY -ErrorAction SilentlyContinue
    } else {
        $env:APP_KEY = $previousAppKey
    }
    if ($null -eq $previousAppSecret) {
        Remove-Item Env:APP_SECRET -ErrorAction SilentlyContinue
    } else {
        $env:APP_SECRET = $previousAppSecret
    }
    $appKey = $null
    $secretKey = $null
}

Write-Output "Profile registration completed."
