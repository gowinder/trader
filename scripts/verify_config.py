"""验证所有 API 配置是否正确"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv

load_dotenv()


async def verify_all():
    print("=" * 60)
    print("API 配置验证")
    print("=" * 60)
    print()

    results = {"total": 0, "passed": 0, "failed": 0}

    # 1. LLM
    print("1. LLM API:")
    provider = os.getenv("LLM_PROVIDER")
    api_key = os.getenv("LLM_API_KEY", "")
    model = os.getenv("LLM_MODEL", "")

    print(f"   Provider: {provider}")
    print(f"   Model: {model}")
    print(f"   API Key: {api_key[:10] if api_key else '未配置'}... (长度: {len(api_key)})")

    results["total"] += 1
    if api_key and len(api_key) > 10:
        print("   ✓ LLM 配置存在")
        results["passed"] += 1
    else:
        print("   ✗ LLM API Key 未配置")
        results["failed"] += 1

    print()

    # 2. Binance
    print("2. Binance Testnet:")
    mode = os.getenv("TRADING_MODE", "")
    exchange = os.getenv("TESTNET_EXCHANGE", "")
    testnet_key = os.getenv("TESTNET_API_KEY", "")

    print(f"   交易模式: {mode}")
    print(f"   交易所: {exchange}")
    print(f"   API Key: {testnet_key[:10] if testnet_key else '未配置'}... (长度: {len(testnet_key)})")

    results["total"] += 1
    try:
        from ai_trader.exchange import create_exchange_client

        client = create_exchange_client()
        ticker = await client.get_ticker("BTC/USDT")
        print(f"   ✓ 连接成功，BTC/USDT: ${ticker.last_price:,.2f}")
        results["passed"] += 1
        await client.close()
    except Exception as e:
        print(f"   ✗ 连接失败: {e}")
        results["failed"] += 1

    print()

    # 3. 情绪分析
    print("3. 情绪分析 API:")
    enabled = os.getenv("ENABLE_SENTIMENT_ANALYSIS", "false").lower() == "true"
    cp_key = os.getenv("CRYPTOPANIC_API_KEY", "")
    na_key = os.getenv("NEWSAPI_KEY", "")

    print(f"   启用状态: {'✅ 已启用' if enabled else '❌ 未启用'}")
    print(f"   CryptoPanic Key: {cp_key[:10] if cp_key else '未配置'}... (长度: {len(cp_key)})")
    print(f"   NewsAPI Key: {na_key[:10] if na_key else '未配置'}... (长度: {len(na_key)})")

    if not enabled:
        print("   ⚠️  情绪分析未启用（可选功能）")
    else:
        # Test CryptoPanic
        results["total"] += 1
        if cp_key:
            try:
                from ai_trader.sentiment.data_sources import CryptoPanicSource

                source = CryptoPanicSource(cp_key)
                news = await source.fetch_news("BTC", limit=5, hours=24)
                print(f"   ✓ CryptoPanic: 获取到 {len(news)} 条新闻")
                results["passed"] += 1
            except Exception as e:
                print(f"   ✗ CryptoPanic 失败: {e}")
                results["failed"] += 1
        else:
            print("   ✗ CryptoPanic API Key 未配置")
            results["failed"] += 1

        # Test NewsAPI
        results["total"] += 1
        if na_key:
            try:
                from ai_trader.sentiment.data_sources import NewsAPISource

                source = NewsAPISource(na_key)
                news = await source.fetch_news("BTC", limit=5, hours=24)
                print(f"   ✓ NewsAPI: 获取到 {len(news)} 条新闻")
                results["passed"] += 1
            except Exception as e:
                print(f"   ✗ NewsAPI 失败: {e}")
                results["failed"] += 1
        else:
            print("   ✗ NewsAPI API Key 未配置")
            results["failed"] += 1

    print()
    print("=" * 60)
    print("验证结果")
    print("=" * 60)
    print(f"总测试数: {results['total']}")
    print(f"✓ 通过: {results['passed']}")
    print(f"✗ 失败: {results['failed']}")
    print()

    if results["failed"] == 0:
        print("🎉 所有配置验证通过！")
    elif results["passed"] >= 2:
        print("⚠️  部分配置缺失，但核心功能可用")
        print()
        print("建议补充:")
        if not enabled or not cp_key or not na_key:
            print("  - 情绪分析 API（可选）")
            print("    1. CryptoPanic: https://cryptopanic.com/developers/api/")
            print("    2. NewsAPI: https://newsapi.org/")
    else:
        print("❌ 关键配置缺失，请检查 .env 文件")

    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(verify_all())
