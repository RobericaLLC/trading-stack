# PowerShell script to start all trading stack services with .env support
# This script automatically loads environment variables from .env file

Write-Host "Starting Trading Stack Services with .env support..." -ForegroundColor Green

# Check if .env exists
if (-not (Test-Path ".env")) {
    Write-Host "ERROR: .env file not found!" -ForegroundColor Red
    Write-Host "Please run: .\setup_env.ps1 to create one" -ForegroundColor Yellow
    exit 1
}

Write-Host "Loading environment from .env file..." -ForegroundColor Cyan

# Services will automatically load .env via env_loader module
Write-Host ""

# 1. Start feedd (market data feed)
Write-Host "Starting feedd..." -ForegroundColor Yellow
Start-Process -WindowStyle Minimized powershell -ArgumentList @(
    "-Command",
    "cd '$PWD'; python -m trading_stack.services.feedd.main live-alpaca --symbol SPY --minutes 0 --feed v2/iex --out-dir data/live --flush-sec 2"
)

Start-Sleep -Seconds 2

# 2. Start engined (trading engine) - monitoring live bars
Write-Host "Starting engined (live mode)..." -ForegroundColor Yellow
Start-Process -WindowStyle Minimized powershell -ArgumentList @(
    "-Command", 
    "cd '$PWD'; python -m trading_stack.services.engined.live --symbol SPY --bars-dir data/live --poll-sec 1.0"
)

Start-Sleep -Seconds 1

# 3. Start advisor (LLM proposals)
Write-Host "Starting advisor..." -ForegroundColor Yellow
Start-Process -WindowStyle Minimized powershell -ArgumentList @(
    "-Command",
    "cd '$PWD'; python -m trading_stack.services.advisor.main --symbol SPY --bars-dir data/live --out-root data/llm --interval-sec 10"
)

Start-Sleep -Seconds 1

# 4. Start controller (parameter management)
Write-Host "Starting controller..." -ForegroundColor Yellow
Start-Process -WindowStyle Minimized powershell -ArgumentList @(
    "-Command",
    "cd '$PWD'; python -m trading_stack.services.controller.apply_params --symbol SPY --llm-root data/llm --interval-sec 30"
)

Start-Sleep -Seconds 1

# 5. Start execd worker (order execution)
Write-Host "Starting execd worker..." -ForegroundColor Yellow
Start-Process -WindowStyle Minimized powershell -ArgumentList @(
    "-Command",
    "cd '$PWD'; python -m trading_stack.services.execd.worker --ledger-root data/exec --poll-sec 0.25"
)

Write-Host "`nAll services started!" -ForegroundColor Green
Write-Host "Check the minimized windows for service logs." -ForegroundColor Cyan
Write-Host "`nTo monitor telemetry, run: python -m trading_stack.scorecard.main" -ForegroundColor Yellow
Write-Host "To stop all services, run: .\stop_services.ps1" -ForegroundColor Yellow

# Start updating heartbeats in background
Write-Host "`nStarting heartbeat monitor..." -ForegroundColor Gray
Start-Process -WindowStyle Hidden powershell -ArgumentList @(
    "-Command",
    @"
    cd '$PWD'
    while (`$true) {
        python -c 'from trading_stack.ops.heartbeat import touch_heartbeat; touch_heartbeat(\"feedd\"); touch_heartbeat(\"engined\"); touch_heartbeat(\"advisor\"); touch_heartbeat(\"controller\"); touch_heartbeat(\"execd\")'
        Start-Sleep -Seconds 30
    }
"@
)
