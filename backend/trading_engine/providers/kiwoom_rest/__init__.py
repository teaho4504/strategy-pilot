"""Kiwoom REST/WebSocket provider skeleton for the paper trading engine.

This package is intentionally non-live by default. It models the contracts
needed for future Kiwoom integration without opening network connections or
exposing credentials.
"""

from trading_engine.providers.kiwoom_rest.adapter import (
    adapt_condition_payload,
    adapt_orderbook_payload,
    adapt_quote_payload,
)
from trading_engine.providers.kiwoom_rest.rest_client import KiwoomRestClientSkeleton
from trading_engine.providers.kiwoom_rest.safety import KiwoomProviderSafety
from trading_engine.providers.kiwoom_rest.websocket_client import KiwoomWebSocketClientSkeleton

__all__ = [
    "KiwoomProviderSafety",
    "KiwoomRestClientSkeleton",
    "KiwoomWebSocketClientSkeleton",
    "adapt_condition_payload",
    "adapt_orderbook_payload",
    "adapt_quote_payload",
]
