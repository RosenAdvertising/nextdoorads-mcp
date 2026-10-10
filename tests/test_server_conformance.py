from __future__ import annotations

import re

import pytest
from mcp import Client

from nextdoorads_mcp.server import mcp

EXPECTED_PROTOCOL_VERSION = "2026-07-28"


@pytest.mark.asyncio
async def test_server_declares_2026_07_28_protocol_revision() -> None:
    async with Client(mcp) as client:
        assert client.protocol_version == EXPECTED_PROTOCOL_VERSION


@pytest.mark.asyncio
async def test_tool_metadata_is_structured_described_and_safe() -> None:
    async with Client(mcp) as client:
        result = await client.list_tools()

    assert len(result.tools) == 14
    for tool in result.tools:
        assert re.fullmatch(r"[a-z][a-z0-9_]*", tool.name)
        assert tool.description
        assert "\n" not in tool.description
        assert tool.output_schema is not None
        for parameter in tool.input_schema.get("properties", {}).values():
            assert parameter.get("description")

    by_name = {tool.name: tool for tool in result.tools}
    for write_name in ("create_report", "create_campaign", "experimental_create_ad_group"):
        schema = by_name[write_name].input_schema
        assert "confirm" in schema["required"]
        assert schema["properties"]["confirm"]["type"] == "boolean"
