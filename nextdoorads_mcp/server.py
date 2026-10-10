"""MCP server and tool registrations for the Nextdoor Ads API."""

from __future__ import annotations

import asyncio
import os
from datetime import date
from typing import Annotated, Any, Literal

from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field
from starlette.applications import Starlette

from nextdoorads_mcp import __version__
from nextdoorads_mcp.client import NextdoorAdsClient
from nextdoorads_mcp.paths import path_id
from nextdoorads_mcp.runtime import LazyClient
from nextdoorads_mcp.runtime import SafeMCPServer as MCPServer

JsonObject = dict[str, Any]
Identifier = Annotated[str, Field(min_length=1, description="The Nextdoor Ads resource ID.")]
AdvertiserId = Annotated[
    str, Field(min_length=1, description="The law firm's Nextdoor advertiser ID.")
]
Cursor = Annotated[
    str | None,
    Field(description="A Nextdoor cursor from a previous list response, or null to start first."),
]
Limit = Annotated[
    int,
    Field(
        ge=1,
        le=1000,
        description="Maximum total records to return; API pages are capped at 500 records.",
    ),
]
Confirmation = Annotated[
    bool,
    Field(description="Must be true to confirm this write operation and its side effects."),
]

Objective = Literal["AWARENESS", "CONSIDERATION", "CONVERSION"]
SubObjective = Literal["WEBSITE_VISITS", "LEAD_GENERATION"]
Placement = Literal["FEED", "FSF", "RHR"]
ReportDimension = Literal["CAMPAIGN", "AD_GROUP", "AD", "PLACEMENT"]
ReportTimeGranularity = Literal["DAY", "WEEK", "MONTH"]
ReportMetric = Literal[
    "CLICKS",
    "IMPRESSIONS",
    "CTR",
    "CONVERSIONS",
    "SPEND",
    "CPM",
    "CPC",
    "BILLABLE_SPEND",
]

mcp = MCPServer(
    "nextdoor-ads",
    title="Nextdoor Ads",
    version=__version__,
    description="Manage and measure approved Nextdoor Ads accounts for US law firms.",
)

_client: NextdoorAdsClient | LazyClient | None = None


def configure_client(client: NextdoorAdsClient | LazyClient) -> None:
    """Set the HTTP client used by registered tools."""
    global _client
    _client = client


def _api() -> NextdoorAdsClient | LazyClient:
    global _client
    if _client is None:
        _client = LazyClient()
    return _client


def _require_confirmation(confirm: bool) -> None:
    if not confirm:
        raise ToolError("This write was not sent because confirm must be true.")


@mcp.tool(structured_output=True)
async def get_authenticated_context() -> JsonObject:
    """Check the token and show the user, profile, advertisers, and roles it can access."""
    return await _api().request("GET", "/me")


@mcp.tool(structured_output=True)
async def list_campaigns(
    advertiser_id: AdvertiserId,
    limit: Limit = 100,
    cursor: Cursor = None,
) -> JsonObject:
    """List campaigns belonging to a law firm's advertiser account."""
    return await _api().paginate(
        "/advertiser/campaign/list",
        body={"advertiser_id": advertiser_id},
        item_key="campaigns",
        limit=limit,
        cursor=cursor,
    )


@mcp.tool(structured_output=True)
async def get_campaign(campaign_id: Identifier) -> JsonObject:
    """Show the configuration of one campaign."""
    return await _api().request("GET", f"/campaign/get/{path_id(campaign_id, 'campaign_id')}")


@mcp.tool(structured_output=True)
async def experimental_get_campaign_stats(
    campaign_id: Identifier,
    advertiser_id: AdvertiserId,
    start_time: Annotated[date, Field(description="First performance date, in YYYY-MM-DD form.")],
    end_time: Annotated[
        date, Field(description="Inclusive last performance date, in YYYY-MM-DD form.")
    ],
) -> JsonObject:
    """Show campaign performance for an inclusive date range using an unverified response shape."""
    return await _api().request(
        "GET",
        f"/campaign/get/{path_id(campaign_id, 'campaign_id')}/stats",
        json_body={
            "advertiser_id": advertiser_id,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
        },
    )


@mcp.tool(structured_output=True)
async def list_ad_groups(
    advertiser_id: AdvertiserId,
    campaign_id: Annotated[str, Field(min_length=1, description="Campaign to list ad groups for.")],
    limit: Limit = 100,
    cursor: Cursor = None,
) -> JsonObject:
    """List budget, schedule, placement, and targeting setups under a campaign."""
    return await _api().paginate(
        "/adgroup/list",
        body={"advertiser_id": advertiser_id, "campaign_id": campaign_id},
        item_key="ad_groups",
        limit=limit,
        cursor=cursor,
    )


@mcp.tool(structured_output=True)
async def get_ad_group_stats(
    ad_group_id: Identifier,
    advertiser_id: AdvertiserId,
    start_time: Annotated[date, Field(description="First performance date, in YYYY-MM-DD form.")],
    end_time: Annotated[
        date, Field(description="Inclusive last performance date, in YYYY-MM-DD form.")
    ],
) -> JsonObject:
    """Show spend, impressions, clicks, conversions, CTR, CPC, and CPM for an ad group."""
    return await _api().request(
        "GET",
        f"/adgroup/get/{path_id(ad_group_id, 'ad_group_id')}/stats",
        json_body={
            "advertiser_id": advertiser_id,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
        },
    )


@mcp.tool(structured_output=True)
async def get_ad_stats(
    ad_id: Identifier,
    advertiser_id: AdvertiserId,
    start_time: Annotated[date, Field(description="First performance date, in YYYY-MM-DD form.")],
    end_time: Annotated[
        date, Field(description="Inclusive last performance date, in YYYY-MM-DD form.")
    ],
) -> JsonObject:
    """Show spend, impressions, clicks, conversions, CTR, CPC, and CPM for one ad."""
    return await _api().request(
        "GET",
        f"/ad/get/{path_id(ad_id, 'ad_id')}/stats",
        json_body={
            "advertiser_id": advertiser_id,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
        },
    )


@mcp.tool(structured_output=True)
async def list_creatives(
    advertiser_id: AdvertiserId,
    limit: Limit = 100,
    cursor: Cursor = None,
) -> JsonObject:
    """List reusable creative assets and their review or status details."""
    return await _api().paginate(
        "/advertiser/creative/list",
        body={"advertiser_id": advertiser_id},
        item_key="creatives",
        limit=limit,
        cursor=cursor,
    )


@mcp.tool(structured_output=True)
async def match_postal_targeting(
    postal_codes: Annotated[
        list[str],
        Field(
            min_length=1,
            max_length=500,
            description=(
                "US ZIP codes in the law firm's service area to resolve into targeting IDs."
            ),
        ),
    ],
) -> JsonObject:
    """Turn service-area ZIP codes into Nextdoor targeting IDs."""
    return await _api().request(
        "GET",
        "/targeting/geo/postalcode/bulk_match",
        json_body={"postal_codes": ",".join(postal_codes)},
    )


@mcp.tool(structured_output=True)
async def experimental_get_report(report_id: Identifier) -> JsonObject:
    """Retrieve a generated report while its exact response format remains unverified."""
    return await _api().request("GET", f"/reporting/get/{path_id(report_id, 'report_id')}")


@mcp.tool(structured_output=True)
async def get_advertiser(advertiser_id: AdvertiserId) -> JsonObject:
    """Show an advertiser's identity, category, billing details, and account balance."""
    return await _api().request("GET", f"/advertiser/get/{path_id(advertiser_id, 'advertiser_id')}")


@mcp.tool(structured_output=True)
async def create_report(
    advertiser_id: AdvertiserId,
    name: Annotated[str, Field(min_length=1, description="Name for the generated report.")],
    recipient_emails: Annotated[
        list[str], Field(min_length=1, description="Email addresses that will receive the report.")
    ],
    dimension_granularity: Annotated[
        list[ReportDimension], Field(min_length=1, description="Reporting breakdowns to include.")
    ],
    time_granularity: Annotated[
        list[ReportTimeGranularity],
        Field(min_length=1, description="Time intervals to include in the report."),
    ],
    metrics: Annotated[
        list[ReportMetric], Field(min_length=1, description="Performance measures to include.")
    ],
    start_time: Annotated[date, Field(description="First report date, in YYYY-MM-DD form.")],
    end_time: Annotated[date, Field(description="Inclusive last report date, in YYYY-MM-DD form.")],
    confirm: Confirmation,
    campaign_ids: Annotated[
        list[str] | None, Field(description="Optional campaign IDs to include.")
    ] = None,
    adgroup_ids: Annotated[
        list[str] | None, Field(description="Optional ad-group IDs to include.")
    ] = None,
    ad_ids: Annotated[list[str] | None, Field(description="Optional ad IDs to include.")] = None,
) -> JsonObject:
    """Generate one report and email it to the specified recipients after confirmation."""
    _require_confirmation(confirm)
    body: JsonObject = {
        "advertiser_id": advertiser_id,
        "name": name,
        "recipient_emails": recipient_emails,
        "dimension_granularity": dimension_granularity,
        "time_granularity": time_granularity,
        "metrics": metrics,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
    }
    for key, value in (
        ("campaign_ids", campaign_ids),
        ("adgroup_ids", adgroup_ids),
        ("ad_ids", ad_ids),
    ):
        if value is not None:
            body[key] = value
    return await _api().request("POST", "/reporting/create", json_body=body)


@mcp.tool(structured_output=True)
async def create_campaign(
    advertiser_id: AdvertiserId,
    name: Annotated[str, Field(min_length=1, description="Name for the new campaign.")],
    objective: Annotated[Objective, Field(description="Primary campaign objective.")],
    confirm: Confirmation,
    sub_objective: Annotated[
        SubObjective | None,
        Field(description="Optional consideration goal: website visits or lead generation."),
    ] = None,
) -> JsonObject:
    """Create a campaign container without creating or activating an ad after confirmation."""
    _require_confirmation(confirm)
    if sub_objective is not None and objective != "CONSIDERATION":
        raise ValueError("sub_objective is only documented for the CONSIDERATION objective.")
    body: JsonObject = {
        "advertiser_id": advertiser_id,
        "name": name,
        "objective": objective,
    }
    if sub_objective is not None:
        body["sub_objective"] = sub_objective
    return await _api().request("POST", "/campaign/create", json_body=body)


@mcp.tool(structured_output=True)
async def experimental_create_ad_group(
    advertiser_id: AdvertiserId,
    campaign_id: Annotated[str, Field(min_length=1, description="Parent campaign ID.")],
    name: Annotated[str, Field(min_length=1, description="Name for the new ad group.")],
    placements: Annotated[
        list[Placement],
        Field(min_length=1, description="Permanent placements: FEED, FSF, or RHR."),
    ],
    bid: Annotated[
        dict[str, Any],
        Field(description="Bid object; money amounts use strings such as 'USD 10'."),
    ],
    budget: Annotated[
        dict[str, Any],
        Field(description="Budget object; money amounts use strings such as 'USD 10'."),
    ],
    start_time: Annotated[
        str,
        Field(
            min_length=1,
            description="Zoned ISO-8601 start time, including the named zone when required.",
        ),
    ],
    confirm: Confirmation,
    end_time: Annotated[
        str | None,
        Field(description="Optional zoned ISO-8601 end time; documentation is contradictory."),
    ] = None,
    frequency_caps: Annotated[
        list[dict[str, Any]] | None,
        Field(description="Optional frequency-cap objects; requiredness is unverified."),
    ] = None,
    targeting: Annotated[
        dict[str, Any] | None, Field(description="Optional location and audience targeting object.")
    ] = None,
    custom_audience_targeting: Annotated[
        dict[str, Any] | None, Field(description="Optional custom-audience include/exclude object.")
    ] = None,
) -> JsonObject:
    """Create an ad group after confirmation with fields needing live verification."""
    _require_confirmation(confirm)
    body: JsonObject = {
        "advertiser_id": advertiser_id,
        "campaign_id": campaign_id,
        "name": name,
        "placements": placements,
        "bid": bid,
        "budget": budget,
        "start_time": start_time,
    }
    for key, value in (
        ("end_time", end_time),
        ("frequency_caps", frequency_caps),
        ("targeting", targeting),
        ("custom_audience_targeting", custom_audience_targeting),
    ):
        if value is not None:
            body[key] = value
    return await _api().request("POST", "/adgroup/create", json_body=body)


STREAMABLE_HTTP_TRANSPORT = "streamable-http"
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _requested_transport() -> str:
    return os.environ.get("NEXTDOORADS_MCP_TRANSPORT", "stdio").strip().lower() or "stdio"


def _host() -> str:
    return os.environ.get("NEXTDOORADS_MCP_HOST", "127.0.0.1").strip() or "127.0.0.1"


def _port() -> int:
    raw = os.environ.get("PORT", "8080").strip()
    try:
        return int(raw)
    except ValueError:
        raise SystemExit(f"PORT must be an integer, got {raw!r}") from None


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _transport_security() -> TransportSecuritySettings | None:
    """Origin checks are required off loopback; the SDK covers loopback binds."""
    host = _host()
    if host in _LOOPBACK_HOSTS:
        return None
    allowed_hosts = _split_csv(os.environ.get("NEXTDOORADS_MCP_ALLOWED_HOSTS", ""))
    if not allowed_hosts:
        raise SystemExit(
            f"NEXTDOORADS_MCP_ALLOWED_HOSTS must be set when NEXTDOORADS_MCP_HOST is {host!r}."
        )
    allowed_origins = _split_csv(os.environ.get("NEXTDOORADS_MCP_ALLOWED_ORIGINS", ""))
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    )


def create_serve_app() -> Starlette:
    """Build the stateless Streamable HTTP app. Credentials stay in the environment."""
    return mcp.streamable_http_app(
        streamable_http_path="/mcp",
        host=_host(),
        stateless_http=True,
        transport_security=_transport_security(),
    )


async def _serve_streamable_http() -> None:
    import uvicorn

    config = uvicorn.Config(
        create_serve_app(),
        host=_host(),
        port=_port(),
        access_log=False,
    )
    await uvicorn.Server(config).serve()


def main() -> None:
    """Serve stdio or stateless Streamable HTTP. Any other transport exits."""
    transport = _requested_transport()
    if transport == "stdio":
        configure_client(LazyClient())
        mcp.run(transport="stdio")
        return
    if transport == STREAMABLE_HTTP_TRANSPORT:
        asyncio.run(_serve_streamable_http())
        return
    raise SystemExit(
        "Unsupported NEXTDOORADS_MCP_TRANSPORT "
        f"{transport!r}; expected 'stdio' or '{STREAMABLE_HTTP_TRANSPORT}'."
    )


def cli() -> int:
    """Run stdio or streamable HTTP with deferred client configuration."""
    main()
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
