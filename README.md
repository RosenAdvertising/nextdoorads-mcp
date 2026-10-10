# Nextdoor Ads MCP

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/RosenAdvertising/nextdoorads-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/RosenAdvertising/nextdoorads-mcp/actions/workflows/ci.yml)

An MCP server that lets AI assistants inspect Nextdoor Ads Manager and perform a small set of
confirmed actions. It communicates with the official Python MCP SDK over stdio. The server exposes
14 tools for advertiser context, campaigns, ad groups, creatives, reporting, and postal targeting.

## Features

- Read advertiser context, campaigns, ad groups, creatives, and performance metrics.
- Resolve postal targeting codes to Nextdoor Ads targeting IDs.
- Create campaign containers, ad groups, and ad-hoc performance reports with explicit confirmation.
- Paginate list results, throttle requests, and retry rate-limit and server errors.
- Preserve successful non-JSON responses, including CSV reports, as structured content.
- Mark tools experimental when endpoint response or parameter details need further verification.

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- An access token for Nextdoor Ads API access
- An MCP-compatible client

Nextdoor Ads API access requires approval. Generate an access token in [Nextdoor Ads Manager](https://ads.nextdoor.com/v2/manage/api).

## Install from source

Clone this repository, then install the locked dependencies:

```bash
uv sync --locked
```

## Configuration

Set `NEXTDOOR_ADS_ACCESS_TOKEN` to the token generated in Nextdoor Ads Manager. The server sends it as a Bearer token and does not log it. Initialization and tool listing work without credentials; tool calls return a clear configuration error until the variable is set.

The server reads configuration from its process environment and does not load dotenv files. `.env.example` documents the token variable; provide its value through your shell, process manager, or MCP client. Nextdoor does not document an Ads API sandbox, refresh flow, token lifetime, or rotation procedure.

## MCP client configuration

A client can start the server from the cloned repository with `uv` and a portable working directory path:

```json
{
  "mcpServers": {
    "nextdoor-ads": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/nextdoorads-mcp", "nextdoorads-mcp"],
      "env": {
        "NEXTDOOR_ADS_ACCESS_TOKEN": "replace_with_your_generated_access_token"
      }
    }
  }
}
```

Replace `/path/to/nextdoorads-mcp` with the location of your clone and provide the token through your MCP client's environment configuration.

## HTTP mode

Stdio stays the default. Set `NEXTDOORADS_MCP_TRANSPORT=streamable-http` to serve stateless Streamable HTTP at `/mcp`. The access token still comes from `NEXTDOOR_ADS_ACCESS_TOKEN` in the process environment, never from the request.

> **Security: this endpoint has no authentication and no TLS.** Anyone who can reach the port can run every tool, including write and delete tools, with this server's vendor credentials. Keep the default loopback bind (`127.0.0.1`), or put the server behind an authenticating TLS proxy on a private network. `NEXTDOORADS_MCP_ALLOWED_HOSTS` and `NEXTDOORADS_MCP_ALLOWED_ORIGINS` protect against browser DNS rebinding, not against direct callers. A proxy in front of it needs connection and idle timeouts: a legacy-style `GET /mcp` with `Accept: text/event-stream` holds a stream open until the client disconnects.

| Variable | Default | Purpose |
| --- | --- | --- |
| `NEXTDOORADS_MCP_TRANSPORT` | `stdio` | `stdio` or `streamable-http`. |
| `NEXTDOORADS_MCP_HOST` | `127.0.0.1` | Bind address. A non-loopback address requires `NEXTDOORADS_MCP_ALLOWED_HOSTS`. |
| `PORT` | `8080` | Bind port. A non-integer value exits. |
| `NEXTDOORADS_MCP_ALLOWED_HOSTS` | unset | Comma-separated `Host` values. Required when the bind address is not loopback. |
| `NEXTDOORADS_MCP_ALLOWED_ORIGINS` | unset | Optional comma-separated `Origin` values checked with the allowed hosts. |
| `NEXTDOOR_ADS_ACCESS_TOKEN` | unset | Bearer token for the Nextdoor Ads API. Tool calls need it; tool listing does not. |

```bash
NEXTDOORADS_MCP_TRANSPORT=streamable-http \
NEXTDOOR_ADS_ACCESS_TOKEN=replace_with_your_generated_access_token \
uv run --directory /path/to/nextdoorads-mcp nextdoorads-mcp
```

The endpoint is `http://127.0.0.1:8080/mcp`.

## Tools

The server registers 14 tools:

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

## API behavior and limitations

- Some documented `GET` requests include a JSON body. Proxies may reject GET bodies; verify this behavior with your network and API access.
- List calls accept a total `limit` and optional cursor. Each API page is capped at 500 records.
- A process-local sliding-window limiter caps traffic at 100 requests per minute. HTTP 429 and 5xx responses are retried with exponential backoff and jitter; numeric `Retry-After` takes precedence.
- Money values retain Nextdoor's string representation. Stats use inclusive `YYYY-MM-DD` ranges; ad-group schedules use zoned ISO-8601 strings.
- Successful non-JSON responses are returned as structured JSON containing `content` and `content_type`.
- Vendor HTTP error details remain in typed client exceptions. MCP errors and logging use sanitized messages; vendor error bodies are not exposed. The general API error envelope and several status-code behaviors are not documented.
- Creating an ad-hoc report emails its recipients. All write tools require an explicit `confirm=true` argument.
- No webhooks are documented or implemented.

## Development

```bash
uv sync --locked
uv run --locked pytest -q
uv run --locked ruff check .
```

Tests use mocked HTTP responses and do not contact Nextdoor.

## License

MIT. See [LICENSE](LICENSE).

## Local setup and verification

The server starts and answers MCP initialization and tool listing without credentials.
Tools report a configuration error until the required environment is provided.
Run `nextdoorads-mcp-setup` for environment-variable instructions, then restart your MCP
launcher with those variables exported. Run `nextdoorads-mcp-verify` to validate local
configuration (exit 2 if missing or invalid). This command does not contact the
vendor or prove authentication. Neither command saves or prints secret values.
