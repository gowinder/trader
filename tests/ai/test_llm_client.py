import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from ai_trader.ai.llm_client import LLMClient


@pytest.fixture
def mock_httpx_client():
    with patch("httpx.AsyncClient") as mock:
        client_instance = AsyncMock()
        mock.return_value = client_instance
        yield client_instance


@pytest.mark.asyncio
async def test_chat_success(mock_httpx_client):
    """Test successful chat"""
    client = LLMClient()
    mock_response = MagicMock()  # Sync mock for response object
    mock_response.status_code = 200
    # Mock OpenRouter response format
    mock_response.json.return_value = {"choices": [{"message": {"content": "Hello"}}]}
    client._client.post.return_value = mock_response

    response = await client.chat(messages=[{"role": "user", "content": "Hi"}])
    assert response["content"] == "Hello"


@pytest.mark.asyncio
async def test_chat_with_schema(mock_httpx_client):
    """Test chat with schema"""
    client = LLMClient()
    mock_response = MagicMock()
    mock_response.status_code = 200
    # Mock JSON structure response
    mock_response.json.return_value = {
        "choices": [{"message": {"content": '{"result": "ok"}'}}]
    }
    client._client.post.return_value = mock_response

    schema = {"type": "object"}
    response = await client.chat(
        messages=[{"role": "user", "content": "Hi"}], schema=schema
    )
    assert response["result"] == "ok"


@pytest.mark.asyncio
async def test_fallback_mechanism(mock_httpx_client):
    """Test fallback when primary fails"""
    client = LLMClient()

    mock_response_success = MagicMock()
    mock_response_success.status_code = 200
    mock_response_success.json.return_value = {
        "choices": [{"message": {"content": "Fallback"}}]
    }

    client._client.post.side_effect = [Exception("Fail"), mock_response_success]

    response = await client.chat(messages=[{"role": "user", "content": "Hi"}])
    assert response["content"] == "Fallback"


@pytest.mark.asyncio
async def test_all_models_fail(mock_httpx_client):
    """Test when all models fail"""
    client = LLMClient()
    # Both calls fail
    client._client.post.side_effect = [
        Exception("Primary Fail"),
        Exception("Fallback Fail"),
    ]

    with pytest.raises(RuntimeError) as excinfo:
        await client.chat(messages=[{"role": "user", "content": "Hi"}])

    assert "All LLM models failed" in str(excinfo.value)
