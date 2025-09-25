"""Execution worker - consumes order intents and places orders via IBKR."""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from pathlib import Path

import typer

from trading_stack.adapters.ibkr.adapter import IBKRAdapter
from trading_stack.core.schemas import NewOrder
from trading_stack.ipc.sqlite_queue import ack, connect, nack, reserve
from trading_stack.risk.gate import RiskConfig, pretrade_check
from trading_stack.storage.ledger import append_ledger, read_ledger
from trading_stack.utils.env_loader import load_env

# Load environment variables on import
load_env()

app = typer.Typer()


def _env(k: str, d: str | None = None) -> str:
    """Get required environment variable."""
    v = os.environ.get(k, d)
    if v is None:
        raise RuntimeError(f"Set {k}")
    return v


def check_idempotency(tag: str, ledger_root: str) -> bool:
    """Check if an order with this tag has already been processed."""
    today = datetime.now(UTC).date().isoformat()
    ledger_path = Path(ledger_root) / today / "ledger.parquet"

    if not ledger_path.exists():
        return False

    df = read_ledger(str(ledger_path))
    return not df[df["tag"] == tag].empty


@app.command()
def main(
    queue: str = "data/queue.db",
    ledger_root: str = "data/exec",
    max_loop: int = 0,
    poll_sec: float = 0.25,
) -> None:
    """Run execution worker consuming from intent queue."""
    con = connect(queue)

    # IBKR connection params
    host = os.environ.get("IB_GATEWAY_HOST", "127.0.0.1")
    port = int(os.environ.get("IB_GATEWAY_PORT", "7497"))
    cid = int(os.environ.get("IB_CLIENT_ID", "7"))

    typer.echo(f"Connecting to IBKR at {host}:{port} with client ID {cid}")
    ib = IBKRAdapter(host, port, cid)
    ib.connect()

    # Risk configuration
    risk = RiskConfig(
        max_notional=2000.0,
        price_band_bps=150,
        symbol_whitelist={"SPY"},
        max_open_orders=3,
        daily_loss_stop_pct=1.0,
        killswitch_path="RUN/HALT",
    )

    typer.echo(f"Starting execution worker, queue: {queue}")
    typer.echo(
        f"Risk limits: max_notional={risk.max_notional}, price_band={risk.price_band_bps}bps"
    )

    loops = 0
    while True:
        try:
            row = reserve(con, "order_intents")
            if not row:
                # Update heartbeat even when idle
                from trading_stack.ops.heartbeat import beat
                beat("execd")
                
                time.sleep(poll_sec)
                loops += 1
                if max_loop and loops >= max_loop:
                    break
                continue

            # Extract order details
            tag, payload = row["tag"], row["payload"]
            ts = datetime.now(UTC)
            order = NewOrder.model_validate(payload)

            typer.echo(f"Processing intent: {tag}")

            # Setup ledger path
            day = ts.date().isoformat()
            ledger_path = f"{ledger_root}/{day}/ledger.parquet"

            # Check idempotency
            if check_idempotency(tag, ledger_root):
                typer.echo(f"Order {tag} already processed, skipping")
                ack(con, row["id"])
                continue

            # Log intent received
            append_ledger(
                ledger_path,
                [
                    {
                        "ts": ts,
                        "kind": "INTENT",
                        "tag": tag,
                        "symbol": order.symbol,
                        "side": order.side,
                        "qty": order.qty,
                        "limit": order.limit,
                    }
                ],
            )

            # Risk pre-check (using limit as proxy for last price)
            ok, reason = pretrade_check(order, order.limit or 0.0, risk)

            if not ok:
                typer.echo(f"Risk check failed: {reason}", err=True)
                append_ledger(
                    ledger_path, [{"ts": ts, "kind": "REJ", "tag": tag, "reason": reason}]
                )
                nack(con, row["id"], dead=True)
                continue

            # Place order via IBKR
            try:
                res = ib.place(order)
                order_id = res.trade.order.orderId if hasattr(res.trade.order, "orderId") else None
                append_ledger(
                    ledger_path,
                    [
                        {
                            "ts": ts,
                            "event_ts": res.ack_ts,
                            "kind": "ACK",
                            "tag": tag,
                            "order_id": order_id,
                        }
                    ],
                )
                typer.echo(f"Order placed: {tag} -> trade={res.trade}")
                ack(con, row["id"])

            except Exception as e:
                typer.echo(f"Failed to place order: {e}", err=True)
                append_ledger(
                    ledger_path, [{"ts": ts, "kind": "REJ", "tag": tag, "reason": str(e)}]
                )
                # Recoverable error - return to queue
                nack(con, row["id"], dead=False)

        except KeyboardInterrupt:
            typer.echo("Shutting down...")
            break
        except Exception as e:
            typer.echo(f"Worker error: {e}", err=True)
            time.sleep(1.0)


if __name__ == "__main__":
    app()
