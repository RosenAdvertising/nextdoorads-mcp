# Nextdoor Ads MCP server

[![CI](https://github.com/RosenAdvertising/nextdoorads-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/RosenAdvertising/nextdoorads-mcp/actions/workflows/ci.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![MCP 2026-07-28](https://img.shields.io/badge/MCP-2026--07--28-7C3AED.svg)](https://modelcontextprotocol.io)

Connect Claude and other MCP clients to Nextdoor Ads to inspect campaigns, ad groups, creatives and performance, resolve postal targeting, and create campaigns, ad groups and reports.

Nextdoor Ads MCP server is a [Model Context Protocol](https://modelcontextprotocol.io) server for [Nextdoor Ads](https://ads.nextdoor.com/), the advertising platform on the Nextdoor neighborhood network. It registers 14 tools that read and write, covering advertiser context, campaigns, ad groups, creatives, reporting and postal targeting. It runs over stdio by default, for desktop clients such as Claude Desktop, and offers an opt-in stateless Streamable HTTP mode that implements MCP specification 2026-07-28. Nextdoor Ads credentials stay on the machine that runs the server: the access token comes from an environment variable, never from tool arguments or requests. Every tool that writes requires `confirm=true`.

## Features

- Read advertiser context, campaigns, ad groups, creatives, and performance metrics.
- Resolve postal targeting codes to Nextdoor Ads targeting IDs.
- Create campaign containers, ad groups, and ad-hoc performance reports with explicit confirmation.
- Paginate list results, throttle requests, and retry rate-limit and server errors.
- Preserve successful non-JSON responses, including CSV reports, as structured content.
- Mark tools experimental when endpoint response or parameter details need further verification.

## Tools

The server registers 14 tools. Every tool that writes requires `confirm=true`.

Tools whose names start with `experimental_` call Nextdoor Ads endpoints whose request or response schema is not fully published. They send only the fields you supply, and `experimental_create_ad_group` requires `confirm=true` before writing.

| Tool | Access | Description |
| --- | --- | --- |
| `get_authenticated_context` | Read | Check the token and return user, profile, advertiser access, and roles. |
| `list_campaigns` | Read | List campaigns for an advertiser with cursor pagination. |
| `get_campaign` | Read | Get one campaign's configuration. |
| `experimental_get_campaign_stats` | Read, experimental | Get campaign performance; response fields need further verification. |
| `list_ad_groups` | Read | List budget, schedule, placement, and targeting settings in a campaign. |
| `get_ad_group_stats` | Read | Get ad-group spend, impressions, clicks, conversions, CTR, CPC, and CPM. |
| `get_ad_stats` | Read | Get individual-ad performance metrics. |
| `list_creatives` | Read | List creative assets and review/status metadata. |
| `match_postal_targeting` | Read | Resolve service-area ZIP codes to targeting IDs. |
| `experimental_get_report` | Read, experimental | Retrieve a report; JSON versus CSV response details need verification. |
| `get_advertiser` | Read | Get advertiser identity, category, billing, and balance details. |
| `create_report` | Write | Generate and email an ad-hoc performance report; requires `confirm=true`. |
| `create_campaign` | Write | Create a campaign container; requires `confirm=true`. |
| `experimental_create_ad_group` | Write, experimental | Create an ad group; requires `confirm=true`. |

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- An access token for Nextdoor Ads API access
- An MCP client such as Claude Desktop

Nextdoor Ads API access requires approval. Generate an access token in [Nextdoor Ads Manager](https://ads.nextdoor.com/v2/manage/api).

## Installation

Install [uv](https://docs.astral.sh/uv/), then clone the repository and install its locked dependencies:

```bash
git clone https://github.com/RosenAdvertising/nextdoorads-mcp.git
cd nextdoorads-mcp
uv sync --locked
```

## Configuration

The server reads its configuration from its process environment and does not load dotenv files. `.env.example` lists the variable; provide its value through your shell, process manager or MCP client. The server sends the token as a Bearer token and does not log it.

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `NEXTDOOR_ADS_ACCESS_TOKEN` | Yes | none | Access token for the Nextdoor Ads API, generated in [Nextdoor Ads Manager](https://ads.nextdoor.com/v2/manage/api). Tool calls need it; initialization and tool listing do not. |

Initialization and tool listing work without credentials. Tool calls return a configuration error until the variable is set. Nextdoor does not document an Ads API sandbox, refresh flow, token lifetime or rotation procedure.

Two commands help with local setup:

```bash
uv run nextdoorads-mcp-setup
uv run nextdoorads-mcp-verify
```

`nextdoorads-mcp-setup` prints instructions for the environment variable: export it in the environment your MCP client uses, then restart the client. `nextdoorads-mcp-verify` checks that the token is set and exits with code 2 if it is missing. It does not contact Nextdoor or prove authentication. Neither command saves or prints secret values.

## Usage with Claude Desktop

Add the server to Claude Desktop's configuration file (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS, `%APPDATA%\Claude\claude_desktop_config.json` on Windows):

```json
{
  "mcpServers": {
    "nextdoor-ads": {
      "command": "uv",
      "args": ["run", "--locked", "--directory", "/absolute/path/to/nextdoorads-mcp", "nextdoorads-mcp"],
      "env": {
        "NEXTDOOR_ADS_ACCESS_TOKEN": "replace-with-your-access-token"
      }
    }
  }
}
```

Replace `/absolute/path/to/nextdoorads-mcp` with the path of your clone, then restart Claude Desktop. Keep real credentials in your client's protected environment or secret store. Any other stdio MCP client uses the same command and arguments.

## HTTP mode

Stdio is the default. Set `NEXTDOORADS_MCP_TRANSPORT=streamable-http` to serve the stateless Streamable HTTP transport from MCP specification 2026-07-28 at `/mcp`. Each request stands alone: no initialization handshake and no `Mcp-Session-Id`. Clients on earlier protocol versions are served on the same endpoint.

> **Security: this endpoint has no authentication and no TLS.** Anyone who can reach the port can run every tool, including write tools, with this server's vendor credentials. Keep the default loopback bind (`127.0.0.1`), or put the server behind an authenticating TLS proxy on a private network. `NEXTDOORADS_MCP_ALLOWED_HOSTS` and `NEXTDOORADS_MCP_ALLOWED_ORIGINS` protect against browser DNS rebinding, not against direct callers. A proxy in front of it needs connection and idle timeouts: a legacy-style `GET /mcp` with `Accept: text/event-stream` holds a stream open until the client disconnects.

| Variable | Default | Purpose |
| --- | --- | --- |
| `NEXTDOORADS_MCP_TRANSPORT` | `stdio` | `stdio` or `streamable-http`. An empty value selects `stdio`; any other value exits. |
| `NEXTDOORADS_MCP_HOST` | `127.0.0.1` | Bind address. `127.0.0.1`, `localhost` and `::1` use the SDK's built-in Host and Origin checks; any other value requires `NEXTDOORADS_MCP_ALLOWED_HOSTS`. |
| `PORT` | `8080` | Port; must be an integer. |
| `NEXTDOORADS_MCP_ALLOWED_HOSTS` | unset | Comma-separated `Host` header values accepted on a non-loopback bind, such as `mcp.example.com:8080` or `mcp.example.com:*`. The server exits if it is unset on a non-loopback bind. |
| `NEXTDOORADS_MCP_ALLOWED_ORIGINS` | unset | Comma-separated `Origin` values accepted on a non-loopback bind, such as `https://client.example.com`. Requests without an `Origin` header are accepted. |

Nextdoor Ads credentials come from the same configuration as stdio (see [Configuration](#configuration)), never from the request.

```bash
NEXTDOORADS_MCP_TRANSPORT=streamable-http PORT=8080 uv run --locked nextdoorads-mcp
```

Point the MCP client at `http://127.0.0.1:8080/mcp`.

## Error handling

A failed tool call returns an MCP error result (`isError`) with a fixed message. Nextdoor's own error text and response bodies are never returned or logged.

- Missing token: a configuration message that names `NEXTDOOR_ADS_ACCESS_TOKEN` and `nextdoorads-mcp-setup`.
- HTTP 401, 403, 404 and 429: a short message that says what to check (credentials, account permissions, the record ID, or waiting before a retry).
- HTTP 5xx: a "Service unavailable" message that asks you to check whether a write completed before retrying.
- Any other HTTP status: "Request rejected or response invalid. Check inputs and API configuration."
- Connection failures and timeouts: "Connection failed; the operation outcome may be unknown."
- Invalid tool input: "Invalid tool input or response."
- Any other failure, including a list response without the expected fields: "The operation could not be completed."
- A write called without `confirm=true`: "This write was not sent because confirm must be true."

HTTP 429 and 5xx responses are retried up to 3 times, so a request is attempted at most 4 times. The delay is random, up to 0.5 seconds before the first retry, then 1 and 2 seconds; a numeric `Retry-After` header sets the delay instead. Retries apply to writes as well as reads, so after a rate-limit or service error check whether a write completed before repeating it. Connection failures and timeouts are not retried. The HTTP timeout is 30 seconds, and a process-local limiter holds traffic to 100 requests per minute.

The server exits with status 1 and a message that names the setting when `NEXTDOORADS_MCP_TRANSPORT` is unsupported, `PORT` is not an integer, or `NEXTDOORADS_MCP_HOST` is not a loopback address and `NEXTDOORADS_MCP_ALLOWED_HOSTS` is unset.

## API behavior and limitations

- Some documented `GET` requests include a JSON body. Proxies may reject GET bodies; verify this behavior with your network and API access.
- List calls accept a total `limit` and optional cursor. Each API page is capped at 500 records.
- Money values retain Nextdoor's string representation. Stats use inclusive `YYYY-MM-DD` ranges; ad-group schedules use zoned ISO-8601 strings.
- Successful non-JSON responses are returned as structured JSON containing `content` and `content_type`.
- Nextdoor does not document the general API error envelope or several status-code behaviors.
- Creating an ad-hoc report emails its recipients. All write tools require an explicit `confirm=true` argument.
- No webhooks are documented or implemented.

## Testing

The test suite runs offline and needs no Nextdoor Ads account: every Nextdoor Ads API call is intercepted at the HTTP layer with `respx`. It covers each tool's requests and responses, write confirmation, identifier validation, pagination, retries, error handling that withholds vendor text, credential loading, the stdio server, and the Streamable HTTP transport including the 2026-07-28 wire format, Host and Origin checks and stateless requests.

```bash
uv sync --locked
uv run --locked pytest -q
uv run --locked ruff check .
```

CI runs the suite on every push and pull request to `main`.

## License

MIT. See [LICENSE](LICENSE).
