from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable
from ipaddress import ip_address, ip_network

from fastapi import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings


RateBucket = deque[float]
_rate_buckets: dict[tuple[str, str], RateBucket] = defaultdict(deque)


def reset_security_state() -> None:
    _rate_buckets.clear()


def client_ip(request: Request) -> str:
    settings = get_settings()
    if settings.backend_trust_proxy_headers:
        forwarded_for = request.headers.get("x-forwarded-for", "")
        first_ip = forwarded_for.split(",", 1)[0].strip()
        if first_ip:
            return first_ip
    return request.client.host if request.client else "unknown"


async def security_middleware(request: Request, call_next: Callable) -> Response:
    if request.method == "OPTIONS":
        return await call_next(request)

    settings = get_settings()
    ip_address = client_ip(request)

    if settings.backend_allowed_client_ips and not _client_ip_allowed(ip_address, settings.backend_allowed_client_ips):
        return JSONResponse(
            status_code=403,
            content={"detail": {"message": "Client IP is not allowed"}},
        )

    rate_limit_name = _rate_limit_name(request.url.path)
    if rate_limit_name:
        limit = _parse_rate_limit(
            settings.backend_auth_rate_limit if rate_limit_name == "auth" else settings.backend_order_rate_limit
        )
        if limit and not _allow_rate(rate_limit_name, ip_address, limit[0], limit[1]):
            return JSONResponse(
                status_code=429,
                content={"detail": {"message": "Too many requests"}},
                headers={"Retry-After": str(limit[1])},
            )

    return await call_next(request)


def _rate_limit_name(path: str) -> str | None:
    if path.startswith("/api/auth/"):
        return "auth"
    if path.startswith("/api/us/orders"):
        return "order"
    return None


def _client_ip_allowed(ip_value: str, allowed_values: set[str]) -> bool:
    if ip_value in allowed_values:
        return True
    try:
        parsed_ip = ip_address(ip_value)
    except ValueError:
        return False
    for allowed in allowed_values:
        if "/" not in allowed:
            continue
        try:
            if parsed_ip in ip_network(allowed, strict=False):
                return True
        except ValueError:
            continue
    return False


def _parse_rate_limit(value: str) -> tuple[int, int] | None:
    raw = value.strip()
    if not raw:
        return None
    if "/" in raw:
        count_text, seconds_text = raw.split("/", 1)
    else:
        count_text, seconds_text = raw, "60"
    try:
        count = int(count_text.strip())
        seconds = int(seconds_text.strip())
    except ValueError:
        return None
    if count <= 0 or seconds <= 0:
        return None
    return count, seconds


def _allow_rate(name: str, ip_address: str, count: int, seconds: int) -> bool:
    now = time.monotonic()
    bucket = _rate_buckets[(name, ip_address)]
    while bucket and now - bucket[0] > seconds:
        bucket.popleft()
    if len(bucket) >= count:
        return False
    bucket.append(now)
    return True
