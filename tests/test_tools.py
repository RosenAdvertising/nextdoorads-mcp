from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx
from mcp import Client

from nextdoorads_mcp.server import mcp
from tests.conftest import TEST_BASE_URL, TEST_TOKEN


async def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.call_tool(name, arguments)
    assert not result.is_error
    assert result.structured_content is not None
    return result.structured_content


READ_TOOL_CASES = [
    (
        "get_authenticated_context",
        {},
        "GET",
        "/me",
        None,
        {"user": {"id": "user-1"}, "profile": {"id": "profile-1"}},
    ),
    (
        "get_campaign",
        {"campaign_id": "campaign-1"},
        "GET",
        "/campaign/get/campaign-1",
        None,
        {"id": "campaign-1", "name": "Injury leads", "objective": "CONSIDERATION"},
    ),
    (
        "experimental_get_campaign_stats",
        {
            "campaign_id": "campaign-1",
            "advertiser_id": "advertiser-1",
            "start_time": "2026-07-01",
            "end_time": "2026-07-31",
        },
        "GET",
        "/campaign/get/campaign-1/stats",
        {
            "advertiser_id": "advertiser-1",
            "start_time": "2026-07-01",
            "end_time": "2026-07-31",
        },
        {"stats": {"clicks": 17}},
    ),
    (
        "get_ad_group_stats",
        {
            "ad_group_id": "adgroup-1",
            "advertiser_id": "advertiser-1",
            "start_time": "2026-07-01",
            "end_time": "2026-07-31",
        },
        "GET",
        "/adgroup/get/adgroup-1/stats",
        {
            "advertiser_id": "advertiser-1",
            "start_time": "2026-07-01",
            "end_time": "2026-07-31",
        },
        {"clicks": 8, "impressions": 500, "total_conversions": 2},
    ),
    (
        "get_ad_stats",
        {
            "ad_id": "ad-1",
            "advertiser_id": "advertiser-1",
            "start_time": "2026-07-01",
            "end_time": "2026-07-31",
        },
        "GET",
        "/ad/get/ad-1/stats",
        {
            "advertiser_id": "advertiser-1",
            "start_time": "2026-07-01",
            "end_time": "2026-07-31",
        },
        {"clicks": 4, "impressions": 300, "total_conversions": 1},
    ),
    (
        "match_postal_targeting",
        {"postal_codes": ["10001", "11201"]},
        "GET",
        "/targeting/geo/postalcode/bulk_match",
        {"postal_codes": "10001,11201"},
        {"matches": [{"postal_code": "10001", "id": "postal-1"}]},
    ),
    (
        "get_advertiser",
        {"advertiser_id": "advertiser-1"},
        "GET",
        "/advertiser/get/advertiser-1",
        None,
        {"id": "advertiser-1", "name": "Example Law"},
    ),
]


@pytest.mark.parametrize(
    ("tool_name", "arguments", "method", "path", "expected_body", "response_payload"),
    READ_TOOL_CASES,
    ids=[case[0] for case in READ_TOOL_CASES],
)
@respx.mock
@pytest.mark.asyncio
async def test_read_tool_round_trip(
    tool_name: str,
    arguments: dict[str, Any],
    method: str,
    path: str,
    expected_body: dict[str, Any] | None,
    response_payload: dict[str, Any],
) -> None:
    route = respx.request(method, f"{TEST_BASE_URL}{path}").mock(
        return_value=httpx.Response(200, json=response_payload)
    )

    result = await call_tool(tool_name, arguments)

    assert result == response_payload
    assert route.call_count == 1
    request = route.calls[0].request
    assert request.headers["Authorization"] == f"Bearer {TEST_TOKEN}"
    if expected_body is None:
        assert not request.content
    else:
        assert json.loads(request.content) == expected_body


LIST_TOOL_CASES = [
    (
        "list_campaigns",
        {"advertiser_id": "advertiser-1", "limit": 2},
        "/advertiser/campaign/list",
        "campaigns",
        {"advertiser_id": "advertiser-1"},
    ),
    (
        "list_ad_groups",
        {"advertiser_id": "advertiser-1", "campaign_id": "campaign-1", "limit": 2},
        "/adgroup/list",
        "ad_groups",
        {"advertiser_id": "advertiser-1", "campaign_id": "campaign-1"},
    ),
    (
        "list_creatives",
        {"advertiser_id": "advertiser-1", "limit": 2},
        "/advertiser/creative/list",
        "creatives",
        {"advertiser_id": "advertiser-1"},
    ),
]


@pytest.mark.parametrize(
    ("tool_name", "arguments", "path", "item_key", "base_body"),
    LIST_TOOL_CASES,
    ids=[case[0] for case in LIST_TOOL_CASES],
)
@respx.mock
@pytest.mark.asyncio
async def test_list_tool_round_trip(
    tool_name: str,
    arguments: dict[str, Any],
    path: str,
    item_key: str,
    base_body: dict[str, Any],
) -> None:
    items = [{"id": "item-1"}, {"id": "item-2"}]
    route = respx.get(f"{TEST_BASE_URL}{path}").mock(
        return_value=httpx.Response(
            200,
            json={item_key: items, "page_info": {"end_cursor": None, "page_size": 2}},
        )
    )

    result = await call_tool(tool_name, arguments)

    assert result[item_key] == items
    assert result["returned_count"] == 2
    expected_body = {
        **base_body,
        "pagination_parameters": {"page_size": 2, "cursor": None},
    }
    assert json.loads(route.calls[0].request.content) == expected_body


@respx.mock
@pytest.mark.asyncio
async def test_experimental_get_report_round_trip() -> None:
    route = respx.get(f"{TEST_BASE_URL}/reporting/get/report-1").mock(
        return_value=httpx.Response(
            200,
            text="campaign_id,clicks\ncampaign-1,11\n",
            headers={"Content-Type": "text/csv"},
        )
    )

    result = await call_tool("experimental_get_report", {"report_id": "report-1"})

    assert result["content_type"] == "text/csv"
    assert "campaign-1,11" in result["content"]
    assert route.call_count == 1


WRITE_TOOL_CASES = [
    (
        "create_report",
        {
            "advertiser_id": "advertiser-1",
            "name": "July lead report",
            "recipient_emails": ["reports@example.test"],
            "dimension_granularity": ["CAMPAIGN"],
            "time_granularity": ["DAY"],
            "metrics": ["CLICKS", "CONVERSIONS"],
            "start_time": "2026-07-01",
            "end_time": "2026-07-31",
            "confirm": True,
            "campaign_ids": ["campaign-1"],
        },
        "/reporting/create",
        {
            "advertiser_id": "advertiser-1",
            "name": "July lead report",
            "recipient_emails": ["reports@example.test"],
            "dimension_granularity": ["CAMPAIGN"],
            "time_granularity": ["DAY"],
            "metrics": ["CLICKS", "CONVERSIONS"],
            "start_time": "2026-07-01",
            "end_time": "2026-07-31",
            "campaign_ids": ["campaign-1"],
        },
    ),
    (
        "create_campaign",
        {
            "advertiser_id": "advertiser-1",
            "name": "Local injury leads",
            "objective": "CONSIDERATION",
            "sub_objective": "LEAD_GENERATION",
            "confirm": True,
        },
        "/campaign/create",
        {
            "advertiser_id": "advertiser-1",
            "name": "Local injury leads",
            "objective": "CONSIDERATION",
            "sub_objective": "LEAD_GENERATION",
        },
    ),
    (
        "experimental_create_ad_group",
        {
            "advertiser_id": "advertiser-1",
            "campaign_id": "campaign-1",
            "name": "Brooklyn ZIPs",
            "placements": ["FEED"],
            "bid": {"pricing_type": "CPM", "amount": "USD 10"},
            "budget": {"budget_type": "DAILY_CAP_MONEY", "amount": "USD 100"},
            "start_time": "2026-08-10T09:00:00-04:00[America/New_York]",
            "targeting": {"included_location_targeting_ids": ["postal-1"]},
            "confirm": True,
        },
        "/adgroup/create",
        {
            "advertiser_id": "advertiser-1",
            "campaign_id": "campaign-1",
            "name": "Brooklyn ZIPs",
            "placements": ["FEED"],
            "bid": {"pricing_type": "CPM", "amount": "USD 10"},
            "budget": {"budget_type": "DAILY_CAP_MONEY", "amount": "USD 100"},
            "start_time": "2026-08-10T09:00:00-04:00[America/New_York]",
            "targeting": {"included_location_targeting_ids": ["postal-1"]},
        },
    ),
]


@pytest.mark.parametrize(
    ("tool_name", "arguments", "path", "expected_body"),
    WRITE_TOOL_CASES,
    ids=[case[0] for case in WRITE_TOOL_CASES],
)
@respx.mock
@pytest.mark.asyncio
async def test_write_tool_round_trip(
    tool_name: str,
    arguments: dict[str, Any],
    path: str,
    expected_body: dict[str, Any],
) -> None:
    route = respx.post(f"{TEST_BASE_URL}{path}").mock(
        return_value=httpx.Response(200, json={"id": "created-1"})
    )

    result = await call_tool(tool_name, arguments)

    assert result == {"id": "created-1"}
    assert json.loads(route.calls[0].request.content) == expected_body


@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        ("create_report", WRITE_TOOL_CASES[0][1]),
        ("create_campaign", WRITE_TOOL_CASES[1][1]),
        ("experimental_create_ad_group", WRITE_TOOL_CASES[2][1]),
    ],
)
@respx.mock
@pytest.mark.asyncio
async def test_write_tools_reject_missing_confirmation(
    tool_name: str, arguments: dict[str, Any]
) -> None:
    unconfirmed = {**arguments, "confirm": False}

    async with Client(mcp) as client:
        result = await client.call_tool(tool_name, unconfirmed)

    assert result.is_error
    assert "confirm must be true" in result.content[0].text
    assert respx.calls.call_count == 0
