# Phase 5: LLM Proposals Live - Run Guide

## Overview
Phase 5 enables live trading with LLM-generated parameter adjustments under strict guardrails. The system dynamically adjusts trading thresholds based on LLM proposals while enforcing hard safety limits.

## Components

### 1. Feed Service (feedd)
Collects live market data from Alpaca IEX feed.
```powershell
python -m trading_stack.services.feedd.main live-alpaca --symbol SPY --minutes 0 --feed v2/iex --out-dir data/live
```

### 2. Advisor Service (LLM Proposals)
Generates trading parameter proposals using the rules-based provider.
```powershell
python -m trading_stack.services.advisor.main --symbol SPY --bars-dir data/live --out-root data/llm --provider rules --interval-sec 5 --budget-usd 10
```

### 3. Controller Service (Policy Enforcer) ⭐ NEW
Applies LLM proposals under strict policy constraints.
```powershell
python -m trading_stack.services.controller.apply_params --symbol SPY --llm-root data/llm --live-root data/live --ledger-root data/exec --params-root data/params --interval-sec 5
```

**Policy Constraints:**
- Parameter bounds: 0.3 ≤ threshold_bps ≤ 3.0
- Delta cap: ≤ 0.2 bps per decision (5s cadence)
- Rate limit: ≤ 30% proposals accepted in 15 min window
- Freeze conditions: 
  - Feed health issues (missing/stale bars)
  - P&L drawdown ≤ -0.5% of equity in 30 min window
  - Equity set via $env:EQUITY_USD (default: 30000)

### 4. Engine Service (with Hot-Reload) ⭐ UPDATED
Trading engine that hot-reloads parameters from runtime JSON.
```powershell
python -m trading_stack.services.engined.live --symbol SPY --bars-dir data/live --queue data/queue.db --params-root data/params
```

### 5. Execution Worker
Processes order intents from the queue.
```powershell
python -m trading_stack.services.execd.worker --queue data/queue.db --ledger-root data/exec --poll-sec 0.25
```

## Quick Start

### Automated Start (Windows PowerShell)
```powershell
# Set your paper account equity (used for P&L drawdown freeze)
$env:EQUITY_USD = "30000"

./run_phase5.ps1
```

### Manual Start
First set environment variables:
```powershell
$env:EXEC_ENV = "paper"
$env:EQUITY_USD = "30000"  # Your paper account equity
```
Then start each service in a separate terminal in the order listed above.

## Monitoring

### Scorecard
Check system health and LLM gates:
```powershell
$env:EXEC_ENV = "paper"
scorecard --since 1d --llm_dir data/llm
```

### Target Gates (PASS)
- `llm_proposals_seen_15m` ≥ 6
- `llm_proposals_applied_15m` ≤ 2  
- `llm_accept_rate_15m` ≤ 30%
- `llm_param_bounds_ok` = True
- `llm_freeze_active` = False

### Key Files to Monitor
- **Runtime parameters**: `data/params/runtime_SPY.json`
- **Applied decisions**: `data/llm/{date}/applied_SPY.parquet`
- **LLM proposals**: `data/llm/{date}/proposals_SPY.parquet`

## Safety Features

1. **Multi-layer Protection**
   - Controller enforces policy at application time
   - Scorecard validates system state continuously
   - Engine uses last known good params on read failure

2. **Audit Trail**
   - All parameter changes logged to parquet
   - Includes: timestamp, delta, seen count, freeze status
   - Traceable decision history

3. **Freeze Mechanism**
   - Automatic freeze on feed health issues
   - Freeze on P&L drawdown (when implemented)
   - Freeze on excessive clock offset

## Troubleshooting

### No Proposals Applied
- Check `llm_proposals_seen_15m` - should be ≥ 6
- Verify feed is healthy (check `data/live` for recent bars)
- Check freeze status in scorecard

### All Proposals Rejected
- Review `data/llm/{date}/applied_SPY.parquet` for freeze=True
- Check current threshold in `data/params/runtime_SPY.json`
- Verify bounds (0.3-3.0 bps)

### High Acceptance Rate
- System enforces max 30% acceptance automatically
- Check `llm_accept_rate_15m` in scorecard
- Review applied decisions for patterns

## Phase 5 vs Previous Phases

| Feature | Phase 4 | Phase 5 |
|---------|---------|---------|
| LLM Proposals | Shadow only | Live with guardrails |
| Threshold Updates | Static | Dynamic hot-reload |
| Policy Enforcement | None | Hard limits enforced |
| Scorecard Gates | Basic | Full LLM monitoring |
| Audit Trail | Ledger only | Complete param history |
