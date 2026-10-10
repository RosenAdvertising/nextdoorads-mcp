"""Environment-only configuration for the Nextdoor Ads MCP server."""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_BASE_URL = "https://ads.nextdoor.com/v2/api"
TOKEN_ENV_VAR = "NEXTDOOR_ADS_ACCESS_TOKEN"


class ConfigError(ValueError):
    """Raised when required server configuration is unavailable."""


@dataclass(frozen=True, slots=True)
class Settings:
    """Validated runtime settings loaded from environment variables."""

    access_token: str
    base_url: str = DEFAULT_BASE_URL

    @classmethod
    def from_env(cls) -> Settings:
        """Load settings from environment variables."""
        access_token = os.environ.get(TOKEN_ENV_VAR, "").strip()
        if not access_token:
            raise ConfigError(
                f"Missing required environment variable {TOKEN_ENV_VAR}. "
                "Set it to the token generated in Nextdoor Ads Manager."
            )
        return cls(access_token=access_token)
