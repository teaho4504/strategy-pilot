"""US stock Kiwoom TR inventory and safe request builders.

The module is local-only scaffolding. It does not perform HTTP/WebSocket
requests and it does not expose an executable order path.
"""

from trading_engine.providers.kiwoom_us.adapter import (
    adapt_us_condition_payload,
    adapt_us_orderbook_payload,
    adapt_us_quote_payload,
    build_account_balance_request,
    build_daily_account_return_request,
    build_profit_loss_request,
    build_realtime_price_subscription,
    map_us_account_balance_response,
    map_us_condition_search_response,
)
from trading_engine.providers.kiwoom_us.credentials import KiwoomUsCredentialConfig, MissingCredentialError
from trading_engine.providers.kiwoom_us.http_transport import KiwoomUsHttpReadOnlyTransport, KiwoomUsTransportError
from trading_engine.providers.kiwoom_us.order_event_mapper import (
    UsBrokerOrderEvent,
    UsOrderEventMappingError,
    map_us_order_realtime_payload,
)
from trading_engine.providers.kiwoom_us.response_mapper import UsMappingError, map_daily_account_return_response
from trading_engine.providers.kiwoom_us.rest_client import KiwoomUsRestClientSkeleton
from trading_engine.providers.kiwoom_us.request_builder import (
    build_condition_clear_request,
    build_condition_list_request,
    build_condition_search_request,
    build_readonly_request,
    build_realtime_registration,
    build_us_order_request_blocked,
)
from trading_engine.providers.kiwoom_us.smoke_plan import (
    US_READONLY_HTTP_SENDER_CONFIRM,
    US_READONLY_SMOKE_CONFIRM,
    US_READONLY_SMOKE_STEPS,
    resolve_us_readonly_smoke_body,
    safe_smoke_result_summary,
    select_us_readonly_smoke_steps,
    validate_us_readonly_http_sender_environment,
    validate_us_readonly_smoke_environment,
    validate_us_readonly_smoke_plan,
)
from trading_engine.providers.kiwoom_us.transport import FakeKiwoomUsTransport, KiwoomUsReadOnlyTransport
from trading_engine.providers.kiwoom_us.tr_codes import US_TR_INVENTORY, UsTrCategory, UsTrSpec

__all__ = [
    "FakeKiwoomUsTransport",
    "KiwoomUsCredentialConfig",
    "KiwoomUsHttpReadOnlyTransport",
    "KiwoomUsReadOnlyTransport",
    "US_TR_INVENTORY",
    "US_READONLY_SMOKE_CONFIRM",
    "US_READONLY_HTTP_SENDER_CONFIRM",
    "US_READONLY_SMOKE_STEPS",
    "KiwoomUsRestClientSkeleton",
    "MissingCredentialError",
    "KiwoomUsTransportError",
    "UsMappingError",
    "UsBrokerOrderEvent",
    "UsOrderEventMappingError",
    "UsTrCategory",
    "UsTrSpec",
    "adapt_us_condition_payload",
    "adapt_us_orderbook_payload",
    "adapt_us_quote_payload",
    "build_account_balance_request",
    "build_daily_account_return_request",
    "build_condition_clear_request",
    "build_condition_list_request",
    "build_condition_search_request",
    "build_profit_loss_request",
    "build_readonly_request",
    "build_realtime_price_subscription",
    "build_realtime_registration",
    "build_us_order_request_blocked",
    "map_us_account_balance_response",
    "map_us_condition_search_response",
    "map_daily_account_return_response",
    "map_us_order_realtime_payload",
    "resolve_us_readonly_smoke_body",
    "safe_smoke_result_summary",
    "select_us_readonly_smoke_steps",
    "validate_us_readonly_http_sender_environment",
    "validate_us_readonly_smoke_environment",
    "validate_us_readonly_smoke_plan",
]
