from __future__ import annotations

from nextdoorads_mcp.config import TOKEN_ENV_VAR, ConfigError, Settings


def test_missing_token_names_required_environment_variable(monkeypatch) -> None:
    monkeypatch.delenv(TOKEN_ENV_VAR, raising=False)

    try:
        Settings.from_env()
    except ConfigError as exc:
        assert TOKEN_ENV_VAR in str(exc)
    else:
        raise AssertionError("Settings.from_env() did not reject a missing token")


def test_startup_without_credentials_runs_stdio(monkeypatch, capsys) -> None:
    from nextdoorads_mcp import server
    from nextdoorads_mcp.runtime import MCPServer

    seen = []
    monkeypatch.setattr(MCPServer, "run", lambda self, **kwargs: seen.append(kwargs))
    server.cli()
    assert seen == [{"transport": "stdio"}]
    assert "Traceback" not in capsys.readouterr().err
