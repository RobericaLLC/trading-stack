# PowerShell script to start all trading stack services with proper env loading
Write-Host "Starting Trading Stack Services..." -ForegroundColor Green

# Check if .env exists
if (-not (Test-Path ".env")) {
    Write-Host "ERROR: .env file not found!" -ForegroundColor Red
    Write-Host "Please run: .\setup_env.ps1 to create one" -ForegroundColor Yellow
    exit 1
}

# Load environment variables from .env file into current session
Write-Host "Loading environment from .env file..." -ForegroundColor Cyan
Get-Content .env | ForEach-Object {
    if ($_ -match '^([^#].*)=(.*)$') {
        $key = $matches[1].Trim()
        $value = $matches[2].Trim()
        [System.Environment]::SetEnvironmentVariable($key, $value, [System.EnvironmentVariableTarget]::Process)
        Write-Host "  Set $key" -ForegroundColor Gray
    }
}

Write-Host ""
Write-Host "Market is OPEN! Starting services..." -ForegroundColor Green

# 1. Start feedd (market data feed) - this one was failing due to missing env vars
Write-Host "Starting feedd..." -ForegroundColor Yellow
$feeddCmd = @"
cd '$PWD'
Get-Content .env | ForEach-Object { if (`$_ -match '^([^#].*)=(.*)$') { [System.Environment]::SetEnvironmentVariable(`$matches[1].Trim(), `$matches[2].Trim(), [System.EnvironmentVariableTarget]::Process) } }
python -m trading_stack.services.feedd.main live-alpaca --symbol SPY --minutes 0 --feed v2/iex --out-dir data/live --flush-sec 2
"@
Start-Process -WindowStyle Minimized powershell -ArgumentList "-Command", $feeddCmd

Start-Sleep -Seconds 3

# 2. Start engined (trading engine) - monitoring live bars
Write-Host "Starting engined (live mode)..." -ForegroundColor Yellow
$enginedCmd = @"
cd '$PWD'
Get-Content .env | ForEach-Object { if (`$_ -match '^([^#].*)=(.*)$') { [System.Environment]::SetEnvironmentVariable(`$matches[1].Trim(), `$matches[2].Trim(), [System.EnvironmentVariableTarget]::Process) } }
python -m trading_stack.services.engined.live --symbol SPY --bars-dir data/live --poll-sec 1.0
"@
Start-Process -WindowStyle Minimized powershell -ArgumentList "-Command", $enginedCmd

Start-Sleep -Seconds 1

# 3. Start advisor (LLM proposals)
Write-Host "Starting advisor..." -ForegroundColor Yellow
$advisorCmd = @"
cd '$PWD'
Get-Content .env | ForEach-Object { if (`$_ -match '^([^#].*)=(.*)$') { [System.Environment]::SetEnvironmentVariable(`$matches[1].Trim(), `$matches[2].Trim(), [System.EnvironmentVariableTarget]::Process) } }
python -m trading_stack.services.advisor.main --symbol SPY --bars-dir data/live --out-root data/llm --interval-sec 10
"@
Start-Process -WindowStyle Minimized powershell -ArgumentList "-Command", $advisorCmd

Start-Sleep -Seconds 1

# 4. Start controller (parameter management)
Write-Host "Starting controller..." -ForegroundColor Yellow
$controllerCmd = @"
cd '$PWD'
Get-Content .env | ForEach-Object { if (`$_ -match '^([^#].*)=(.*)$') { [System.Environment]::SetEnvironmentVariable(`$matches[1].Trim(), `$matches[2].Trim(), [System.EnvironmentVariableTarget]::Process) } }
python -m trading_stack.services.controller.apply_params --symbol SPY --llm-root data/llm --interval-sec 30
"@
Start-Process -WindowStyle Minimized powershell -ArgumentList "-Command", $controllerCmd

Start-Sleep -Seconds 1

# 5. Start execd worker (order execution)
Write-Host "Starting execd worker..." -ForegroundColor Yellow
$execdCmd = @"
cd '$PWD'
Get-Content .env | ForEach-Object { if (`$_ -match '^([^#].*)=(.*)$') { [System.Environment]::SetEnvironmentVariable(`$matches[1].Trim(), `$matches[2].Trim(), [System.EnvironmentVariableTarget]::Process) } }
python -m trading_stack.services.execd.worker --ledger-root data/exec --poll-sec 0.25
"@
Start-Process -WindowStyle Minimized powershell -ArgumentList "-Command", $execdCmd

# Start heartbeat updater
Write-Host "`nStarting heartbeat monitor..." -ForegroundColor Gray
$heartbeatCmd = @"
cd '$PWD'
while (`$true) {
    python -c 'from trading_stack.ops.heartbeat import touch_heartbeat; touch_heartbeat(\"feedd\"); touch_heartbeat(\"engined\"); touch_heartbeat(\"advisor\"); touch_heartbeat(\"controller\"); touch_heartbeat(\"execd\")'
    Start-Sleep -Seconds 30
}
"@
Start-Process -WindowStyle Hidden powershell -ArgumentList "-Command", $heartbeatCmd

Write-Host "`nAll services started!" -ForegroundColor Green
Write-Host "Services are running with live market data." -ForegroundColor Cyan
Write-Host "`nMonitor progress with: python -m trading_stack.scorecard.main" -ForegroundColor Yellow
Write-Host "Stop all services with: .\stop_services.ps1" -ForegroundColor Yellow
Write-Host "`nCheck live data: dir data\live\$(Get-Date -Format yyyy-MM-dd)\" -ForegroundColor Gray
