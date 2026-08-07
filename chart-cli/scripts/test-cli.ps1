<#
.SYNOPSIS
    Check chart-cli, then open it.

.DESCRIPTION
    Checks the toolchain, syntax-checks the Node dashboard, drives the Python
    workflow server over its real NDJSON protocol with one request per supported
    kind (model status, model switch, ask, advisory), and then launches the
    dashboard in this terminal. Nothing is written outside a temp file, and no
    API key is used.

.PARAMETER CheckOnly
    Run the checks and exit without opening the dashboard, for CI.

.PARAMETER SkipWorkflow
    Skip the workflow protocol checks; toolchain and Node syntax only.

.EXAMPLE
    .\scripts\test-cli.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\test-cli.ps1 -CheckOnly
#>

[CmdletBinding()]
param(
    [switch]$CheckOnly,
    [switch]$SkipWorkflow
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$script:Passed = 0
$script:Failed = 0

function Write-Result {
    param([string]$Name, [bool]$Ok, [string]$Detail = '')
    if ($Ok) {
        $script:Passed++
        Write-Host "  PASS  $Name" -ForegroundColor Green
    }
    else {
        $script:Failed++
        Write-Host "  FAIL  $Name" -ForegroundColor Red
    }
    if ($Detail) { Write-Host "        $Detail" -ForegroundColor DarkGray }
}

function Test-Tool {
    param([string]$Name, [string]$VersionArgs)
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $command) {
        Write-Result "$Name on PATH" $false 'not found'
        return
    }
    $version = (& $Name $VersionArgs 2>&1 | Select-Object -First 1)
    Write-Result "$Name on PATH" $true "$version"
}

function New-Request {
    param([string]$Kind, [hashtable]$Payload)
    [pscustomobject]@{ kind = $Kind; payload = $Payload } |
        ConvertTo-Json -Depth 12 -Compress
}

function Get-Report {
    param([object[]]$Lines, [string]$Kind)
    foreach ($line in $Lines) {
        if ($line -notlike '@@REPORT@@ *') { continue }
        $report = $line.Substring(11) | ConvertFrom-Json
        if ($report.kind -eq $Kind) { return $report }
    }
    return $null
}

Push-Location $root
try {
    Write-Host ''
    Write-Host 'chart-cli startup checks' -ForegroundColor Cyan
    Write-Host "  root: $root" -ForegroundColor DarkGray
    Write-Host ''

    # --- toolchain --------------------------------------------------------
    Write-Host 'Toolchain' -ForegroundColor Cyan
    Test-Tool -Name 'node' -VersionArgs '--version'
    Test-Tool -Name 'uv'   -VersionArgs '--version'
    Write-Result 'node_modules installed' (Test-Path 'node_modules') 'run: pnpm install'
    Write-Result 'config.json present' (Test-Path 'config.json')

    # --- dashboard syntax -------------------------------------------------
    Write-Host ''
    Write-Host 'Dashboard' -ForegroundColor Cyan
    foreach ($file in Get-ChildItem 'src' -Filter '*.js' -File) {
        $output = & node --check $file.FullName 2>&1
        Write-Result "node --check src/$($file.Name)" ($LASTEXITCODE -eq 0) ($output -join ' ')
    }

    if (-not $SkipWorkflow) {
        # --- workflow protocol --------------------------------------------
        Write-Host ''
        Write-Host 'Workflow protocol' -ForegroundColor Cyan

        $history = @(280, 279, 277, 276, 274, 273, 272, 271, 270, 271)
        $rising = @(480, 484, 487, 489, 492, 495, 497, 499, 500, 500)
        $backtestHistory = @(1..250 | ForEach-Object { [double](100 + $_ * 0.5) })
        $snapshot = @{
            generated_at = (Get-Date).ToUniversalTime().ToString('o')
            period_label = '7D'
            period_days  = 7
            assets       = @(
                @{ symbol = 'AAPL'; kind = 'stock'; price = 271.0; change_pct = -2.5; history = $history },
                @{ symbol = 'MSFT'; kind = 'stock'; price = 500.0; change_pct = 1.5; history = $rising }
            )
        }

        $requests = @(
            (New-Request -Kind 'model' -Payload @{ action = 'status' }),
            (New-Request -Kind 'model' -Payload @{ action = 'set'; provider = 'offline' }),
            (New-Request -Kind 'ask' -Payload @{
                    question     = 'which symbol has the weakest momentum?'
                    focus_symbol = 'AAPL'
                    snapshot     = $snapshot
                }),
            (New-Request -Kind 'advisory' -Payload $snapshot),
            (New-Request -Kind 'backtest' -Payload @{
                    symbol         = 'MSFT'
                    kind_label     = 'stock'
                    criteria       = 'Generate a transparent 50/200 SMA and RSI(14) strategy.'
                    history        = $backtestHistory
                    timestamps     = @()
                    initial_capital = 10000
                    frame_delay_ms = 0
                    max_frames     = 10
                })
        )

        $requestFile = Join-Path ([System.IO.Path]::GetTempPath()) "chart-cli-requests-$PID.ndjson"
        $outFile = Join-Path ([System.IO.Path]::GetTempPath()) "chart-cli-reports-$PID.ndjson"
        $logFile = Join-Path ([System.IO.Path]::GetTempPath()) "chart-cli-workflow-$PID.log"
        # UTF-8 without a BOM: the server parses each line as JSON.
        [System.IO.File]::WriteAllLines($requestFile, [string[]]$requests, (New-Object System.Text.UTF8Encoding($false)))

        Write-Host '  starting the workflow server (this can take a while)...' -ForegroundColor DarkGray
        # cmd.exe does the redirection so native stderr never becomes a PowerShell error.
        $serve = 'uv run --project .. python -m signal_agent.run_agent --serve'
        & cmd.exe /c "$serve < ""$requestFile"" > ""$outFile"" 2> ""$logFile""" | Out-Null
        $lines = if (Test-Path $outFile) { @(Get-Content $outFile) } else { @() }

        $reports = @($lines | Where-Object { $_ -like '@@REPORT@@ *' })
        Write-Result 'workflow answered every request' ($reports.Count -ge 5) "$($reports.Count) report(s)"

        $model = Get-Report -Lines $lines -Kind 'model'
        Write-Result '/model returns a provider' ($null -ne $model -and $model.provider) `
            $(if ($model) { "provider=$($model.provider) mode=$($model.mode)" } else { 'no model report' })
        Write-Result '/model publishes the provider catalog' `
            ($null -ne $model -and $model.available.Count -gt 0 -and $model.default_api_key_var) `
            $(if ($model) { "available=$($model.available -join ',') key_var=$($model.default_api_key_var)" } else { '' })

        $ask = Get-Report -Lines $lines -Kind 'ask'
        Write-Result '/ask answers the typed question' ($null -ne $ask -and $ask.answer) `
            $(if ($ask) { "mode=$($ask.mode) answer=$($ask.answer.Substring(0, [Math]::Min(70, $ask.answer.Length)))..." } else { 'no ask report' })
        Write-Result '/ask echoes the question and stays grounded' `
            ($null -ne $ask -and $ask.question -eq 'which symbol has the weakest momentum?' -and $ask.highlights.Count -gt 0)

        $advisory = Get-Report -Lines $lines -Kind 'advisory'
        Write-Result 'advisory workflow returns rows' ($null -ne $advisory -and $advisory.rows.Count -gt 0) `
            $(if ($advisory) { "mode=$($advisory.mode) rows=$($advisory.rows.Count) risk=$($advisory.portfolio_risk)" } else { 'no advisory report' })

        $backtest = Get-Report -Lines $lines -Kind 'summary'
        Write-Result '/backtest requires an Agent Framework-generated strategy' ($null -ne $backtest -and $backtest.error -match 'chat provider is required') `
            $(if ($backtest) { "mode=$($backtest.mode) return=$($backtest.metrics.total_return_pct)% trades=$($backtest.metrics.trade_count)" } else { 'no backtest summary' })

        if (Test-Path $logFile) {
            $stderr = @(Get-Content $logFile | Where-Object { $_.Trim() })
            if ($stderr.Count -gt 0) {
                Write-Host ''
                Write-Host 'Workflow log' -ForegroundColor Cyan
                $stderr | Select-Object -First 10 | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
            }
        }
        Remove-Item $requestFile, $outFile, $logFile -ErrorAction SilentlyContinue
    }
}
finally {
    Write-Host ''
    $color = if ($script:Failed -eq 0) { 'Green' } else { 'Red' }
    Write-Host "$($script:Passed) passed, $($script:Failed) failed" -ForegroundColor $color
    Pop-Location
}

if ($script:Failed -gt 0) { exit 1 }
if ($CheckOnly) { return }

Write-Host ''
Write-Host 'Launching the dashboard. Inside it:' -ForegroundColor Cyan
Write-Host '  /  open the command prompt, then: /ask <question>, /backtest [SYMBOL], /model, /help' -ForegroundColor DarkGray
Write-Host '  ?  help    a  analyze    r  refresh    l  log    q  quit' -ForegroundColor DarkGray
Write-Host ''
if ([Console]::IsInputRedirected -or [Console]::IsOutputRedirected) {
    Write-Host 'The dashboard needs a real terminal; run this without redirection.' -ForegroundColor Yellow
    exit 1
}
Push-Location $root
try { & node 'src/index.js' } finally { Pop-Location }
