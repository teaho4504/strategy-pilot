[CmdletBinding()]
param(
    [switch]$Restart
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$backendPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$nodeExe = "C:\Users\windows\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
$viteScript = Join-Path $repoRoot "node_modules\vite\bin\vite.js"
$backendEnv = Join-Path $repoRoot "backend\.env"
$runDirectory = Join-Path $repoRoot ".run"
$pinFile = Join-Path $runDirectory "dashboard.pin"

function Set-EnvironmentLine {
    param([string[]]$Lines, [string]$Name, [string]$Value)

    $replacement = "$Name=$Value"
    $pattern = "^" + [regex]::Escape($Name) + "="
    $found = $false
    $updated = @(foreach ($line in $Lines) {
        if ($line -match $pattern) {
            if (-not $found) {
                $replacement
                $found = $true
            }
        } else {
            $line
        }
    })
    if (-not $found) {
        $updated += $replacement
    }
    return @($updated)
}

function Stop-ProjectListener {
    param([int]$Port, [string]$ExpectedCommand)

    $listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    foreach ($listener in $listeners) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" -ErrorAction SilentlyContinue
        if (-not $process -or $process.CommandLine -notmatch $ExpectedCommand) {
            throw "Port $Port is owned by a non-project process. Refusing to stop it."
        }
        Stop-Process -Id $listener.OwningProcess -Force
    }
}

function Wait-HttpOk {
    param([string]$Uri, [int]$Attempts = 30)

    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
                return
            }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    throw "Local service did not become ready: $Uri"
}

function Test-LocalTcpPort {
    param([int]$Port)

    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $result = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        if (-not $result.AsyncWaitHandle.WaitOne(500)) {
            return $false
        }
        $client.EndConnect($result)
        return $true
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Set-PrivateRuntimeFileAcl {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return
    }
    $owner = (Get-Acl -LiteralPath $Path).Owner
    $grants = @(
        "${owner}:(M)",
        "*S-1-5-18:(F)",
        "*S-1-5-32-544:(F)"
    )
    $sandboxGroup = Get-LocalGroup -Name "CodexSandboxUsers" -ErrorAction SilentlyContinue
    if ($sandboxGroup -and $sandboxGroup.SID) {
        $grants += "*$($sandboxGroup.SID.Value):(R)"
    }
    & icacls.exe $Path /inheritance:r /grant:r $grants | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to restrict runtime file permissions: $Path"
    }
}

if (-not (Test-Path -LiteralPath $backendPython -PathType Leaf)) {
    throw "Backend Python was not found: $backendPython"
}
if (-not (Test-Path -LiteralPath $nodeExe -PathType Leaf)) {
    throw "Node.js was not found: $nodeExe"
}
if (-not (Test-Path -LiteralPath $viteScript -PathType Leaf)) {
    throw "Vite was not found: $viteScript"
}

New-Item -ItemType Directory -Path $runDirectory -Force | Out-Null
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$backendWasListening = Test-LocalTcpPort -Port 8000
$shouldRotateDashboardPin = $Restart -or -not $backendWasListening

if ($shouldRotateDashboardPin) {
    # Issue a fresh PIN whenever a new backend process will start. Keeping the
    # existing PIN while an already-running backend is reused avoids a file /
    # process mismatch that would lock the user out until the next restart.
    $bytes = New-Object byte[] 4
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $dashboardPin = (([BitConverter]::ToUInt32($bytes, 0) % 90000000) + 10000000).ToString()
    [System.IO.File]::WriteAllText($pinFile, $dashboardPin, $utf8NoBom)
} elseif (Test-Path -LiteralPath $pinFile -PathType Leaf) {
    $dashboardPin = (Get-Content -Raw -LiteralPath $pinFile).Trim()
} else {
    throw "Dashboard PIN file is missing while the backend is already running. Restart the local server to rotate and recover the PIN."
}

$envLines = if (Test-Path -LiteralPath $backendEnv) {
    @(Get-Content -LiteralPath $backendEnv -Encoding UTF8)
} else {
    @()
}
$safeValues = [ordered]@{
    "KIWOOM_MODE" = "live"
    "KIWOOM_READ_ONLY" = "true"
    "KIWOOM_ENABLE_ORDER" = "false"
    "KIWOOM_US_ENABLE_ORDER" = "false"
    "KIWOOM_US_ALLOWED_SYMBOLS" = "NVDA"
    "KIWOOM_US_MAX_ORDER_QUANTITY" = "1"
    "KIWOOM_US_MAX_ORDER_NOTIONAL" = "500"
    "KIWOOM_US_CAPITAL_USAGE_PCT" = "50"
    "KIWOOM_US_AUTOTRADE_RUNNER_ENABLED" = "false"
    "KIWOOM_US_ORDER_STATE_MONITOR_ENABLED" = "false"
    "DASHBOARD_ACCESS_PIN" = $dashboardPin
    "BACKEND_CORS_ORIGINS" = "http://localhost:8080,http://127.0.0.1:8080"
    "BACKEND_ALLOWED_CLIENT_IPS" = "127.0.0.1,::1"
    "BACKEND_TRUST_PROXY_HEADERS" = "false"
    "BACKEND_AUTH_RATE_LIMIT" = "6/60"
    "BACKEND_ORDER_RATE_LIMIT" = "3/60"
}
foreach ($entry in $safeValues.GetEnumerator()) {
    $envLines = Set-EnvironmentLine -Lines $envLines -Name $entry.Key -Value $entry.Value
}
$serializedEnv = (($envLines | ForEach-Object { [string]$_ }) -join [Environment]::NewLine) + [Environment]::NewLine
[System.IO.File]::WriteAllText($backendEnv, $serializedEnv, $utf8NoBom)
Set-PrivateRuntimeFileAcl -Path $pinFile
Set-PrivateRuntimeFileAcl -Path $backendEnv

if ($Restart) {
    Stop-ProjectListener -Port 8000 -ExpectedCommand "uvicorn"
    Stop-ProjectListener -Port 8080 -ExpectedCommand "vite"
}

# Some desktop hosts inject both `Path` and `PATH`. Windows Start-Process treats
# them as duplicate dictionary keys, so normalize once before launching workers.
$normalizedProcessPath = $env:PATH
[Environment]::SetEnvironmentVariable("PATH", $null, "Process")
[Environment]::SetEnvironmentVariable("Path", $normalizedProcessPath, "Process")

if (-not (Test-LocalTcpPort -Port 8000)) {
    $previousBackendEnvironment = @{}
    try {
        foreach ($entry in $safeValues.GetEnumerator()) {
            $previousBackendEnvironment[$entry.Key] = [Environment]::GetEnvironmentVariable($entry.Key, "Process")
            [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, "Process")
        }
        Start-Process -FilePath $backendPython `
            -ArgumentList @("-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--host", "127.0.0.1", "--port", "8000") `
            -WorkingDirectory $repoRoot `
            -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $runDirectory "backend.out.log") `
            -RedirectStandardError (Join-Path $runDirectory "backend.err.log")
    } finally {
        foreach ($entry in $previousBackendEnvironment.GetEnumerator()) {
            [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, "Process")
        }
    }
}

if (-not (Test-LocalTcpPort -Port 8080)) {
    $previousApiBase = $env:VITE_API_BASE_URL
    $previousProxyTarget = $env:VITE_BACKEND_PROXY_TARGET
    try {
        $env:VITE_API_BASE_URL = "same-origin"
        $env:VITE_BACKEND_PROXY_TARGET = "http://127.0.0.1:8000"
        Start-Process -FilePath $nodeExe `
            -ArgumentList @(".\node_modules\vite\bin\vite.js", "--host", "127.0.0.1", "--port", "8080") `
            -WorkingDirectory $repoRoot `
            -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $runDirectory "frontend.out.log") `
            -RedirectStandardError (Join-Path $runDirectory "frontend.err.log")
    } finally {
        $env:VITE_API_BASE_URL = $previousApiBase
        $env:VITE_BACKEND_PROXY_TARGET = $previousProxyTarget
    }
}

Wait-HttpOk -Uri "http://127.0.0.1:8000/api/health"
Wait-HttpOk -Uri "http://127.0.0.1:8080/"

$profiles = Invoke-RestMethod `
    -Uri "http://127.0.0.1:8000/api/auth/kiwoom/profiles" `
    -Headers @{ "X-Dashboard-Pin" = $dashboardPin } `
    -TimeoutSec 5

Write-Output "LOCAL_DASHBOARD_READY=true"
Write-Output "FRONTEND_URL=http://127.0.0.1:8080"
Write-Output "BACKEND_URL=http://127.0.0.1:8000"
Write-Output "DASHBOARD_ACCESS_PIN=$dashboardPin"
Write-Output "KIWOOM_PROFILE_COUNT=$(@($profiles).Count)"
foreach ($profile in @($profiles)) {
    Write-Output "KIWOOM_PROFILE=$($profile.profile) mode=$($profile.mode) account=$($profile.accountLabel)"
}
