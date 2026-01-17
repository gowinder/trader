import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_httpx():
    """Mock httpx client"""
    with patch("httpx.AsyncClient") as mock:
        client_instance = AsyncMock()
        mock.return_value = client_instance
        yield client_instance


# ============ OpenRouter Provider Tests ============


@pytest.mark.asyncio
async def test_openrouter_chat_success(mock_httpx):
    """Test successful OpenRouter chat"""
    from ai_trader.ai.providers.openrouter import OpenRouterProvider

    provider = OpenRouterProvider(
        api_key="test_key",
        model="deepseek/deepseek-chat",
        fallback_model="minimax/minimax-01",
    )

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": [{"message": {"content": "Hello"}}]}
    provider._client.post.return_value = mock_response

    response = await provider.chat(messages=[{"role": "user", "content": "Hi"}])
    assert response["content"] == "Hello"


@pytest.mark.asyncio
async def test_openrouter_chat_with_schema(mock_httpx):
    """Test OpenRouter chat with schema"""
    from ai_trader.ai.providers.openrouter import OpenRouterProvider

    provider = OpenRouterProvider(
        api_key="test_key",
        model="deepseek/deepseek-chat",
        fallback_model="minimax/minimax-01",
    )

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": '{"result": "ok"}'}}]
    }
    provider._client.post.return_value = mock_response

    schema = {"type": "object"}
    response = await provider.chat(
        messages=[{"role": "user", "content": "Hi"}], schema=schema
    )
    assert response["result"] == "ok"


@pytest.mark.asyncio
async def test_openrouter_fallback_mechanism(mock_httpx):
    """Test OpenRouter fallback when primary fails"""
    from ai_trader.ai.providers.openrouter import OpenRouterProvider

    provider = OpenRouterProvider(
        api_key="test_key",
        model="deepseek/deepseek-chat",
        fallback_model="minimax/minimax-01",
    )

    mock_response_success = MagicMock()
    mock_response_success.status_code = 200
    mock_response_success.json.return_value = {
        "choices": [{"message": {"content": "Fallback"}}]
    }

    provider._client.post.side_effect = [Exception("Fail"), mock_response_success]

    response = await provider.chat(messages=[{"role": "user", "content": "Hi"}])
    assert response["content"] == "Fallback"


@pytest.mark.asyncio
async def test_openrouter_all_models_fail(mock_httpx):
    """Test when all OpenRouter models fail"""
    from ai_trader.ai.providers.openrouter import OpenRouterProvider

    provider = OpenRouterProvider(
        api_key="test_key",
        model="deepseek/deepseek-chat",
        fallback_model="minimax/minimax-01",
    )

    provider._client.post.side_effect = [
        Exception("Primary Fail"),
        Exception("Fallback Fail"),
    ]

    with pytest.raises(RuntimeError) as excinfo:
        await provider.chat(messages=[{"role": "user", "content": "Hi"}])

    assert "All LLM models failed" in str(excinfo.value)


# ============ GLM Provider Tests (Anthropic Protocol) ============


@pytest.mark.asyncio
async def test_glm_chat_success(mock_httpx):
    """Test successful GLM chat (Anthropic protocol)"""
    from ai_trader.ai.providers.glm import GLMProvider

    provider = GLMProvider(
        api_key="test_glm_key",
        model="glm-4",
    )

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "content": [{"type": "text", "text": "Hello from GLM"}]
    }
    provider._client.post.return_value = mock_response

    response = await provider.chat(messages=[{"role": "user", "content": "Hi"}])
    assert response["content"] == "Hello from GLM"


@pytest.mark.asyncio
async def test_glm_chat_with_system_prompt(mock_httpx):
    """Test GLM chat with system prompt (Anthropic protocol)"""
    from ai_trader.ai.providers.glm import GLMProvider

    provider = GLMProvider(
        api_key="test_glm_key",
        model="glm-4",
    )

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "content": [{"type": "text", "text": '{"result": "ok"}'}]
    }
    provider._client.post.return_value = mock_response

    schema = {"type": "object"}
    response = await provider.chat(
        messages=[
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "Hi"},
        ],
        schema=schema,
    )
    assert response["result"] == "ok"


@pytest.mark.asyncio
async def test_glm_all_models_fail(mock_httpx):
    """Test when GLM model fails (no fallback)"""
    from ai_trader.ai.providers.glm import GLMProvider

    provider = GLMProvider(
        api_key="test_glm_key",
        model="glm-4",
    )

    provider._client.post.side_effect = Exception("GLM API Error")

    with pytest.raises(Exception) as excinfo:
        await provider.chat(messages=[{"role": "user", "content": "Hi"}])

    assert "GLM API Error" in str(excinfo.value)


@pytest.mark.asyncio
async def test_glm_with_fallback_all_fail(mock_httpx):
    """Test when GLM model and fallback both fail"""
    from ai_trader.ai.providers.glm import GLMProvider

    provider = GLMProvider(
        api_key="test_glm_key",
        model="glm-4",
        fallback_model="glm-4-plus",
    )

    provider._client.post.side_effect = [
        Exception("Primary Fail"),
        Exception("Fallback Fail"),
    ]

    with pytest.raises(RuntimeError) as excinfo:
        await provider.chat(messages=[{"role": "user", "content": "Hi"}])

    assert "All LLM models failed" in str(excinfo.value)


# ============ Provider Name Tests ============


def test_provider_names():
    """Test provider name property"""
    from ai_trader.ai.providers.openrouter import OpenRouterProvider
    from ai_trader.ai.providers.deepseek import DeepSeekProvider
    from ai_trader.ai.providers.glm import GLMProvider
    from ai_trader.ai.providers.gemini import GeminiProvider

    assert OpenRouterProvider(api_key="k", model="m").provider_name == "openrouter"
    assert DeepSeekProvider(api_key="k", model="m").provider_name == "deepseek"
    assert GLMProvider(api_key="k", model="m").provider_name == "glm"
    assert GeminiProvider(api_key="k", model="m").provider_name == "gemini"
