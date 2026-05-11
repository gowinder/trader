# Kraken XStock Spot Trading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate Kraken XStock (tokenized stocks) spot trading into the existing AI quant trading system, supporting long-only, AI-driven stock buying/selling.

**Architecture:** Parallel to the existing crypto futures pipeline. We add a `KrakenXStockAdapter` extending `BaseExchange` via `ccxt`. The scheduler will distinguish between futures and spot symbols (via `config.is_stock_symbol`), skipping leverage setup and modifying position sizing logic for spot. The decision engine will use a dedicated `stock_trading.py` prompt and stock-specific quant strategies (`StockTrendFollowing`, `StockMeanReversion`), filtering out any short actions.

**Tech Stack:** Python 3.12+, asyncio, ccxt, pydantic, pytest

---

### Task 1: Configuration Updates

**Files:**
- Modify: `src/ai_trader/config.py`
- Modify: `.env.example`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
def test_kraken_stock_config(monkeypatch):
    monkeypatch.setenv("EXCHANGE_TYPE", "kraken")
    monkeypatch.setenv("KRAKEN_API_KEY", "test_key")
    monkeypatch.setenv("KRAKEN_API_SECRET", "test_secret")
    monkeypatch.setenv("STOCK_TRADING_SYMBOLS", "AAPLx/USD, TSLAx/USD")
    monkeypatch.setenv("TRADING_SYMBOLS", "BTC/USDT")
    
    from src.ai_trader.config import Config
    cfg = Config()
    
    assert cfg.exchange_type == "kraken"
    assert cfg.kraken_api_key == "test_key"
    assert cfg.kraken_api_secret == "test_secret"
    
    creds = cfg.get_exchange_credentials("kraken")
    assert creds["api_key"] == "test_key"
    assert creds["api_secret"] == "test_secret"
    
    symbols = cfg.symbols_list
    assert "AAPLx/USD" in symbols
    assert "TSLAx/USD" in symbols
    assert "BTC/USDT" in symbols
    
    assert cfg.is_stock_symbol("AAPLx/USD") is True
    assert cfg.is_stock_symbol("BTC/USDT") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py::test_kraken_stock_config -v`
Expected: FAIL (ValidationError for kraken not in Literal, or missing fields)

- [ ] **Step 3: Write minimal implementation**

Modify `src/ai_trader/config.py`:
1. Update `exchange_type` type hint to include `"kraken"`
2. Add fields for kraken:
```python
    kraken_api_key: str = Field(default="", validation_alias="KRAKEN_API_KEY")
    kraken_api_secret: str = Field(default="", validation_alias="KRAKEN_API_SECRET")
    stock_trading_symbols: str = Field(default="", validation_alias="STOCK_TRADING_SYMBOLS")
```
3. Update `get_exchange_credentials` to include `"kraken"` in `credentials_map`.
4. Update `symbols_list` property to combine `trading_symbols` and `stock_trading_symbols`.
5. Add `is_stock_symbol` method:
```python
    def is_stock_symbol(self, symbol: str) -> bool:
        """检查是否为美股交易对"""
        if not self.stock_trading_symbols:
            return False
        stocks = [s.strip() for s in self.stock_trading_symbols.split(",") if s.strip()]
        return symbol in stocks
```

Modify `.env.example`:
```
EXCHANGE_TYPE=kraken
KRAKEN_API_KEY=
KRAKEN_API_SECRET=
STOCK_TRADING_SYMBOLS=
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py::test_kraken_stock_config -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ai_trader/config.py .env.example tests/test_config.py
git commit -m "feat(config): add kraken and xstock settings"
```

---

### Task 2: Kraken XStock Adapter

**Files:**
- Create: `src/ai_trader/exchange/kraken_xstock_adapter.py`
- Modify: `src/ai_trader/exchange/__init__.py`
- Modify: `src/ai_trader/exchange/base.py` (Add optional `margin_mode` to `Position` model if needed, but it's already there as `str`, so just leave it if it works, or provide default)
- Test: `tests/exchange/test_kraken_xstock_adapter.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/exchange/test_kraken_xstock_adapter.py
import pytest
from src.ai_trader.exchange.kraken_xstock_adapter import KrakenXStockAdapter
from src.ai_trader.models.order import OrderSide
from src.ai_trader.exchange.base import Position

@pytest.mark.asyncio
async def test_kraken_adapter_init():
    adapter = KrakenXStockAdapter(api_key="key", api_secret="secret")
    assert adapter._client.options["defaultType"] == "spot"
    
@pytest.mark.asyncio
async def test_kraken_set_leverage():
    adapter = KrakenXStockAdapter(api_key="key", api_secret="secret")
    result = await adapter.set_leverage("AAPLx/USD", 5)
    assert result is True  # no-op for spot
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/exchange/test_kraken_xstock_adapter.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Write minimal implementation**

Create `src/ai_trader/exchange/kraken_xstock_adapter.py`:
```python
import ccxt.async_support as ccxt
from typing import Dict, List, Optional, Any
from .base import BaseExchange, AccountInfo, Position
from ..models.order import OrderSide
from ..utils.logger import logger

class KrakenXStockAdapter(BaseExchange):
    def __init__(self, api_key: str, api_secret: str, **kwargs):
        self._client = ccxt.kraken({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": {"defaultType": "spot"}
        })

    async def get_account(self) -> AccountInfo:
        balance = await self._client.fetch_balance()
        return AccountInfo(
            total_equity=balance.get('total', {}).get('USD', 0.0),
            available_balance=balance.get('free', {}).get('USD', 0.0)
        )

    async def get_klines(self, symbol: str, timeframe: str = "1h", limit: int = 100) -> List[List[float]]:
        return await self._client.fetch_ohlcv(symbol, timeframe, limit=limit)

    async def get_ticker(self, symbol: str) -> Dict:
        return await self._client.fetch_ticker(symbol)

    async def get_positions(self, symbol: Optional[str] = None) -> List[Position]:
        balance = await self._client.fetch_balance()
        positions = []
        target_symbols = [symbol] if symbol else [s for s in balance.get('total', {}).keys() if s.endswith('x')]
        
        for sym in target_symbols:
            base_currency = sym.split('/')[0] if '/' in sym else sym
            amount = balance.get('total', {}).get(base_currency, 0.0)
            if amount > 0:
                ticker = await self.get_ticker(sym if '/' in sym else f"{sym}/USD")
                mark_price = ticker.get('last', 0.0)
                positions.append(Position(
                    symbol=sym if '/' in sym else f"{sym}/USD",
                    side="long",
                    size=amount,
                    entry_price=mark_price, # We can't easily get avg entry from balance, approximate or use 0
                    mark_price=mark_price,
                    unrealized_pnl=0.0,
                    leverage=1,
                    margin_mode="spot",
                    liquidation_price=0.0,
                    margin=amount * mark_price,
                    roi=0.0
                ))
        return positions

    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        return True

    async def create_order(self, symbol: str, side: OrderSide, order_type: str, quantity: float, price: Optional[float] = None, **kwargs) -> Dict:
        ccxt_side = "buy" if side == OrderSide.OPEN_LONG else "sell"
        # Validate parameter is for testing/dry-run, pass from kwargs if needed
        params = {"asset_class": "tokenized_asset"}
        if kwargs.get('validate'):
            params['validate'] = True
            
        return await self._client.create_order(
            symbol=symbol, type=order_type, side=ccxt_side, 
            amount=quantity, price=price, params=params
        )

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        await self._client.cancel_order(order_id, symbol)
        return True

    async def get_available_symbols(self) -> List[str]:
        markets = await self._client.fetch_markets()
        return [m['symbol'] for m in markets if m.get('spot') and m.get('active') and m.get('quote') == 'USD']
        
    async def close(self):
        await self._client.close()
```

Modify `src/ai_trader/exchange/__init__.py`:
```python
# Add import
from .kraken_xstock_adapter import KrakenXStockAdapter

# In create_exchange_client:
    # After okx and other checks
    if exchange_type == "kraken":
        return KrakenXStockAdapter(
            api_key=creds["api_key"],
            api_secret=creds["api_secret"]
        )
```

Modify `src/ai_trader/exchange/base.py` if necessary (e.g. ensure `margin_mode` default works or is optional).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/exchange/test_kraken_xstock_adapter.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ai_trader/exchange/kraken_xstock_adapter.py src/ai_trader/exchange/__init__.py tests/exchange/test_kraken_xstock_adapter.py
git commit -m "feat(exchange): add kraken xstock adapter"
```

---

### Task 3: Prompts and Hybrid Decision Engine Updates

**Files:**
- Create: `src/ai_trader/prompts/stock_trading.py`
- Modify: `src/ai_trader/ai/hybrid_decision.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/ai/test_hybrid_decision_stock.py
import pytest
from src.ai_trader.ai.hybrid_decision import HybridDecisionEngine
from src.ai_trader.config import config
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_stock_decision_filtering(monkeypatch):
    monkeypatch.setattr(config, "stock_trading_symbols", "AAPLx/USD")
    engine = HybridDecisionEngine(llm_client=AsyncMock(), exchange=AsyncMock())
    
    # Test short signal filtering
    # Assuming we mock _run_stock_strategies and _get_llm_decision to return a short action
    engine._run_stock_strategies = AsyncMock(return_value=None)
    engine._get_llm_decision = AsyncMock() # Mock returning a short decision
    # Further implementation based on exact engine structure
```
*(Keep minimal for this step, just test that `config.is_stock_symbol` branches correctly in the engine if applicable)*

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/ai/test_hybrid_decision_stock.py -v`
Expected: FAIL (file not found or assert fails)

- [ ] **Step 3: Write minimal implementation**

Create `src/ai_trader/prompts/stock_trading.py`:
```python
STOCK_SYSTEM_PROMPT = """
你是一个专业的美股量化交易员。你的任务是分析美股市场的技术指标和价格走势，给出明确的交易决策。
请严格分析成交量、市值、板块轮动。
交易动作只能是：buy, sell, hold, add, reduce。无杠杆。
返回JSON格式：
{
    "action": "buy/sell/hold/add/reduce",
    "confidence": 0.8,
    "position_size_percent": 0.1,
    "stop_loss_percent": 0.05,
    "take_profit_percent": 0.1,
    "reason": "..."
}
"""

STOCK_USER_PROMPT_TEMPLATE = """
Symbol: {symbol}
Current Price: {current_price}
Data:
{indicators}
Market Sentiment:
{sentiment}
"""
```

Modify `src/ai_trader/ai/hybrid_decision.py`:
Add stock logic in the main decision flow:
```python
from ..config import config
from ..prompts.stock_trading import STOCK_SYSTEM_PROMPT, STOCK_USER_PROMPT_TEMPLATE

# Inside HybridDecisionEngine.make_decision:
    if config.is_stock_symbol(symbol):
        # Use stock prompts and strategies
        system_prompt = STOCK_SYSTEM_PROMPT
        user_prompt = STOCK_USER_PROMPT_TEMPLATE.format(...)
        # Run stock strategies
        # Filter actions: if action in ['open_short', 'close_short'], convert to 'hold'
        # Force leverage = 1
        decision.leverage = 1
        if decision.action in ["open_short", "close_short", "reduce_short"]:
            decision.action = "hold"
        return decision
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/ai/test_hybrid_decision_stock.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ai_trader/prompts/stock_trading.py src/ai_trader/ai/hybrid_decision.py tests/ai/test_hybrid_decision_stock.py
git commit -m "feat(ai): add stock trading prompts and decision filtering"
```

---

### Task 4: Stock Strategies

**Files:**
- Create: `src/ai_trader/strategies/stock/__init__.py`
- Create: `src/ai_trader/strategies/stock/stock_strategy_base.py`
- Create: `src/ai_trader/strategies/stock/stock_trend_following.py`
- Create: `src/ai_trader/strategies/stock/stock_mean_reversion.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/strategies/test_stock_strategies.py
import pytest
from src.ai_trader.strategies.stock.stock_trend_following import StockTrendFollowing
from src.ai_trader.strategies.stock.stock_strategy_base import StockSignalAction

def test_trend_following_no_short():
    strategy = StockTrendFollowing()
    # Mock some bearish data
    data = {"ma7": 100, "ma25": 110, "macd": -1}
    signal = strategy.analyze(data)
    # Even if bearish, shouldn't output short, maybe sell if holding, but typically BUY/SELL/HOLD for spot
    assert signal.action in [StockSignalAction.SELL, StockSignalAction.HOLD]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/strategies/test_stock_strategies.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Write minimal implementation**

Create `src/ai_trader/strategies/stock/stock_strategy_base.py`:
```python
from enum import Enum
from pydantic import BaseModel
from typing import Optional

class StockSignalAction(Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"

class StockSignal(BaseModel):
    action: StockSignalAction
    confidence: float
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    reason: str = ""

class StockStrategyBase:
    def analyze(self, data: dict) -> StockSignal:
        raise NotImplementedError
```

Create `src/ai_trader/strategies/stock/stock_trend_following.py`:
```python
from .stock_strategy_base import StockStrategyBase, StockSignal, StockSignalAction

class StockTrendFollowing(StockStrategyBase):
    def analyze(self, data: dict) -> StockSignal:
        ma7 = data.get("ma7", 0)
        ma25 = data.get("ma25", 0)
        macd = data.get("macd", 0)
        
        if ma7 > ma25 and macd > 0:
            return StockSignal(action=StockSignalAction.BUY, confidence=0.8, reason="Trend up")
        elif ma7 < ma25 and macd < 0:
            return StockSignal(action=StockSignalAction.SELL, confidence=0.8, reason="Trend down")
        
        return StockSignal(action=StockSignalAction.HOLD, confidence=0.5, reason="Neutral")
```

Create `src/ai_trader/strategies/stock/stock_mean_reversion.py`:
```python
from .stock_strategy_base import StockStrategyBase, StockSignal, StockSignalAction

class StockMeanReversion(StockStrategyBase):
    def analyze(self, data: dict) -> StockSignal:
        rsi = data.get("rsi14", 50)
        # Add bollinger logic
        if rsi < 30:
            return StockSignal(action=StockSignalAction.BUY, confidence=0.7, reason="Oversold")
        elif rsi > 70:
            return StockSignal(action=StockSignalAction.SELL, confidence=0.7, reason="Overbought")
            
        return StockSignal(action=StockSignalAction.HOLD, confidence=0.5, reason="Neutral")
```

Create `src/ai_trader/strategies/stock/__init__.py`:
```python
from .stock_strategy_base import StockStrategyBase, StockSignal, StockSignalAction
from .stock_trend_following import StockTrendFollowing
from .stock_mean_reversion import StockMeanReversion
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/strategies/test_stock_strategies.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ai_trader/strategies/stock/ tests/strategies/test_stock_strategies.py
git commit -m "feat(strategies): add stock-specific long-only quant strategies"
```

---

### Task 5: Scheduler Updates

**Files:**
- Modify: `src/ai_trader/scheduler.py`
- Test: `tests/test_scheduler_stock.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scheduler_stock.py
import pytest
from src.ai_trader.scheduler import TraderScheduler
from unittest.mock import AsyncMock
from src.ai_trader.config import config

@pytest.mark.asyncio
async def test_scheduler_stock_leverage_skip(monkeypatch):
    monkeypatch.setattr(config, "stock_trading_symbols", "AAPLx/USD")
    scheduler = TraderScheduler()
    scheduler.exchange = AsyncMock()
    scheduler.exchange.set_leverage = AsyncMock()
    scheduler.exchange.get_ticker = AsyncMock(return_value={'last': 100})
    scheduler.exchange.get_account = AsyncMock(return_value=AsyncMock(available_balance=1000))
    scheduler.db_manager = AsyncMock()
    
    # We want to assert set_leverage is not called for stock symbols
    # Implement a focused mock of _run_cycle_for_symbol_impl
```
*(Use logic to test that leverage is not set or that cooldowns are bypassed for spot)*

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_scheduler_stock.py -v`
Expected: FAIL 

- [ ] **Step 3: Write minimal implementation**

Modify `src/ai_trader/scheduler.py`:
In `_run_cycle_for_symbol_impl` (or wherever leverage is set):
```python
    is_stock = config.is_stock_symbol(symbol)
    
    # 1. Skip leverage setup
    if not is_stock:
        await self.exchange.set_leverage(symbol, leverage)
        
    # 2. Modify stop-loss/take-profit check
    if is_stock:
        # Only check long positions
        pass
    else:
        # Check long and short positions
        pass
        
    # 3. Position size calculation
    if is_stock:
        quantity = (available_balance * position_percent) / price
    else:
        quantity = (available_balance * position_percent * leverage) / price
        
    # 4. Skip reverse cooldown
    if is_stock:
        pass # don't check reverse cooldown
```

*(Ensure all usages of `leverage` in the scheduler correctly use `1` for stocks and calculate margin correctly as `size * entry_price` before saving to `position_history`)*

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_scheduler_stock.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ai_trader/scheduler.py tests/test_scheduler_stock.py
git commit -m "feat(scheduler): adapt cycle logic for spot stock symbols"
```

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | issues_open | 10 issues, 4 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |

**UNRESOLVED:** 0 — all issues resolved by user decisions
**CRITICAL GAPS:** 4 regression test gaps (contract position sizing, SL/TP both-sides check, reverse cooldown, margin calc)
**MODE:** SCOPE_REDUCED — KrakenXStockAdapter removed → CCXTSpotAdapter; 4 strategy files removed → inline filtering
**VERDICT:** eng review required — 4 regression tests + 24 test gaps must be addressed in implementation

### Scope Reductions Applied
- **Issue 1:** KrakenXStockAdapter (80 lines) → `CCXTSpotAdapter(CCXTAdapter)` minimal subclass (40 lines) — avoids interface bugs (missing AccountInfo fields, Dict vs Ticker mismatch)
- **Issue 2:** 4 stock strategy files → reuse existing `TrendFollowingStrategy` / `MeanReversionStrategy` + inline SHORT filtering in `hybrid_decision.py`

### Architecture Decisions
- **Issue 3:** `is_stock_symbol()` string parsing → symbol metadata object with `is_spot` flag
- **Issue 4:** CCXTAdapter hardcoded `defaultType: "swap"` → `CCXTSpotAdapter(CCXTAdapter)` subclass overriding `get_positions()` and `set_leverage()`
- **Issue 5:** Scheduler change points underspecified — line numbers documented: sizing (L2682), SL/TP (L2473), SignalFilter (L2624), margin recovery
- **Issue 6:** USD vs USDT balance — acknowledged risk, verify ccxt normalization at implementation time

### Code Quality Decisions
- **Issue 7:** Stock prompt (20 lines) → structured like existing `trading.py` (60-80 lines) with JSON schema, enums, discipline rules
- **Issue 8:** `hybrid_decision.py` changes vague — decision.leverage=1 placement, SHORT filtering placement, prompt selection anchored at `analyze_and_decide`
- **Issue 9:** `exchange_type` Literal → `credentials_map` refactored to data-driven to prevent sync drift

### Test Decisions
- **Issue 10:** 4 regression tests required for contract paths that the stock change touches (sizing, SL/TP, reverse cooldown, margin)
- 24 total test gaps identified across config, adapter, prompts, hybrid_decision, scheduler
- Test plan artifact: `~/.gstack/projects/gowinder-trader/gowinder-develop-eng-review-test-plan-20260511-155741.md`

### Scheduler Change Points (to be refined in plan)
| Location | Current Behavior | Stock Change |
|----------|-----------------|--------------|
| L2682: `amount_usdt = balance * pct/100 * decision.leverage` | Multiply by leverage | Force `decision.leverage = 1` for stocks |
| L2473: `_check_stop_loss_take_profit()` | Check long+short | Check long only for stocks |
| L2624: `SignalFilter(reverse_cooldown_hours=...)` | Enforce both directions | Disable reverse cooldown for stocks |
| L2278: `margin = (entry_price * size) / leverage` | Divide by leverage | `margin = size * entry_price` for stocks |
