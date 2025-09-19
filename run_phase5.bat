@echo off
REM Phase 5: LLM Proposals Live - Run Sequence
REM Batch script to start all components for live LLM trading with guardrails

echo Starting Phase 5 - LLM Proposals Live with Hard Guardrails
echo =============================================

REM Set environment for paper trading
set EXEC_ENV=paper
set EQUITY_USD=30000

REM Create necessary directories
for %%d in (data\live data\llm data\exec data\params RUN\heartbeat) do (
    if not exist %%d mkdir %%d
)

echo.
echo Starting services...

REM Start Feed Service
echo.
echo 1. Starting Feed Service (feedd)...
start "FEED SERVICE" cmd /k "python -m trading_stack.services.feedd.main live-alpaca --symbol SPY --minutes 0 --feed v2/iex --out-dir data/live"

timeout /t 2 /nobreak > nul

REM Start Advisor Service (LLM proposals)
echo 2. Starting Advisor Service (LLM proposals)...
start "ADVISOR SERVICE" cmd /k "python -m trading_stack.services.advisor.main --symbol SPY --bars-dir data/live --out-root data/llm --provider rules --interval-sec 5 --budget-usd 10"

timeout /t 2 /nobreak > nul

REM Start Controller (Policy Enforcer) - NEW in Phase 5
echo 3. Starting Controller (Policy Enforcer)...
start "CONTROLLER - POLICY ENFORCER" cmd /k "python -m trading_stack.services.controller.apply_params --symbol SPY --llm-root data/llm --live-root data/live --ledger-root data/exec --params-root data/params --interval-sec 5"

timeout /t 2 /nobreak > nul

REM Start Engine with hot-reload - UPDATED in Phase 5
echo 4. Starting Engine (with hot-reload)...
start "ENGINE - HOT RELOAD" cmd /k "python -m trading_stack.services.engined.live --symbol SPY --bars-dir data/live --queue data/queue.db --params-root data/params"

timeout /t 2 /nobreak > nul

REM Start Execution Worker
echo 5. Starting Execution Worker...
start "EXECUTION WORKER" cmd /k "python -m trading_stack.services.execd.worker --queue data/queue.db --ledger-root data/exec --poll-sec 0.25"

echo.
echo All services started!
echo.
echo Phase 5 Guardrails Active:
echo   - Parameter bounds: 0.3-3.0 bps
echo   - Delta cap: 0.2 bps per decision
echo   - Rate limit: max 30%% acceptance in 15 min
echo   - Freeze on: feed issues, P&L drawdown
echo.
echo To check scorecard status, run in a new terminal:
echo   set EXEC_ENV=paper
echo   scorecard --since 1d --llm_dir data/llm
echo.
echo Target scorecard values (PASS):
echo   llm_proposals_seen_15m      ^>= 6
echo   llm_proposals_applied_15m   ^<= 2
echo   llm_accept_rate_15m         ^<= 30%%
echo   llm_param_bounds_ok         True
echo   llm_freeze_active           False
echo.
pause
