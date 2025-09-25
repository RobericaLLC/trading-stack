# Phase 0 Trading Stack Startup Script
# Run this after setting ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY

Write-Host "=== Starting Phase 0 Trading Stack ===" -ForegroundColor Green

# Check prerequisites
if (-not $env:ALPACA_API_KEY_ID -or -not $env:ALPACA_API_SECRET_KEY) {
    Write-Host "ERROR: Alpaca API credentials not set!" -ForegroundColor Red
    Write-Host "Please set:" -ForegroundColor Yellow
    Write-Host '  $env:ALPACA_API_KEY_ID = "your-key-id"' -ForegroundColor Yellow
    Write-Host '  $env:ALPACA_API_SECRET_KEY = "your-secret-key"' -ForegroundColor Yellow
    exit 1
}

# Set trading environment variables
$env:EQUITY_USD = "30000"
$env:EXEC_ENV = "paper"
Write-Host "Environment: EQUITY_USD=$($env:EQUITY_USD), EXEC_ENV=$($env:EXEC_ENV)" -ForegroundColor Cyan

# Start services in separate PowerShell windows
Write-Host "`nStarting services..." -ForegroundColor Green

# 1. Feed service (continuous streaming)
Write-Host "1. Starting feedd (continuous streaming)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PWD'; python -m trading_stack.services.feedd.main live-alpaca --symbol SPY --minutes 0 --feed v2/iex --out-dir data/live --flush-sec 2"

Start-Sleep -Seconds 3

# 2. Advisor service (rules provider)
Write-Host "2. Starting advisor (rules provider)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PWD'; python -m trading_stack.services.advisor.main --symbol SPY --bars-dir data/live --out-root data/llm --provider rules --interval-sec 5 --budget-usd 10"

Start-Sleep -Seconds 2

# 3. Controller service
Write-Host "3. Starting controller..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PWD'; python -m trading_stack.services.controller.apply_params --symbol SPY --llm-root data/llm --live-root data/live --ledger-root data/exec --params-root data/params --interval-sec 5"

Start-Sleep -Seconds 2

# 4. Engine daemon
Write-Host "4. Starting engined live..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PWD'; python -m trading_stack.services.engined.live --symbol SPY --bars-dir data/live --queue data/queue.db --params-root data/params"

Start-Sleep -Seconds 2

# 5. Execution worker
Write-Host "5. Starting execd worker..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PWD'; python -m trading_stack.services.execd.worker --queue data/queue.db --ledger-root data/exec --poll-sec 0.25"

Write-Host "`nAll services started!" -ForegroundColor Green
Write-Host "Waiting for system to stabilize..." -ForegroundColor Cyan
Start-Sleep -Seconds 10

# Run initial health check
Write-Host "`n=== Initial Health Check ===" -ForegroundColor Green
python -m trading_stack.services.feedd.main verify

Write-Host "`n=== Scorecard ===" -ForegroundColor Green
python -m trading_stack.scorecard.main

Write-Host "`nMonitoring commands:" -ForegroundColor Cyan
Write-Host "  python -m trading_stack.services.feedd.main verify" -ForegroundColor White
Write-Host "  python -m trading_stack.scorecard.main" -ForegroundColor White
Write-Host "`nTo stop all services, close the PowerShell windows or run:" -ForegroundColor Cyan
Write-Host '  Get-Process python | Stop-Process -Force' -ForegroundColor White
