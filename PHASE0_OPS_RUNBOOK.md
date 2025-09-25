# Phase 0 Operations Runbook (Lenovo-only)

This runbook covers the minimal operational procedures for running the trading stack during RTH (Regular Trading Hours) in a Lenovo-only environment.

## Prerequisites

- All services must be configured and ready
- System clock offset must be < 1 second (already solved)
- Access to scorecard for monitoring
- Alpaca API credentials set in environment:
  - `ALPACA_API_KEY_ID`
  - `ALPACA_API_SECRET_KEY`

## During RTH Operations

### 1. Service Startup Sequence

Start services in the following order:

1. **feedd** with `minutes=0` parameter (continuous streaming mode with 5-second flush intervals)
2. **advisor** with `--provider rules` (not --rules)
3. **controller**
4. **engined** in live mode
5. **execd** worker

```powershell
# Set environment variables
$env:EQUITY_USD = "30000"
$env:EXEC_ENV   = "paper"

# 1) Feed (continuous)
python -m trading_stack.services.feedd.main live-alpaca --symbol SPY --minutes 0 --feed v2/iex --out-dir data/live --flush-sec 2

# 2) Advisor (shadow)
python -m trading_stack.services.advisor.main --symbol SPY --bars-dir data/live --out-root data/llm --provider rules --interval-sec 5 --budget-usd 10

# 3) Controller (guardrails + freeze)
python -m trading_stack.services.controller.apply_params --symbol SPY --llm-root data/llm --live-root data/live --ledger-root data/exec --params-root data/params --interval-sec 5

# 4) Engine
python -m trading_stack.services.engined.live --symbol SPY --bars-dir data/live --queue data/queue.db --params-root data/params

# 5) Execution worker
python -m trading_stack.services.execd.worker --queue data/queue.db --ledger-root data/exec --poll-sec 0.25
```

### 2. Initial Verification

- **Check feed health** in scorecard
- Verify all services are running and connected

### 3. System Behavior Expectations

Once the system is running:

- **llm_freeze_active** should flip to `False` within one flush cycle (≤ 2 seconds) once trades start flowing
- Expect **at most 2 applied updates per 15 minutes**
- **Acceptance rate** should be ≤ 30%
- **Trade coverage** now uses 5-minute rolling window (target ≥ 35% for IEX)
- If fills occur:
  - `realized_points_30m` will grow
  - Drawdown gate should remain `PASS`

### 4. Monitoring

Let the system run and monitor:
- Feed health status
- LLM freeze status
- Applied update frequency
- Acceptance rate
- Realized points (if trading)
- Drawdown gate status

```powershell
# 6) Scorecard (watch every minute)
python -m trading_stack.scorecard.main
```

### 5. Quick Sanity Checks

```powershell
# Use feedd verify command for comprehensive health check
python -m trading_stack.services.feedd.main verify --symbol SPY --out_dir data/live

# For quieter periods, use wider window
python -m trading_stack.services.feedd.main verify --symbol SPY --out_dir data/live --window_min 5 --coverage_threshold 0.40

# Alternative: Show last bar timestamp and age
python -c "import pandas as pd, glob, datetime; paths = sorted(glob.glob(r'data\live\*\bars1s_SPY.parquet')); df = pd.read_parquet(paths[-1]); df['ts']=pd.to_datetime(df['ts'], utc=True); print('bars rows', len(df), 'last', df['ts'].iloc[-1], 'age(s)', (pd.Timestamp.utcnow().tz_localize('UTC')-df['ts'].iloc[-1]).total_seconds())"
```

What the verify command checks:
- **Bars**: Last timestamp age, 1-second coverage in window, total rows
- **Trades**: Last ingest_ts age, trades in window, % with ingest_ts, freshness p99, clock offset
- **Health**: PASS if (bars fresh & coverage ≥ threshold) OR (trades fresh with ≥ 20 trades)

This matches the controller's feed health logic, so if verify shows PASS, the controller should unfreeze within one flush cycle.

## Troubleshooting

### If Freeze Persists

If `llm_freeze_active` remains `True` for more than 1 minute:

1. **Check feed health with verify command**:
   ```powershell
   python -m trading_stack.services.feedd.main verify
   ```
   This will tell you exactly why the feed is unhealthy (stale bars, low coverage, no trades).

2. **Run ledger sanitization**:
   ```powershell
   python -m trading_stack.tools.ledger_sanitize
   ```

3. **Switch controller to sanitized ledger path** (temporarily):
   - Update controller configuration to use the sanitized ledger
   - Restart controller service

4. **Ensure system clock**:
   - Verify system clock offset is < 1 second (should already be solved)
   - The verify command shows `clock_offset_median_ms` to detect time drift

### Common Issues and Solutions

| Issue | Check | Solution |
|-------|-------|----------|
| No bars coming in | `feedd verify` command | Restart feedd with correct parameters |
| High rejection rate | Advisor logs | Check rule configuration |
| Freeze won't clear | `feedd verify` + scorecard | Follow freeze troubleshooting steps |
| Low feed coverage | `feedd verify` output | Check if market hours; adjust coverage threshold |
| No fills executing | Execd worker status | Verify execd worker is running |

### 6. Post-RTH Procedures

1. Monitor final metrics in scorecard
2. Check for any error logs
3. Verify data persistence in parquet files
4. Review realized points and drawdown metrics

## Notes

- This is a Phase 0 minimal setup - no external services, feeds, or LLM calls
- All behavior should be deterministic
- System is designed for conservative operation with low update frequency
