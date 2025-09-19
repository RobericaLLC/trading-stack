from trading_stack.tca.metrics import TCA


def test_shortfall_signs() -> None:
    assert round(TCA(arrival=100.0, fills_wavg=100.2, side="BUY").shortfall_bps, 1) == 20.0
    assert round(TCA(arrival=100.0, fills_wavg=99.8, side="SELL").shortfall_bps, 1) == 20.0
