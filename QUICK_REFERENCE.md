# Trading Stack Quick Reference
**For Market Hours Operations**

## 🚀 Start All Services (T-15)
```powershell
.\start_services_with_env.ps1
```

## 📊 Check Health
```powershell
# Quick ops status (one-liner)
python -m trading_stack.ops.status --symbol SPY

# Live ops ticker (updates every 5s)
python -m trading_stack.ops.status --symbol SPY --watch 5

# Detailed ops dashboard
python -m trading_stack.ops.status --symbol SPY --verbose

# Full scorecard
python -m trading_stack.scorecard.main

# With tunable threshold
$env:REALIZED_POINTS_MIN = "5"
python -m trading_stack.scorecard.main

# Feed health check
python -m trading_stack.services.feedd.main verify --symbol SPY --out-dir data/live --window-min 1
```

## 💉 Quick Fixes

### Generate ACK/Cancel metrics
```powershell
python -m trading_stack.services.execd.main sanity-cancel --symbol SPY --qty 1 --limit 0.01
```

### Generate fill/shortfall metrics
```powershell
# Get current price
$last = python -c "import pandas as pd, glob; p=sorted(glob.glob('data/live/*/bars1s_SPY.parquet'))[-1]; df=pd.read_parquet(p); print(float(df['close'].iloc[-1]))"

# Place micro-fill
python -m trading_stack.services.execd.main one-shot --symbol SPY --side BUY --qty 1 --limit ($last + 0.03) --bars-path (Get-ChildItem data/live/*/bars1s_SPY.parquet | Sort -Last 1).FullName --ttl-sec 5
```

### Force update heartbeats
```powershell
python -c "from trading_stack.ops.heartbeat import beat; services=['feedd','engined','advisor','controller','execd']; [beat(s) for s in services]; print('Updated all heartbeats')"
```

## 🛑 Emergency Stop
```powershell
.\stop_services.ps1
```

## 📁 Key Files to Monitor
- `data/ops/heartbeat/*.json` - Service health
- `data/ops/controller_state.json` - Freeze status
- `data/exec/YYYY-MM-DD/ledger.parquet` - Execution events
- `data/exec/YYYY-MM-DD/shadow_ledger.parquet` - Engine intents
- `data/queue.db` - Order queue

## 🔧 Common Issues

| Symptom | Fix |
|---------|-----|
| uptime_rth < 100% | Check heartbeat files, restart affected service |
| llm_freeze_active = True | Run `feedd verify`, check feed health |
| ack_latency = NA | Run 2x sanity-cancel |
| realized_points = 0 | Run micro-fill |
| Ledger corrupt | Stop execd, delete ledger, restart |

---
*Keep this handy during market hours!*
