[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

function Write-Check {
    param(
        [string]$Name,
        [bool]$Passed,
        [string]$Detail
    )

    $status = if ($Passed) { "OK" } else { "NEEDS_SETUP" }
    Write-Output ("[{0}] {1}: {2}" -f $status, $Name, $Detail)
}

$isWindows = [System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT
Write-Check "Windows" $isWindows ([System.Environment]::OSVersion.VersionString)

$uvCommand = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uvCommand) {
    $projectUv = Join-Path $repoRoot ".venv\Scripts\uv.exe"
    if (Test-Path -LiteralPath $projectUv -PathType Leaf) {
        $uvCommand = Get-Command $projectUv
    }
}
Write-Check "uv" ($null -ne $uvCommand) $(if ($uvCommand) { $uvCommand.Source } else { "Install uv by following the official Kiwoom guide." })

$cliCommand = Get-Command kiwoomcli -ErrorAction SilentlyContinue
if (-not $cliCommand) {
    $userCli = Join-Path $HOME ".local\bin\kiwoomcli.exe"
    if (Test-Path -LiteralPath $userCli -PathType Leaf) {
        $cliCommand = Get-Command $userCli
    }
}
Write-Check "kiwoomcli" ($null -ne $cliCommand) $(if ($cliCommand) { $cliCommand.Source } else { "Run: uv tool install kwcli" })

$configDirectory = Join-Path $env:LOCALAPPDATA "kiwoom\kiwoom"
$settingsPath = Join-Path $configDirectory "settings.json"
$settingsExists = Test-Path -LiteralPath $settingsPath -PathType Leaf
Write-Check "settings.json" $settingsExists $settingsPath

if ($cliCommand) {
    Write-Output ""
    Write-Output "Running the safe Kiwoom CLI auth status check."
    & $cliCommand.Source auth status
}

Write-Output ""
Write-Output "If setup is required, run 'kiwoomcli setup' in PowerShell."
Write-Output "The dashboard remains read-only; order, amend, and cancel actions stay blocked."
