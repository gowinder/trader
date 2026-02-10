import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_advisory_llm_client_chat():
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '{"urgency":"high","suggestions":[],"market_summary":"test"}'}}]
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        from ai_trader.advisory.llm_client import AdvisoryLLMClient

        client = AdvisoryLLMClient(
            provider="openrouter",
            api_key="test_key",
            model="deepseek/deepseek-chat",
            base_url="https://openrouter.ai/api/v1",
        )
        result = await client.chat(
            messages=[{"role": "user", "content": "test"}],
            schema={"type": "object"},
        )
        assert result["urgency"] == "high"
        await client.close()
