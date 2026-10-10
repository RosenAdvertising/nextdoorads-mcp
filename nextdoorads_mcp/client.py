"""Thin asynchronous HTTP client for the Nextdoor Ads API."""

from __future__ import annotations

import asyncio
import json
import random
import time
from collections import deque
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import httpx

from nextdoorads_mcp.config import Settings

MAX_PAGE_SIZE = 500
RATE_LIMIT_REQUESTS = 100
RATE_LIMIT_PERIOD_SECONDS = 60.0
JsonObject = dict[str, Any]
Sleep = Callable[[float], Awaitable[None]]


class NextdoorAdsAPIError(RuntimeError):
    """An HTTP error returned by the Nextdoor Ads API."""

    def __init__(self, status_code: int, message: str, body: str) -> None:
        self.status_code = status_code
        self.vendor_message = message
        self.body = body
        super().__init__(f"Nextdoor Ads API returned HTTP {status_code}: {message}")


class NextdoorAdsResponseError(RuntimeError):
    """A malformed successful response returned by the Nextdoor Ads API."""


class RequestRateLimiter:
    """Process-local sliding-window limiter for the documented 100 requests/minute."""

    def __init__(
        self,
        max_requests: int = RATE_LIMIT_REQUESTS,
        period_seconds: float = RATE_LIMIT_PERIOD_SECONDS,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._max_requests = max_requests
        self._period_seconds = period_seconds
        self._clock = clock
        self._sleep = sleep
        self._timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until one request is available in the local rate-limit window."""
        while True:
            async with self._lock:
                now = self._clock()
                cutoff = now - self._period_seconds
                while self._timestamps and self._timestamps[0] <= cutoff:
                    self._timestamps.popleft()

                if len(self._timestamps) < self._max_requests:
                    self._timestamps.append(now)
                    return

                delay = max(0.0, self._timestamps[0] + self._period_seconds - now)
            await self._sleep(delay)


class NextdoorAdsClient:
    """Bearer-authenticated client with retries, throttling, and cursor pagination."""

    def __init__(
        self,
        settings: Settings,
        *,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        backoff_base_seconds: float = 0.5,
        rate_limiter: RequestRateLimiter | None = None,
        sleep: Sleep = asyncio.sleep,
        jitter: Callable[[], float] = random.random,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = settings.base_url.rstrip("/")
        self._access_token = settings.access_token
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._backoff_base_seconds = backoff_base_seconds
        self._rate_limiter = rate_limiter or RequestRateLimiter()
        self._sleep = sleep
        self._jitter = jitter
        self._transport = transport

    async def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Mapping[str, Any] | None = None,
    ) -> JsonObject:
        """Send one API request and return a JSON-serializable object."""
        url = f"{self._base_url}/{path.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json, text/csv",
        }

        async with httpx.AsyncClient(
            timeout=self._timeout_seconds,
            transport=self._transport,
        ) as http_client:
            for attempt in range(self._max_retries + 1):
                await self._rate_limiter.acquire()
                response = await http_client.request(
                    method,
                    url,
                    headers=headers,
                    json=dict(json_body) if json_body is not None else None,
                )
                if response.status_code != 429 and not 500 <= response.status_code < 600:
                    break
                if attempt == self._max_retries:
                    break
                await self._sleep(self._retry_delay(response, attempt))

        if response.is_error:
            message = _vendor_error_message(response)
            raise NextdoorAdsAPIError(response.status_code, message, response.text)
        return _structured_response(response)

    async def paginate(
        self,
        path: str,
        *,
        body: Mapping[str, Any],
        item_key: str,
        limit: int,
        cursor: str | None = None,
    ) -> JsonObject:
        """Collect cursor-paginated results without exceeding the vendor page-size cap."""
        if limit < 1:
            raise ValueError("limit must be at least 1")

        items: list[Any] = []
        next_cursor = cursor
        last_page_info: JsonObject = {"end_cursor": cursor, "page_size": 0}

        while len(items) < limit:
            page_size = min(MAX_PAGE_SIZE, limit - len(items))
            request_body = dict(body)
            request_body["pagination_parameters"] = {
                "page_size": page_size,
                "cursor": next_cursor,
            }
            payload = await self.request("GET", path, json_body=request_body)
            page_items = _page_items(payload, item_key)
            items.extend(page_items[:page_size])

            page_info = payload.get("page_info")
            if not isinstance(page_info, dict):
                raise NextdoorAdsResponseError(
                    "Nextdoor Ads pagination response omitted object field "
                    f"'page_info': {payload!r}"
                )
            last_page_info = dict(page_info)
            end_cursor = page_info.get("end_cursor")
            if end_cursor is not None and not isinstance(end_cursor, str):
                raise NextdoorAdsResponseError(
                    "Nextdoor Ads pagination response contained a non-string end_cursor"
                )
            next_cursor = end_cursor
            if next_cursor is None or not page_items:
                break

        return {
            item_key: items,
            "page_info": last_page_info,
            "returned_count": len(items),
            "next_cursor": next_cursor,
        }

    def _retry_delay(self, response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after is not None:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                pass
        exponential_cap = self._backoff_base_seconds * (2**attempt)
        return self._jitter() * exponential_cap


def _page_items(payload: JsonObject, item_key: str) -> list[Any]:
    value = payload.get(item_key)
    if isinstance(value, list):
        return value

    candidates = [candidate for candidate in payload.values() if isinstance(candidate, list)]
    if len(candidates) == 1:
        return candidates[0]
    raise NextdoorAdsResponseError(
        f"Nextdoor Ads pagination response omitted list field '{item_key}': {payload!r}"
    )


def _structured_response(response: httpx.Response) -> JsonObject:
    if not response.content:
        return {}
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return {
            "content": response.text,
            "content_type": response.headers.get("Content-Type", "application/octet-stream"),
        }

    if isinstance(payload, dict):
        return payload
    return {"data": payload}


def _vendor_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return response.text.strip() or response.reason_phrase

    if isinstance(payload, dict):
        for key in ("message", "detail", "error"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
            if isinstance(value, dict):
                nested_message = value.get("message")
                if isinstance(nested_message, str) and nested_message:
                    return nested_message
    return json.dumps(payload, ensure_ascii=False)
