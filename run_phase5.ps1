# Phase 5: LLM Proposals Live - Run Sequence
# PowerShell script to start all components for live LLM trading with guardrails

Write-Host "Starting Phase 5 - LLM Proposals Live with Hard Guardrails" -ForegroundColor Green
Write-Host "=============================================" -ForegroundColor Green

# Set environment for paper trading
$env:EXEC_ENV = "paper"

# Create necessary directories
$dirs = @("data/live", "data/llm", "data/exec", "data/params", "RUN/heartbeat")
foreach ($dir in $dirs) {
    if (!(Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "Created directory: $dir" -ForegroundColor Yellow
    }
}

Write-Host "`nStarting services..." -ForegroundColor Cyan

# Start Feed Service
Write-Host "`n1. Starting Feed Service (feedd)..." -ForegroundColor Yellow
Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command", @"
Write-Host 'FEED SERVICE' -ForegroundColor Green
feedd live-alpaca --symbol SPY --minutes 0 --feed v2/iex --out_dir data/live
"@

Start-Sleep -Seconds 2

# Start Advisor Service (LLM proposals)
Write-Host "2. Starting Advisor Service (LLM proposals)..." -ForegroundColor Yellow
Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command", @"
Write-Host 'ADVISOR SERVICE' -ForegroundColor Green
python -m trading_stack.services.advisor.main --symbol SPY --bars_dir data/live --out_root data/llm --provider rules --interval_sec 5 --budget_usd 10
"@

Start-Sleep -Seconds 2

# Start Controller (Policy Enforcer) - NEW in Phase 5
Write-Host "3. Starting Controller (Policy Enforcer)..." -ForegroundColor Yellow
Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command", @"
Write-Host 'CONTROLLER SERVICE - POLICY ENFORCER' -ForegroundColor Red
python -m trading_stack.services.controller.apply_params --symbol SPY --llm_root data/llm --live_root data/live --ledger_root data/exec --params_root data/params --interval_sec 5
"@

Start-Sleep -Seconds 2

# Start Engine with hot-reload - UPDATED in Phase 5
Write-Host "4. Starting Engine (with hot-reload)..." -ForegroundColor Yellow
Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command", @"
Write-Host 'ENGINE SERVICE - HOT RELOAD ENABLED' -ForegroundColor Blue
python -m trading_stack.services.engined.live --symbol SPY --bars_dir data/live --queue data/queue.db --params_root data/params
"@

Start-Sleep -Seconds 2

# Start Execution Worker
Write-Host "5. Starting Execution Worker..." -ForegroundColor Yellow
Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command", @"
Write-Host 'EXECUTION WORKER' -ForegroundColor Magenta
python -m trading_stack.services.execd.worker --queue data/queue.db --ledger_root data/exec --poll_sec 0.25
"@

Write-Host "`nAll services started!" -ForegroundColor Green
Write-Host "`nPhase 5 Guardrails Active:" -ForegroundColor Cyan
Write-Host "  - Parameter bounds: 0.3-3.0 bps" -ForegroundColor White
Write-Host "  - Delta cap: 0.2 bps per decision" -ForegroundColor White
Write-Host "  - Rate limit: max 30% acceptance in 15 min" -ForegroundColor White
Write-Host "  - Freeze on: feed issues, P&L drawdown" -ForegroundColor White

Write-Host "`nTo check scorecard status, run in a new terminal:" -ForegroundColor Yellow
Write-Host '  $env:EXEC_ENV = "paper"' -ForegroundColor White
Write-Host "  scorecard --since 1d --llm_dir data/llm" -ForegroundColor White

Write-Host "`nTarget scorecard values (PASS):" -ForegroundColor Green
Write-Host "  llm_proposals_seen_15m      >= 6" -ForegroundColor White
Write-Host "  llm_proposals_applied_15m   <= 2" -ForegroundColor White
Write-Host "  llm_accept_rate_15m         <= 30%" -ForegroundColor White
Write-Host "  llm_param_bounds_ok         True" -ForegroundColor White
Write-Host "  llm_freeze_active           False" -ForegroundColor White

Write-Host "`nPress any key to exit this launcher..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
