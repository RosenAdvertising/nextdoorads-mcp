from __future__ import annotations

import json

import httpx
import pytest
import respx

from nextdoorads_mcp.client import MAX_PAGE_SIZE, NextdoorAdsAPIError, NextdoorAdsClient
from nextdoorads_mcp.config import Settings
from tests.conftest import TEST_BASE_URL, TEST_TOKEN


@respx.mock
@pytest.mark.asyncio
async def test_happy_path_sends_bearer_token_and_get_body(settings: Settings) -> None:
    route = respx.get(f"{TEST_BASE_URL}/campaign/get/campaign-1/stats").mock(
        return_value=httpx.Response(200, json={"clicks": 12})
    )
    client = NextdoorAdsClient(settings, max_retries=0)

    result = await client.request(
        "GET",
        "/campaign/get/campaign-1/stats",
        json_body={"advertiser_id": "advertiser-1"},
    )

    assert result == {"clicks": 12}
    request = route.calls[0].request
    assert request.headers["Authorization"] == f"Bearer {TEST_TOKEN}"
    assert json.loads(request.content) == {"advertiser_id": "advertiser-1"}


@respx.mock
@pytest.mark.asyncio
async def test_auth_failure_surfaces_vendor_message(settings: Settings) -> None:
    respx.get(f"{TEST_BASE_URL}/me").mock(
        return_value=httpx.Response(401, json={"message": "The access token is invalid"})
    )
    client = NextdoorAdsClient(settings, max_retries=0)

    with pytest.raises(NextdoorAdsAPIError) as caught:
        await client.request("GET", "/me")

    assert caught.value.status_code == 401
    assert caught.value.vendor_message == "The access token is invalid"
    assert "The access token is invalid" in str(caught.value)


@respx.mock
@pytest.mark.asyncio
async def test_429_is_retried_with_retry_after(settings: Settings) -> None:
    delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    route = respx.get(f"{TEST_BASE_URL}/me").mock(
        side_effect=[
            httpx.Response(429, json={"message": "Slow down"}, headers={"Retry-After": "2"}),
            httpx.Response(200, json={"user": {"id": "user-1"}}),
        ]
    )
    client = NextdoorAdsClient(settings, max_retries=2, sleep=record_sleep)

    result = await client.request("GET", "/me")

    assert result == {"user": {"id": "user-1"}}
    assert route.call_count == 2
    assert delays == [2.0]


@respx.mock
@pytest.mark.asyncio
async def test_5xx_is_retried_with_exponential_jitter(settings: Settings) -> None:
    delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    route = respx.get(f"{TEST_BASE_URL}/me").mock(
        side_effect=[
            httpx.Response(599, json={"message": "Temporary vendor failure"}),
            httpx.Response(200, json={"user": {"id": "user-1"}}),
        ]
    )
    client = NextdoorAdsClient(
        settings,
        max_retries=2,
        backoff_base_seconds=0.5,
        sleep=record_sleep,
        jitter=lambda: 0.5,
    )

    result = await client.request("GET", "/me")

    assert result == {"user": {"id": "user-1"}}
    assert route.call_count == 2
    assert delays == [0.25]


@respx.mock
@pytest.mark.asyncio
async def test_pagination_caps_pages_and_passes_cursor(settings: Settings) -> None:
    request_bodies: list[dict[str, object]] = []

    def page_response(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        request_bodies.append(body)
        pagination = body["pagination_parameters"]
        if pagination["cursor"] is None:
            return httpx.Response(
                200,
                json={
                    "campaigns": [{"id": f"campaign-{index}"} for index in range(MAX_PAGE_SIZE)],
                    "page_info": {"end_cursor": "page-2", "page_size": MAX_PAGE_SIZE},
                },
            )
        return httpx.Response(
            200,
            json={
                "campaigns": [{"id": f"campaign-{index}"} for index in range(500, 600)],
                "page_info": {"end_cursor": None, "page_size": 100},
            },
        )

    route = respx.get(f"{TEST_BASE_URL}/advertiser/campaign/list").mock(side_effect=page_response)
    client = NextdoorAdsClient(settings, max_retries=0)

    result = await client.paginate(
        "/advertiser/campaign/list",
        body={"advertiser_id": "advertiser-1"},
        item_key="campaigns",
        limit=600,
    )

    assert route.call_count == 2
    assert len(result["campaigns"]) == 600
    assert result["returned_count"] == 600
    assert result["next_cursor"] is None
    assert request_bodies[0]["pagination_parameters"] == {
        "page_size": 500,
        "cursor": None,
    }
    assert request_bodies[1]["pagination_parameters"] == {
        "page_size": 100,
        "cursor": "page-2",
    }


@respx.mock
@pytest.mark.asyncio
async def test_successful_csv_response_becomes_structured_json(settings: Settings) -> None:
    respx.get(f"{TEST_BASE_URL}/reporting/get/report-1").mock(
        return_value=httpx.Response(
            200,
            text="campaign_id,clicks\ncampaign-1,7\n",
            headers={"Content-Type": "text/csv"},
        )
    )
    client = NextdoorAdsClient(settings, max_retries=0)

    result = await client.request("GET", "/reporting/get/report-1")

    assert result == {
        "content": "campaign_id,clicks\ncampaign-1,7\n",
        "content_type": "text/csv",
    }
