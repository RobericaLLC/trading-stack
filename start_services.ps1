# PowerShell script to start all trading stack services
# Set environment variables (REPLACE WITH YOUR ACTUAL KEYS)
$env:ALPACA_API_KEY_ID = "YOUR_ALPACA_KEY_ID"
$env:ALPACA_API_SECRET_KEY = "YOUR_ALPACA_SECRET"
$env:OPENAI_API_KEY = "YOUR_OPENAI_KEY"  # Optional, for LLM features

# Also set for IBKR if needed
$env:IB_GATEWAY_HOST = "127.0.0.1"
$env:IB_GATEWAY_PORT = "7497"
$env:IB_CLIENT_ID = "7"

Write-Host "Starting Trading Stack Services..." -ForegroundColor Green

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
Write-Host "`nTo stop all services, run: ./stop_services.ps1" -ForegroundColor Yellow
