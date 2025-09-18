# Trading Stack (Scaffold)

A minimal, **deterministic trading spine** with a *scorecard-gated* promotion path.
This is the thin vertical slice you will harden before adding feeds, options, EMSX, and LLM advisors.

## Install (uv or pip)
```bash
# Using uv (recommended)
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# Or pip
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Quickstart
```bash
# 1) Run the scorecard on sample data
scorecard --since 1d

# 2) Run feedd to generate synthetic 1s bars for SPY (for demo)
feedd --mode synthetic --symbol SPY --minutes 5

# 3) Replay a sample day to the bus (dry-run)
python -m trading_stack.storage.replay --path sample_data/events_spy_2024-09-10.parquet
```

## Services
- `feedd`: Ingests market data and publishes normalized events (synthetic mode for now).
- `engined`: Deterministic strategy loop (baseline mean-reversion placeholder).
- `execd`: Order state machine and (later) broker adapters (IBKR adapter scaffold).

## Scorecard (truth source)
The CLI prints **PASS/FAIL** for deterministic checks. Green gates only → promotion.
