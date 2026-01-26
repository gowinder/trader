# Testnet Environment Research

> Research Date: 2026-01-26
> Purpose: Investigate Binance and Bybit testnet environments for risk-free trading validation

## Executive Summary

Both Binance and Bybit provide testnet environments suitable for AI trading system validation. CCXT library supports both exchanges with sandbox mode, but requires custom URL configuration for reliable testnet connections.

**Recommendation**: Prioritize Binance Futures Testnet due to better CCXT integration and active community support.

---

## 1. Binance Testnet

### 1.1 Overview

Binance provides separate testnet environments for Spot and Futures trading, accessible via API only (no web UI for futures testnet).

### 1.2 API Endpoints

| Product | Testnet URL | Production URL |
|---------|------------|----------------|
| Spot | https://demo-api.binance.com | https://api.binance.com |
| USDS-Margined Futures | https://testnet.binancefuture.com/fapi/v1 | https://fapi.binance.com |
| Coin-Margined Futures | https://testnet.binancefuture.com/dapi/v1 | https://dapi.binance.com |
| WebSocket (Futures) | wss://fstream.binancefuture.com | wss://fstream.binance.com |

### 1.3 Key Features

- **Free Test Funds**: Virtual USDT for testing (no real money risk)
- **Full API Parity**: All production endpoints available in testnet
- **Separate API Keys**: Testnet keys generated at [testnet.binancefuture.com](https://testnet.binancefuture.com/)
- **Rate Limits**: Same as production (1200 requests/minute for futures)
- **Order Types**: Market, Limit, Stop-Limit, Take-Profit, Trailing Stop
- **Position Modes**: Hedge Mode (dual-direction) and One-Way Mode

### 1.4 CCXT Integration

#### Standard Sandbox Mode (Unreliable)

```python
import ccxt

exchange = ccxt.binance({
    'apiKey': 'YOUR_TESTNET_KEY',
    'secret': 'YOUR_TESTNET_SECRET',
    'enableRateLimit': True
})
exchange.set_sandbox_mode(True)  # May use outdated endpoints
```

**Issue**: CCXT's built-in sandbox mode may route to old endpoints (e.g., `testnet.binance.vision` for Spot).

#### Recommended: Custom URL Configuration

```python
exchange = ccxt.binance({
    'apiKey': 'YOUR_TESTNET_KEY',
    'secret': 'YOUR_TESTNET_SECRET',
    'enableRateLimit': True,
    'options': {
        'defaultType': 'future',  # 'future' or 'spot'
        'urls': {
            'fapi': 'https://testnet.binancefuture.com/fapi/v1'
        }
    }
})
```

### 1.5 Limitations

- No web trading interface for futures testnet (API only)
- Test funds require manual request (not auto-replenished)
- Some advanced features (e.g., portfolio margin) may be unavailable

### 1.6 References

- [Binance Futures API Documentation](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info)
- [Testnet Quick Start](https://developers.binance.com/docs/derivatives/quick-start)
- [CCXT Binance Futures Tutorial (Jan 2026)](https://medium.com/@aliyansayz/binance-ccxt-python-leverage-trading-api-end-to-end-tutorial-361e35ab53f0)

---

## 2. Bybit Testnet

### 2.1 Overview

Bybit provides a unified testnet environment supporting Spot, Futures (USDT Perpetual, USDC Perpetual, Inverse Perpetual), and Options trading.

### 2.2 API Endpoints

| Environment | Base URL | Account Management |
|-------------|----------|-------------------|
| Testnet | https://api-testnet.bybit.com | https://testnet.bybit.com |
| Production | https://api.bybit.com | https://www.bybit.com |

**API Structure**: `{host}/{version}/{product}/{module}`

Example: `https://api-testnet.bybit.com/v5/market/kline`

### 2.3 Key Features

- **V5 Unified API**: Single API for all products (Spot, Linear, Inverse, Options)
- **Free Test Funds**: Virtual assets available via web interface
- **Full Feature Parity**: All production endpoints supported
- **Rate Limits**: Stricter than production (e.g., 120 req/s vs 200 req/s)
- **Position Modes**: Hedge Mode (buy and sell simultaneously)
- **Order Types**: Market, Limit, Conditional Orders

### 2.4 CCXT Integration

#### Custom URL Configuration (Required)

```python
import ccxt

exchange = ccxt.bybit({
    'apiKey': 'YOUR_TESTNET_KEY',
    'secret': 'YOUR_TESTNET_SECRET',
    'enableRateLimit': True,
    'urls': {
        'api': 'https://api-testnet.bybit.com'
    }
})
```

**Note**: Bybit's `set_sandbox_mode()` may not reliably switch to testnet URLs in all CCXT versions. Explicit URL override recommended.

### 2.5 Limitations

- Testnet data quality may differ slightly from production (market depth, volatility)
- Rate limits are lower than production
- Some new features may be delayed in testnet deployment

### 2.6 References

- [Bybit API Documentation](https://bybit-exchange.github.io/docs/v5/intro)
- [Integration Guidance](https://bybit-exchange.github.io/docs/v5/guide)
- [Testnet Account Registration](https://www.bybit.com/en/help-center/article/How-to-Request-Test-Coins-on-Testnet/)

---

## 3. Comparison Matrix

| Feature | Binance Testnet | Bybit Testnet |
|---------|----------------|---------------|
| **CCXT Support** | ✅ Good (with custom URLs) | ✅ Good (with custom URLs) |
| **API Completeness** | 95% (some portfolio margin features missing) | 98% (nearly full parity) |
| **Test Fund Availability** | Manual request | Web interface auto-claim |
| **Rate Limits** | Same as production | Lower than production |
| **Data Quality** | High (real-time-like) | High (real-time-like) |
| **Community Support** | ⭐⭐⭐⭐⭐ (very active) | ⭐⭐⭐⭐ (active) |
| **Documentation** | Excellent | Excellent |
| **WebSocket Support** | ✅ Yes | ✅ Yes |

---

## 4. Implementation Recommendations

### 4.1 Exchange Selection Strategy

**Primary**: Binance Futures Testnet
- Larger user base = more community resources
- Proven CCXT integration patterns
- Better documentation coverage

**Secondary**: Bybit Testnet
- V5 API is cleaner and more modern
- Easier test fund management
- Good for cross-exchange validation

### 4.2 CCXT Configuration Pattern

```python
def create_testnet_exchange(exchange_type: str, api_key: str, api_secret: str):
    """Create testnet exchange client with proper URL override"""

    if exchange_type == "binance":
        return ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future',
                'urls': {
                    'fapi': 'https://testnet.binancefuture.com/fapi/v1'
                }
            }
        })

    elif exchange_type == "bybit":
        return ccxt.bybit({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'urls': {
                'api': 'https://api-testnet.bybit.com'
            }
        })

    else:
        raise ValueError(f"Unsupported testnet exchange: {exchange_type}")
```

### 4.3 Validation Checklist

Before production deployment, validate on testnet:

- [ ] Account balance retrieval
- [ ] Real-time market data (ticker, klines, orderbook)
- [ ] Order placement (market, limit orders)
- [ ] Position management (open, close, modify)
- [ ] Stop-loss and take-profit order execution
- [ ] Leverage setting
- [ ] Error handling (invalid symbols, insufficient balance)
- [ ] Rate limit compliance
- [ ] WebSocket connectivity (if used)

### 4.4 Known Issues and Workarounds

#### Issue 1: CCXT Sandbox Mode Outdated URLs

**Problem**: `exchange.set_sandbox_mode(True)` may use deprecated endpoints.

**Workaround**: Always use explicit URL override in exchange options.

#### Issue 2: Testnet API Keys Not Working

**Problem**: Using production API keys in testnet (or vice versa).

**Solution**: Generate separate API keys from testnet-specific account management pages:
- Binance: https://testnet.binancefuture.com/
- Bybit: https://testnet.bybit.com/app/user/api-management

#### Issue 3: Rate Limit Differences

**Problem**: Testnet rate limits may differ from production.

**Solution**: Always enable `enableRateLimit: True` in CCXT config and implement exponential backoff retry logic.

---

## 5. Security Considerations

### 5.1 API Key Isolation

**Critical**: Never use production API keys in testnet code or vice versa.

**Implementation**:
```python
# In .env file
TRADING_MODE=testnet  # or 'live'

# Testnet credentials
TESTNET_EXCHANGE=binance
TESTNET_API_KEY=xxx
TESTNET_API_SECRET=xxx

# Production credentials (separate variables)
BINANCE_API_KEY=xxx
BINANCE_API_SECRET=xxx
```

### 5.2 Code Safety Guards

Implement runtime validation to prevent accidental production trading:

```python
def validate_testnet_mode(config):
    """Ensure testnet mode is properly configured"""
    if config.trading_mode == "testnet":
        assert config.testnet_api_key, "Testnet API key missing"
        assert "testnet" in config.exchange_url.lower(), "Not using testnet URL"
    else:
        # Add extra confirmation for production mode
        logger.warning("PRODUCTION MODE ENABLED - Real money at risk!")
```

### 5.3 Configuration File Template

```env
# Trading Mode (CRITICAL: Change to 'live' only after thorough testnet validation)
TRADING_MODE=testnet

# Testnet Configuration
TESTNET_EXCHANGE=binance  # or 'bybit'
TESTNET_API_KEY=your_testnet_key_here
TESTNET_API_SECRET=your_testnet_secret_here

# Production Configuration (Leave empty during testnet phase)
BINANCE_API_KEY=
BINANCE_API_SECRET=
BYBIT_API_KEY=
BYBIT_API_SECRET=
```

---

## 6. Next Steps

1. **Immediate** (Phase 2):
   - Implement `BinanceAdapter` with testnet URL configuration
   - Add `trading_mode` and `testnet_exchange` config validation
   - Create factory function with testnet whitelist (binance, bybit only)

2. **Testing** (Phase 2):
   - Unit tests: Testnet URL configuration correctness
   - Integration tests: Full trading cycle on Binance Testnet
   - Validation: Run system for 1 week on testnet

3. **Future** (Phase 3+):
   - Compare testnet data quality vs production (lag, price deviation)
   - Implement graceful testnet → production migration
   - Document testnet limitations discovered during validation

---

## Appendix: Useful Resources

### Official Documentation
- [Binance Futures API](https://developers.binance.com/docs/derivatives)
- [Bybit API v5](https://bybit-exchange.github.io/docs/v5/intro)
- [CCXT Manual](https://docs.ccxt.com/)

### Community Resources
- [CCXT Testnet Issues](https://github.com/ccxt/ccxt/issues?q=testnet)
- [Binance CCXT Tutorial (Jan 2026)](https://medium.com/@aliyansayz/binance-ccxt-python-leverage-trading-api-end-to-end-tutorial-361e35ab53f0)

### Troubleshooting
- [CCXT Binance Futures Testnet Issue #26487](https://github.com/ccxt/ccxt/issues/26487)
- [CCXT Bybit Testnet Configuration](https://copyprogramming.com/t/ccxt-to-use-binance-bybit-testnet)
