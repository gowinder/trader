import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from ai_trader.exchange.weex_client import WeexClient


@pytest.fixture
def mock_httpx_client():
    with patch("httpx.AsyncClient") as mock:
        client_instance = AsyncMock()
        mock.return_value = client_instance
        yield client_instance


@pytest.mark.asyncio
async def test_weex_signature(mock_httpx_client):
    """Test signature generation"""
    # Patch config to ensure known values
    with patch("ai_trader.exchange.weex_client.config") as mock_config:
        mock_config.weex_api_key = "test_key"
        mock_config.weex_api_secret = "test_secret"
        mock_config.weex_passphrase = "test_pass"
        mock_config.weex_api_url = "https://api.test"
        mock_config.proxy_url = ""  # Add proxy_url mock

        client = WeexClient()
        # Mock time to fix timestamp
        with patch("time.time", return_value=1234567890.0):
            headers = client._headers("GET", "/test", "")

            assert headers["ACCESS-KEY"] == "test_key"
            assert headers["ACCESS-PASSPHRASE"] == "test_pass"
            assert headers["ACCESS-TIMESTAMP"] == "1234567890000"
            assert "ACCESS-SIGN" in headers


@pytest.mark.asyncio
async def test_get_ticker(mock_httpx_client):
    """Test get_ticker"""
    client = WeexClient()
    mock_response = MagicMock()
    mock_response.json.return_value = {"code": "00000", "data": {"last": "1000"}}
    client._client.get.return_value = mock_response

    result = await client.get_ticker("BTCUSDT")
    assert result["data"]["last"] == "1000"

    # Verify call args
    call_args = client._client.get.call_args
    assert "/capi/v2/market/ticker" in call_args[0][0]
    assert call_args[1]["params"]["symbol"] == "BTCUSDT"


@pytest.mark.asyncio
async def test_create_order(mock_httpx_client):
    """Test create_order"""
    client = WeexClient()
    mock_response = MagicMock()
    mock_response.json.return_value = {"code": "00000", "data": {"orderId": "123"}}
    client._client.post.return_value = mock_response

    result = await client.create_order(
        symbol="BTCUSDT", side="open_long", order_type="market", size=1.0
    )

    assert result["data"]["orderId"] == "123"
