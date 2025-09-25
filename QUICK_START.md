# Trading Stack Quick Start Guide

## Prerequisites

1. **Set Alpaca API Credentials** (required for live data):
   ```powershell
   $env:ALPACA_API_KEY_ID = "your-alpaca-key-id"
   $env:ALPACA_API_SECRET_KEY = "your-alpaca-secret-key"
   ```

2. **Verify System Time** (should already be synchronized):
   ```powershell
   w32tm /query /status
   ```

## Starting the System

### Option 1: Automated Startup (Recommended)

Run the startup script:
```powershell
.\start_trading_stack.ps1
```

This will:
- Check prerequisites
- Set environment variables
- Start all 5 services in separate windows
- Run initial health checks

### Option 2: Manual Startup

If you prefer to start services manually:

```powershell
# Set environment
$env:EQUITY_USD = "30000"
$env:EXEC_ENV = "paper"

# 1. Feed service (continuous streaming)
python -m trading_stack.services.feedd.main live-alpaca --symbol SPY --minutes 0 --feed v2/iex --out_dir data/live --flush_sec 5

# 2. Advisor service (rules provider)
python -m trading_stack.services.advisor.main --symbol SPY --bars_dir data/live --out_root data/llm --provider rules --interval_sec 5 --budget_usd 10

# 3. Controller service
python -m trading_stack.services.controller.apply_params --symbol SPY --llm_root data/llm --live_root data/live --ledger_root data/exec --params_root data/params --interval_sec 5

# 4. Engine daemon
python -m trading_stack.services.engined.live --symbol SPY --bars_dir data/live --queue data/queue.db --params_root data/params

# 5. Execution worker
python -m trading_stack.services.execd.worker --queue data/queue.db --ledger_root data/exec --poll_sec 0.25
```

## Monitoring

### Continuous Monitoring
```powershell
.\monitor_trading_stack.ps1
```

### Manual Health Checks
```powershell
# Check feed health
python -m trading_stack.services.feedd.main verify

# View scorecard
python -m trading_stack.scorecard.main

# Check latest bar data
python -c "import pandas as pd, glob; paths = sorted(glob.glob(r'data\live\*\bars1s_SPY.parquet')); df = pd.read_parquet(paths[-1]); df['ts']=pd.to_datetime(df['ts'], utc=True); print('bars rows', len(df), 'last', df['ts'].iloc[-1], 'age(s)', (pd.Timestamp.utcnow().tz_localize('UTC')-df['ts'].iloc[-1]).total_seconds())"
```

## Expected Behavior

Within 5-10 seconds of startup:
- Feed health should show `PASS`
- `llm_freeze_active` should be `False`
- Intents should start being enqueued
- Proposals should start being generated

## Troubleshooting

If `llm_freeze_active` stays `True`:
1. Run `python -m trading_stack.services.feedd.main verify`
2. Check if trades/bars are flowing
3. Verify market hours (9:30 AM - 4:00 PM ET)

If no data is flowing:
1. Check Alpaca credentials
2. Verify network connectivity
3. Check if market is open

## Stopping the System

To stop all services:
```powershell
Get-Process python | Stop-Process -Force
```

Or close each PowerShell window individually.
