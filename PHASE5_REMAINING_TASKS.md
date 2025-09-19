# Phase 5: Remaining Tasks

## ✅ Completed
1. **Runtime Param Store** - JSON persistence and Parquet audit log
2. **Param Controller** - Policy enforcement with hard guardrails
3. **Engine Hot-Reload** - Dynamic threshold updates
4. **Scorecard LLM Gates** - All 5 monitoring gates implemented
5. **P&L Patch** - Realized P&L tracking with drawdown-based freeze
6. **Risk Multiplier Protection** - Confirmed read-only in controller

## 📋 Remaining Tasks

### 1. Prove Safety Brakes
Run the full system and demonstrate:
- **Feed Health Freeze**: Controller freezes when bars are missing/stale
- **P&L Drawdown Freeze**: Controller freezes when 30-min drawdown ≤ -0.5%

To test:
```powershell
# Start all services
./run_phase5.ps1

# Simulate feed issues: stop feedd temporarily
# Simulate P&L drawdown: place losing trades

# Monitor applied_SPY.parquet for freeze=True entries
```

### 2. Prove Rate Limiting
Demonstrate the controller enforces:
- ≤ 2 applied changes in 15 minutes
- ≤ 30% acceptance rate

To verify:
```powershell
# Check applied file
python -c "import pandas as pd; df = pd.read_parquet('data/llm/2025-09-19/applied_SPY.parquet'); print(df.tail(20))"

# Look for acceptance patterns in scorecard
scorecard --since 1d --llm-dir data/llm
```

### 3. Prove Parameter Bounds
Confirm the controller enforces:
- 0.3 ≤ signal.threshold_bps ≤ 3.0
- Per-decision delta ≤ 0.2 bps

To verify:
```powershell
# Check runtime params
cat data/params/runtime_SPY.json

# Check applied deltas
python -c "import pandas as pd; df = pd.read_parquet('data/llm/2025-09-19/applied_SPY.parquet'); print(df[['accepted_threshold_bps', 'delta_bps']])"
```

### 4. Three-Day Green Scorecard
Run the controller continuously for 3 consecutive RTH sessions with:
- All LLM gates passing
- `llm_proposals_seen_15m` ≥ 6
- `llm_proposals_applied_15m` ≤ 2
- `llm_accept_rate_15m` ≤ 30%
- `llm_param_bounds_ok` = True
- `llm_freeze_active` = False

## 🚀 Phase 5 Completion Criteria
1. All safety mechanisms proven to work
2. Three consecutive days of green scorecard gates
3. No manual intervention required
4. Ready for Phase 6 (paid LLM providers)

## 📝 Notes
- Stay on RulesProvider (zero-cost) for Phase 5
- OpenAI/Anthropic/Groq keys only needed for Phase 6
- Risk multiplier remains at 1.0 (sizing changes in later phase)
