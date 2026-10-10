"""In-process Streamable HTTP checks against create_serve_app()."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from mcp import Client

from nextdoorads_mcp import server
from tests.conftest import TEST_BASE_URL

PROTOCOL_VERSION = "2026-07-28"
PROTOCOL_VERSION_META_KEY = "io.modelcontextprotocol/protocolVersion"
CLIENT_CAPABILITIES_META_KEY = "io.modelcontextprotocol/clientCapabilities"
CLIENT_INFO_META_KEY = "io.modelcontextprotocol/clientInfo"
SERVER_INFO_META_KEY = "io.modelcontextprotocol/serverInfo"
HTTP_ENV_VARS = (
    "NEXTDOORADS_MCP_TRANSPORT",
    "NEXTDOORADS_MCP_HOST",
    "NEXTDOORADS_MCP_ALLOWED_HOSTS",
    "NEXTDOORADS_MCP_ALLOWED_ORIGINS",
    "PORT",
)


@pytest.fixture(autouse=True)
def _clear_http_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in HTTP_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def _modern_request(
    method: str,
    params: dict[str, Any] | None = None,
    *,
    header_overrides: dict[str, str] | None = None,
) -> tuple[dict[str, str], dict[str, Any]]:
    request_params = dict(params or {})
    request_params["_meta"] = {
        PROTOCOL_VERSION_META_KEY: PROTOCOL_VERSION,
        CLIENT_CAPABILITIES_META_KEY: {},
        CLIENT_INFO_META_KEY: {"name": "nextdoorads-http-test", "version": "0"},
    }
    headers = {
        "accept": "application/json, text/event-stream",
        "content-type": "application/json",
        "mcp-protocol-version": PROTOCOL_VERSION,
        "mcp-method": method,
    }
    if method == "tools/call":
        headers["mcp-name"] = str(request_params["name"])
    elif method == "resources/read":
        headers["mcp-name"] = str(request_params["uri"])
    if header_overrides:
        headers.update(header_overrides)
    return headers, {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": request_params,
    }


def _payload(response: httpx.Response) -> dict[str, Any]:
    content_type = response.headers.get("content-type", "")
    if "text/event-stream" in content_type:
        data_lines = [
            line[len("data:") :].strip()
            for line in response.text.splitlines()
            if line.startswith("data:")
        ]
        assert data_lines, response.text
        return json.loads(data_lines[-1])
    return response.json()


async def _post(
    app: Any,
    method: str,
    params: dict[str, Any] | None = None,
    *,
    header_overrides: dict[str, str] | None = None,
    client: httpx.AsyncClient | None = None,
) -> httpx.Response:
    headers, body = _modern_request(method, params, header_overrides=header_overrides)
    if client is not None:
        return await client.post("/mcp", headers=headers, json=body)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8080") as owned:
        return await owned.post("/mcp", headers=headers, json=body)


async def _stdio_tools() -> list[tuple[str, dict[str, Any]]]:
    async with Client(server.mcp) as client:
        listed = await client.list_tools()
    return [(tool.name, dict(tool.input_schema)) for tool in listed.tools]


def test_tools_list_over_http_matches_stdio() -> None:
    async def run() -> tuple[list[tuple[str, dict[str, Any]]], dict[str, Any]]:
        stdio_tools = await _stdio_tools()
        app = server.create_serve_app()
        async with app.router.lifespan_context(app):
            response = await _post(app, "tools/list")
        return stdio_tools, _payload(response) | {"_status": response.status_code}

    stdio_tools, http_body = asyncio.run(run())
    assert http_body.pop("_status") == 200
    result = http_body["result"]
    http_tools = [(tool["name"], tool["inputSchema"]) for tool in result["tools"]]
    assert http_tools == stdio_tools


@respx.mock
def test_read_tool_runs_over_http() -> None:
    respx.get(f"{TEST_BASE_URL}/advertiser/get/advertiser-1").mock(
        return_value=httpx.Response(200, json={"id": "advertiser-1", "name": "Example Law"})
    )

    async def run() -> httpx.Response:
        app = server.create_serve_app()
        async with app.router.lifespan_context(app):
            return await _post(
                app,
                "tools/call",
                {"name": "get_advertiser", "arguments": {"advertiser_id": "advertiser-1"}},
            )

    response = asyncio.run(run())
    assert response.status_code == 200
    result = _payload(response)["result"]
    assert result["isError"] is False
    assert result["structuredContent"] == {"id": "advertiser-1", "name": "Example Law"}


def test_responses_have_no_session_and_requests_share_none() -> None:
    async def run() -> tuple[httpx.Response, httpx.Response]:
        app = server.create_serve_app()
        transport = httpx.ASGITransport(app=app)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8080") as client,
        ):
            first = await _post(app, "tools/list", client=client)
            second = await _post(
                app,
                "tools/list",
                client=client,
                header_overrides={"mcp-session-id": "stale-session"},
            )
        return first, second

    first, second = asyncio.run(run())
    assert first.status_code == 200
    assert second.status_code == 200
    assert "mcp-session-id" not in first.headers
    assert "mcp-session-id" not in second.headers
    assert _payload(first)["result"]["tools"] == _payload(second)["result"]["tools"]


def test_bogus_transport_exits_and_default_is_stdio(monkeypatch: pytest.MonkeyPatch) -> None:
    assert server._requested_transport() == "stdio"
    monkeypatch.setenv("NEXTDOORADS_MCP_TRANSPORT", "bogus")
    with pytest.raises(SystemExit) as exc:
        server.main()
    message = exc.value.code
    assert isinstance(message, str)
    assert "stdio" in message
    assert "streamable-http" in message
    assert "bogus" in message


@pytest.mark.parametrize("transport", ["", "   "])
def test_empty_transport_selects_stdio(transport: str, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    monkeypatch.setenv("NEXTDOORADS_MCP_TRANSPORT", transport)
    monkeypatch.setattr(server.mcp, "run", lambda **kwargs: calls.append(kwargs))
    assert server._requested_transport() == "stdio"
    server.main()
    assert calls == [{"transport": "stdio"}]


def test_allowed_hosts_refuse_other_host_and_bad_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXTDOORADS_MCP_HOST", "0.0.0.0")
    monkeypatch.setenv("NEXTDOORADS_MCP_ALLOWED_HOSTS", "nextdoorads.internal:8080")
    monkeypatch.setenv("NEXTDOORADS_MCP_ALLOWED_ORIGINS", "https://nextdoorads.internal")
    app = server.create_serve_app()

    async def run() -> tuple[httpx.Response, httpx.Response, httpx.Response]:
        async with app.router.lifespan_context(app):
            other_host = await _post(
                app,
                "tools/list",
                header_overrides={"host": "evil.example:8080"},
            )
            bad_origin = await _post(
                app,
                "tools/list",
                header_overrides={
                    "host": "nextdoorads.internal:8080",
                    "origin": "https://evil.example",
                },
            )
            allowed = await _post(
                app,
                "tools/list",
                header_overrides={
                    "host": "nextdoorads.internal:8080",
                    "origin": "https://nextdoorads.internal",
                },
            )
        return other_host, bad_origin, allowed

    other_host, bad_origin, allowed = asyncio.run(run())
    assert other_host.status_code == 421
    assert bad_origin.status_code == 403
    assert allowed.status_code == 200


def test_non_loopback_host_without_allowed_hosts_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXTDOORADS_MCP_HOST", "0.0.0.0")
    with pytest.raises(SystemExit) as exc:
        server.create_serve_app()
    assert "NEXTDOORADS_MCP_ALLOWED_HOSTS" in str(exc.value.code)


@pytest.mark.parametrize("host", ["", "   "])
def test_empty_host_defaults_to_loopback(host: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXTDOORADS_MCP_HOST", host)
    assert server._host() == "127.0.0.1"


def test_mixed_case_localhost_is_non_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXTDOORADS_MCP_HOST", "LOCALHOST")
    assert server._host() == "LOCALHOST"
    with pytest.raises(SystemExit, match="NEXTDOORADS_MCP_ALLOWED_HOSTS"):
        server.create_serve_app()


def test_server_import_survives_missing_distribution() -> None:
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(root), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
    env["PYTHON_KEYRING_BACKEND"] = "keyring.backends.null.Keyring"
    script = """
import importlib.metadata
import mcp.server  # import the SDK before patching so third-party metadata reads stay intact

def missing(distribution):
    raise importlib.metadata.PackageNotFoundError(distribution)

importlib.metadata.version = missing
import nextdoorads_mcp.server
print(nextdoorads_mcp.server.mcp.name)
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        cwd=root,
        env=env,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "nextdoor-ads"


def test_non_integer_port_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PORT", "nope")
    with pytest.raises(SystemExit) as exc:
        server._port()
    assert exc.value.code == "PORT must be an integer, got 'nope'"


def test_get_and_delete_are_method_not_allowed_and_discover_names_version() -> None:
    async def run() -> tuple[httpx.Response, httpx.Response, httpx.Response]:
        app = server.create_serve_app()
        transport = httpx.ASGITransport(app=app)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8080") as client,
        ):
            modern_headers = {
                "host": "127.0.0.1:8080",
                "mcp-protocol-version": PROTOCOL_VERSION,
            }
            get_response = await client.get("/mcp", headers=modern_headers)
            delete_response = await client.delete("/mcp", headers=modern_headers)
            discover = await _post(app, "server/discover", client=client)
        return get_response, delete_response, discover

    get_response, delete_response, discover = asyncio.run(run())
    assert get_response.status_code == 405
    assert delete_response.status_code == 405
    assert discover.status_code == 200
    result = _payload(discover)["result"]
    assert PROTOCOL_VERSION in result["supportedVersions"]
    assert result["_meta"][SERVER_INFO_META_KEY]["version"]


def test_stateless_lifespan_runs_once_per_app_not_per_request() -> None:
    calls = {"enter": 0}
    lowlevel = server.mcp._lowlevel_server
    original = lowlevel.lifespan

    @asynccontextmanager
    async def counting(app: object) -> AsyncIterator[object]:
        calls["enter"] += 1
        async with original(app) as state:
            yield state

    lowlevel.lifespan = counting
    try:

        async def two_requests() -> None:
            app = server.create_serve_app()
            async with app.router.lifespan_context(app):
                first = await _post(app, "tools/list")
                second = await _post(app, "tools/list")
            assert first.status_code == 200
            assert second.status_code == 200

        asyncio.run(two_requests())
    finally:
        lowlevel.lifespan = original
    assert calls["enter"] == 1
