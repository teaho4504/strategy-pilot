# AI-REC-5M-001: High-Liquidity Five-Minute Pullback

Status: implemented as a live-data strategy candidate. It is listed separately
from the existing one-minute and five-minute strategies and defaults to OFF.
When explicitly enabled, it is eligible for the existing live-order pipeline
but remains subject to all shared order and entry safeguards.

## Strategy Blocks

- US common stocks only, USD 5-300.
- Day change +1.5% to +40%.
- Cumulative volume at least 1,000,000 shares.
- Cumulative trade value at least USD 20,000,000.
- Same-time RVOL at least 1.5.
- Bid/ask spread no wider than 0.15%.
- Five-minute close above VWAP and EMA(9) > EMA(20) > EMA(50).
- Three-to-six-bar impulse with at least 1.2% gain and 1.5 times baseline
  volume.
- Two-to-four-bar pullback, 30% to 60% retracement, and pullback volume no
  greater than 70% of impulse volume.
- Reversal close above the previous bar high with renewed volume.
- Stop below the pullback low by 0.1 ATR; reject stop widths over 1.2%.
- +1R partial target, +2R/EMA(9) remainder target, and 15:50 ET force-flat.

## Kiwoom Mapping

| Purpose | Source |
| --- | --- |
| Condition list/search/realtime | `usa20280`, `usa20281`, `usa20290`, `usa20291` |
| Change-rate candidates | `usa20910` |
| Volume candidates | `usa20530` |
| Five-minute chart | `usa06011`, `tic_scope=5` |
| Realtime quote/order book | `FE`, `FT` |
| Orderable amount precheck | `ust31490` |

The strategy does not invent an RVOL value when a same-time historical volume
baseline is unavailable. That criterion remains unavailable and advisory until
historical baseline storage is complete. Available price, liquidity, spread,
trend, pullback, and reversal conditions remain mandatory.
