"""Unit tests for exchange factory function"""

import pytest
from unittest.mock import patch, Mock
from ai_trader.exchange import create_exchange_client
from ai_trader.exchange.weex_client import WeexClient
from ai_trader.exchange.ccxt_adapter import CCXTAdapter


class TestCreateExchangeClient:
    """Test create_exchange_client factory function"""

    @patch("ai_trader.exchange.config")
    def test_create_weex_native_client(self, mock_config):
        """Test creating native WEEX client when use_ccxt=False"""
        mock_config.trading_mode = "live"
        mock_config.exchange_type = "weex"
        mock_config.use_ccxt = False
        mock_config.proxy_url = ""
        mock_config.get_exchange_credentials.return_value = {
            "api_key": "test_key",
            "api_secret": "test_secret",
            "passphrase": "test_passphrase",
        }

        client = create_exchange_client()

        assert isinstance(client, WeexClient)

    @patch("ai_trader.exchange.CCXTAdapter.from_config")
    @patch("ai_trader.exchange.config")
    def test_create_ccxt_client_for_other_exchange(self, mock_config, mock_from_config):
        """Test creating CCXT client for non-WEEX exchanges"""
        mock_config.trading_mode = "live"
        mock_config.exchange_type = "binance"
        mock_config.proxy_url = ""
        mock_config.get_exchange_credentials.return_value = {
            "api_key": "test_key",
            "api_secret": "test_secret",
        }
        mock_from_config.return_value = Mock(spec=CCXTAdapter)

        client = create_exchange_client()

        mock_from_config.assert_called_once_with(
            exchange_id="binance",
            api_key="test_key",
            api_secret="test_secret",
            passphrase=None,
            testnet=False,
            proxy=None,
        )

    @patch("ai_trader.exchange.CCXTAdapter.from_config")
    @patch("ai_trader.exchange.config")
    def test_testnet_mode_validation(self, mock_config, mock_from_config):
        """Test testnet mode only allows supported exchanges"""
        mock_config.trading_mode = "testnet"
        mock_config.testnet_exchange = "unsupported_exchange"
        mock_config.testnet_api_key = "test_key"
        mock_config.testnet_api_secret = "test_secret"
        mock_config.proxy_url = ""

        with pytest.raises(ValueError, match="Testnet mode does not support"):
            create_exchange_client()

    @patch("ai_trader.exchange.BinanceAdapter")
    @patch("ai_trader.exchange.config")
    def test_testnet_mode_binance(self, mock_config, mock_binance_adapter):
        """Test testnet mode with Binance uses BinanceAdapter"""
        from ai_trader.exchange.binance_adapter import BinanceAdapter

        mock_config.trading_mode = "testnet"
        mock_config.testnet_exchange = "binance"
        mock_config.testnet_api_key = "test_key"
        mock_config.testnet_api_secret = "test_secret"
        mock_config.proxy_url = ""
        mock_binance_adapter.return_value = Mock(spec=BinanceAdapter)

        client = create_exchange_client()

        # Verify BinanceAdapter was called with correct parameters
        mock_binance_adapter.assert_called_once_with(
            api_key="test_key",
            api_secret="test_secret",
            testnet=True,
            proxy=None,
        )

    @patch("ai_trader.exchange.WeexClient")
    @patch("ai_trader.exchange.CCXTAdapter.from_config")
    @patch("ai_trader.exchange.config")
    def test_weex_ccxt_fallback(self, mock_config, mock_from_config, mock_weex_client):
        """Test WEEX falls back to native implementation if CCXT fails"""
        mock_config.trading_mode = "live"
        mock_config.exchange_type = "weex"
        mock_config.use_ccxt = True
        mock_config.proxy_url = ""
        mock_config.get_exchange_credentials.return_value = {
            "api_key": "test_key",
            "api_secret": "test_secret",
            "passphrase": "test_passphrase",
        }

        # Simulate CCXT not supporting WEEX
        mock_from_config.side_effect = ValueError("CCXT does not support exchange: weex")
        mock_weex_client.return_value = Mock(spec=WeexClient)

        client = create_exchange_client()

        # Should fallback to native WeexClient
        mock_weex_client.assert_called_once()

    @patch("ai_trader.exchange.config")
    def test_missing_credentials(self, mock_config):
        """Test error when exchange credentials are not configured"""
        mock_config.trading_mode = "live"
        mock_config.exchange_type = "binance"
        mock_config.get_exchange_credentials.side_effect = ValueError("未配置binance的API凭证")

        with pytest.raises(ValueError, match="未配置binance的API凭证"):
            create_exchange_client()
