# Go-Live Playbook for Trading Stack
**Created**: September 25, 2025  
**For**: Tomorrow's Market Open (September 26, 2025)

## ✅ Go/No-Go Checklist (Lenovo, **T-15 → T+10**)

### **T-15 min** — Environment + Services

```powershell
# env
$env:EQUITY_USD = "30000"
$env:EXEC_ENV   = "paper"
$env:REALIZED_POINTS_MIN = "5"   # optional for Phase 5

# start feed (continuous, fast flush)
python -m trading_stack.services.feedd.main live-alpaca `
  --symbol SPY --minutes 0 --feed v2/iex --out-dir data/live --flush-sec 2

# advisor (rules provider, shadow)
python -m trading_stack.services.advisor.main `
  --symbol SPY --bars-dir data/live --out-root data/llm `
  --provider rules --interval-sec 5 --budget-usd 10

# controller (guardrails + freeze)
python -m trading_stack.services.controller.apply_params `
  --symbol SPY --llm-root data/llm --live-root data/live `
  --ledger-root data/exec --params-root data/params --interval-sec 5

# engine (hot-reload threshold, enqueue intents)
python -m trading_stack.services.engined.live `
  --symbol SPY --bars-dir data/live --queue data/queue.db --params-root data/params

# executor (single writer of ledger.parquet)
python -m trading_stack.services.execd.worker `
  --queue data/queue.db --ledger-root data/exec --poll-sec 0.25
```

**Verify feed health & clocks (should PASS):**

```powershell
# mirrors controller's unfreeze gate
python -m trading_stack.services.feedd.main verify --symbol SPY --out-dir data/live --window-min 1 --coverage-threshold 0.50
```

### **T-10 min** — Baseline health snapshot

```powershell
# Quick ops check
python -m trading_stack.ops.status --symbol SPY

# Full scorecard
scorecard --since 1d --llm_dir data/llm
```

Expect:
* `uptime_rth = 100%`
* `clock_offset_median_ms` ~ ±250 ms (current ~-170 ms is fine)
* `trade_sec_coverage` (5-min window) ≥ **35%** on IEX
* `llm_freeze_active = False` (once trades are flowing)
* `engine_coverage_last_15m = 100%`

### **T-5 min** — Seed execution SLOs

Generate two cancels to populate ACK/CANCEL metrics (paper is jittery; do this early):

```powershell
python -m trading_stack.services.execd.main sanity-cancel --symbol SPY --qty 1 --limit 0.01
python -m trading_stack.services.execd.main sanity-cancel --symbol SPY --qty 1 --limit 0.01
```

Expect:
* `ack_latency_p95_ms` < **1200 ms** (paper)
* `cancel_success (sanity …)` = **100%**

### **T+0 to T+10** — One micro-fill for realized P&L

1 share slightly inside the market to fill quickly:

```powershell
$last = python - << 'PY'
import pandas as pd, glob
p = sorted(glob.glob("data/live/*/bars1s_SPY.parquet"))[-1]
df = pd.read_parquet(p); print(float(df['close'].iloc[-1]))
PY

python -m trading_stack.services.execd.main one-shot `
  --symbol SPY --side BUY --qty 1 `
  --limit ($last + 0.03) `
  --bars-path (Get-ChildItem data/live/*/bars1s_SPY.parquet | Sort-Object Name | Select -Last 1).FullName `
  --ttl-sec 5
```

Expect:
* `shortfall_median_bps` < **4**
* `realized_points_30m` ≥ **5** (with your env setting)

---

## 🔒 Safety Rails (live guards you already have)

* **Feed-health gate**: unfreezes only when **age ≤ 60 s** (bars) & **coverage ≥ 50%**, or **trades age ≤ 10 s** & **≥ 20 trades/60s**.
* **LLM policy**: bounds **[0.3, 3.0] bps**, per-decision **Δ ≤ 0.2 bps**, **≤ 2** applies / 15 min, **≤ 30%** acceptance.
* **P&L freeze**: only considered when there are **≥ 10** realized points in last 30 min; otherwise neutral.
* **Killswitch**: `RUN/HALT` file respected in risk gate (leave in place).

---

## 🧪 What "Green Board" looks like (quick read)

Key lines from `scorecard` during RTH:

* `clock_offset_median_ms` ≈ small number → **PASS**
* `freshness_p99_ms` < **750 ms** → **PASS**
* `trade_sec_coverage` (5-min window) ≥ **35%** → **PASS**
* `ack_latency_p95_ms` < **1200 ms** (paper) → **PASS**
* `cancel_success (sanity …)` = **100%** → **PASS**
* `shortfall_median_bps` < **4** → **PASS**
* `realized_points_30m` ≥ **5** → **PASS**
* `llm_freeze_active = False` → **PASS**
* `engine_coverage_last_15m = 100%` → **PASS**
* `uptime_rth = 100%` → **PASS**

---

## 🛠 Rapid Triage Matrix

* **`llm_freeze_active=True`**
  - Run `feedd verify` → if **trades_ok=True** or **bars_ok=True**, controller should unfreeze within one loop (≤5 s).
  - If not: check env keys, network, or Alpaca WS logs.

* **`ack_latency_p95_ms=NA` / `cancel_success=NA`**
  - Re-run two `sanity-cancel` calls.

* **`shortfall_median_bps=NA` / `realized_points_30m=0`**
  - Run the micro-fill once.

* **Ledger error**
  - You're protected now (atomic + single writer). If it ever occurs: stop `execd`, run `ledger_sanitize`, restart.

* **`uptime_rth < 99%`**
  - Ensure each service is writing a heartbeat every few seconds; check timestamps in `data/ops/heartbeat/*`.

---

## 🗂 End-of-Day (EOD)

* **Snapshot** positions & realized P&L:

```powershell
python -m trading_stack.accounting.snapshot --ledger_root data/exec --out_root data/accounting
```

* **Backup** (zip & copy to Fury or NAS):

```powershell
$stamp = Get-Date -Format "yyyy-MM-dd_HH-mm"
Compress-Archive -Path data\* -DestinationPath backups\data_$stamp.zip
```

* **Rotate** logs/daily folders if needed.

---

## 📈 What to watch tomorrow

* Acceptance should stay **low** (0-2 applies / 15 min, ≈ **< 3%** acceptance).
* Shortfall around **0-3 bps** on the micro-fills.
* IEX coverage typically **35-70%** in active periods; your 40-46% is normal.
* Queue stays **depth=0**, **dead letters=0**.

### 📺 Live Monitoring (Optional)

Keep ops status running in a dedicated terminal:

```powershell
# Real-time ticker (updates every 5 seconds)
python -m trading_stack.ops.status --symbol SPY --watch 5
```

Example output:
```
OPS | feed=PASS | cov 52% | bar_age 2.9s | trades_age 1.7s | trades_1m 58 | fresh_p99 3.2ms | queue q:0 proc:0 dead:0 | freeze False | th 0.352bps | llm 64→2 (3%) | uptime 100%
```

---

## 🚀 Trading Stack Status

### Ready for Go-Live ✅

**Atomic Writes**: Proven solid under concurrent load  
**Heartbeats**: All services reporting (100% uptime)  
**Controller State**: Persistent, no more NA  
**Thresholds**: Tunable for paper/live transition  
**Safety Rails**: All guards in place and tested  

---

*Playbook created after successful market close testing on September 25, 2025*
