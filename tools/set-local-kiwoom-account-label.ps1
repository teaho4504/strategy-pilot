[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Alias,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d{4}$')]
    [string]$AccountSuffix,

    [string]$AccountType = "위탁종합"
)

$ErrorActionPreference = "Stop"
$directory = Join-Path $HOME ".strategy-pilot"
$path = Join-Path $directory "kiwoom_profile_labels.json"
$labels = [ordered]@{}

if (Test-Path -LiteralPath $path -PathType Leaf) {
    $existing = Get-Content -Raw -LiteralPath $path -Encoding UTF8 | ConvertFrom-Json
    foreach ($property in $existing.PSObject.Properties) {
        $labels[$property.Name] = [string]$property.Value
    }
}

$labels[$Alias] = "****-$AccountSuffix [$AccountType]"
New-Item -ItemType Directory -Path $directory -Force | Out-Null
$json = $labels | ConvertTo-Json
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($path, $json, $utf8NoBom)

Write-Output "PROFILE_LABEL_UPDATED=$Alias ****-$AccountSuffix [$AccountType]"
