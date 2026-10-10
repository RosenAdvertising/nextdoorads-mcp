from __future__ import annotations

import pytest

from nextdoorads_mcp.client import NextdoorAdsClient
from nextdoorads_mcp.config import Settings
from nextdoorads_mcp.server import configure_client

TEST_BASE_URL = "https://ads.nextdoor.test/v2/api"
TEST_TOKEN = "offline-test-token"


@pytest.fixture
def settings() -> Settings:
    return Settings(access_token=TEST_TOKEN, base_url=TEST_BASE_URL)


@pytest.fixture(autouse=True)
def configured_tool_client(settings: Settings) -> None:
    configure_client(
        NextdoorAdsClient(
            settings,
            max_retries=0,
            backoff_base_seconds=0,
        )
    )
