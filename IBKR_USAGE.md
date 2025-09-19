# IBKR Execution Commands Usage

This document describes how to use the IBKR execution commands in the trading-stack.

## Prerequisites

1. Install the IBKR dependencies:
   ```bash
   pip install '.[ib]'
   ```

2. Ensure IB Gateway or TWS is running with API enabled
   - Default port: 7497 (paper trading) or 7496 (live trading)
   - Enable "Enable ActiveX and Socket Clients" in API settings

3. Set environment variables (optional, defaults shown):
   ```bash
   export IB_GATEWAY_HOST=127.0.0.1
   export IB_GATEWAY_PORT=7497
   export IB_CLIENT_ID=7
   ```

## Available Commands

### 1. IBKR Handshake Test

Test connectivity to IBKR (read-only mode OK):

```bash
python -m trading_stack.services.execd.main ib-handshake
```

Expected output:
```
IBKR handshake OK
```

### 2. Cancel-Only Smoke Test

Place and immediately cancel an order (requires "Read-Only API" to be OFF):

```bash
python -m trading_stack.services.execd.main sanity-cancel --symbol SPY --qty 1 --limit 0.01
```

This creates a ledger file at `data/exec/YYYY-MM-DD/ledger.parquet` with:
- INTENT: Order intention
- ACK: Order acknowledgment
- CANCEL: Order cancellation

Expected output:
```
[sanity-cancel] tag=sanity_SPY_1234567890 ACK+Cancel recorded
```

### 3. One-Shot Order with TTL

Place an order with Time-To-Live and arrival price capture:

First, ensure you have bars data from Phase 1:
```
data/live/YYYY-MM-DD/bars1s_SPY.parquet
```

Then place the order:
```bash
python -m trading_stack.services.execd.main one-shot \
    --symbol SPY \
    --side BUY \
    --qty 1 \
    --limit 10.00 \
    --bars_path data/live/YYYY-MM-DD/bars1s_SPY.parquet \
    --ttl_sec 2
```

Parameters:
- `--symbol`: Stock symbol (default: SPY)
- `--side`: BUY or SELL (default: BUY)
- `--qty`: Order quantity (default: 1)
- `--limit`: Limit price (optional, market order if not specified)
- `--tif`: Time in force - IOC, DAY, GTC (default: DAY)
- `--tag`: Custom order tag (optional)
- `--bars_path`: Path to bars data for arrival price capture (optional)
- `--ttl_sec`: Time-to-live in seconds before auto-cancel (default: 3)
- `--out_dir`: Output directory for ledger (default: data/exec)

Expected output:
```
[one-shot] tag=oneshot_SPY_1234567890 state=CANCEL fill_qty=0 avg_px=— arrival=123.45
```

## Ledger Output

All commands that place orders create or append to a ledger file at:
```
data/exec/YYYY-MM-DD/ledger.parquet
```

The ledger contains events:
- `INTENT`: Order placement intention with details
- `ACK`: Order acknowledged by broker
- `REJ`: Order rejected (if applicable)
- `PARTIAL`: Partial fill
- `FILL`: Complete fill
- `CANCEL`: Order cancelled
- `PNL_SNAPSHOT`: TCA metrics (if arrival price available and order filled)

## Tips

1. For paper trading tests, use very low limit prices (e.g., $0.01) to avoid fills
2. For testing partial fills, use limit prices close to market but not at market
3. The TTL feature ensures orders don't stay open indefinitely
4. Arrival price capture requires bars data from the same day

## Troubleshooting

1. **Connection refused**: Ensure IB Gateway/TWS is running and API is enabled
2. **Read-only API error**: Disable "Read-Only API" in IB Gateway settings for order placement
3. **No bars data**: Run Phase 1 data capture first to get bars data for TCA
