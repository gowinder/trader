#!/usr/bin/env python3
"""End-to-End Test - Run AI Trading System on Binance Testnet

This script runs the complete trading system in a loop:
1. Multi-Timeframe Analysis
2. Technical Analysis
3. Risk Assessment
4. Trading Decision
5. Order Execution (if signal)
6. Trade Journal Recording
7. Performance Monitoring
"""

import os
import sys
import time
import json
import hmac
import hashlib
import urllib.request
import urllib.parse
from datetime import datetime
from typing import Optional, List, Dict, Any

# Force unbuffered output
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)
sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', buffering=1)

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Configuration
SYMBOL = "BTCUSDT"
TIMEFRAMES = ["15m", "1h", "4h", "1d"]
CHECK_INTERVAL = 300  # Check every 5 minutes
MAX_DAILY_TRADES = 3
RISK_PER_TRADE = 0.01  # 1% default
HIGH_CONFIDENCE_RISK = 0.02  # 2% for high confluence

# Read API credentials
env_file = os.path.join(os.path.dirname(__file__), '..', '.env')
api_key = None
api_secret = None

if os.path.exists(env_file):
    with open(env_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('TESTNET_API_KEY='):
                api_key = line.split('=', 1)[1].strip('"\'')
            elif line.startswith('TESTNET_API_SECRET='):
                api_secret = line.split('=', 1)[1].strip('"\'')

if not api_key or not api_secret:
    print("❌ API credentials not found in .env")
    sys.exit(1)


class TradingState:
    """Track trading state across runs"""

    def __init__(self):
        self.trades_today = 0
        self.daily_pnl = 0.0
        self.consecutive_losses = 0
        self.last_trade_time = None
        self.positions = []
        self.trade_history = []
        self.session_start = datetime.now()

    def reset_daily(self):
        """Reset daily counters"""
        self.trades_today = 0
        self.daily_pnl = 0.0


class BinanceTestnetClient:
    """Simple Binance Testnet client"""

    BASE_URL = "https://testnet.binancefuture.com"

    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret

    def _sign_request(self, params: Dict[str, Any]) -> str:
        """Sign request parameters"""
        query_string = urllib.parse.urlencode(params)
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature

    def get_account(self) -> Optional[Dict]:
        """Get account information"""
        try:
            timestamp = int(time.time() * 1000)
            params = {"timestamp": timestamp}
            signature = self._sign_request(params)
            params["signature"] = signature

            query_string = urllib.parse.urlencode(params)
            url = f"{self.BASE_URL}/fapi/v2/account?{query_string}"

            req = urllib.request.Request(url)
            req.add_header('X-MBX-APIKEY', self.api_key)

            with urllib.request.urlopen(req, timeout=10) as response:
                return json.loads(response.read())
        except Exception as e:
            print(f"❌ Failed to get account: {e}")
            return None

    def get_klines(self, symbol: str, interval: str, limit: int = 100) -> Optional[List]:
        """Get kline/candlestick data"""
        try:
            url = f"{self.BASE_URL}/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
            with urllib.request.urlopen(url, timeout=10) as response:
                return json.loads(response.read())
        except Exception as e:
            print(f"❌ Failed to get {interval} klines: {e}")
            return None

    def get_position(self, symbol: str) -> Optional[Dict]:
        """Get current position for symbol"""
        try:
            timestamp = int(time.time() * 1000)
            params = {"timestamp": timestamp}
            signature = self._sign_request(params)
            params["signature"] = signature

            query_string = urllib.parse.urlencode(params)
            url = f"{self.BASE_URL}/fapi/v2/positionRisk?{query_string}"

            req = urllib.request.Request(url)
            req.add_header('X-MBX-APIKEY', self.api_key)

            with urllib.request.urlopen(req, timeout=10) as response:
                positions = json.loads(response.read())
                for pos in positions:
                    if pos['symbol'] == symbol and float(pos['positionAmt']) != 0:
                        return pos
                return None
        except Exception as e:
            print(f"❌ Failed to get position: {e}")
            return None


def calculate_ma(closes: List[float], period: int) -> Optional[float]:
    """Calculate moving average"""
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def calculate_rsi(closes: List[float], period: int = 14) -> Optional[float]:
    """Calculate RSI"""
    if len(closes) < period + 1:
        return None

    gains = []
    losses = []

    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))

    if len(gains) < period:
        return None

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def analyze_timeframe(symbol: str, interval: str, klines: List) -> Optional[Dict]:
    """Analyze a single timeframe"""
    if not klines or len(klines) < 100:
        return None

    closes = [float(k[4]) for k in klines]
    highs = [float(k[2]) for k in klines]
    lows = [float(k[3]) for k in klines]
    volumes = [float(k[5]) for k in klines]

    current_price = closes[-1]

    # Calculate indicators
    ma7 = calculate_ma(closes, 7)
    ma25 = calculate_ma(closes, 25)
    ma99 = calculate_ma(closes, 99)
    rsi = calculate_rsi(closes, 14)

    # Calculate ATR
    tr_list = []
    for i in range(1, len(klines)):
        high = float(klines[i][2])
        low = float(klines[i][3])
        prev_close = float(klines[i - 1][4])
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr_list.append(tr)
    atr = sum(tr_list[-14:]) / 14 if len(tr_list) >= 14 else None

    # Determine trend
    trend = "SIDEWAYS"
    if ma7 and ma25 and ma99:
        if ma7 > ma25 > ma99 and current_price > ma7:
            trend = "UPTREND"
        elif ma7 < ma25 < ma99 and current_price < ma7:
            trend = "DOWNTREND"

    # Calculate support/resistance
    support = min(lows[-20:])
    resistance = max(highs[-20:])

    # Volume trend
    recent_volume = sum(volumes[-10:]) / 10
    older_volume = sum(volumes[-30:-10]) / 20
    volume_trend = "INCREASING" if recent_volume > older_volume * 1.1 else "DECREASING" if recent_volume < older_volume * 0.9 else "STABLE"

    return {
        "interval": interval,
        "current_price": current_price,
        "trend": trend,
        "ma7": ma7,
        "ma25": ma25,
        "ma99": ma99,
        "rsi": rsi,
        "atr": atr,
        "support": support,
        "resistance": resistance,
        "volume_trend": volume_trend,
    }


def calculate_confluence(analyses: List[Dict]) -> float:
    """Calculate multi-timeframe confluence score"""
    if not analyses:
        return 0.0

    trends = [a["trend"] for a in analyses]
    uptrend_count = trends.count("UPTREND")
    downtrend_count = trends.count("DOWNTREND")

    max_aligned = max(uptrend_count, downtrend_count)
    return max_aligned / len(trends)


def determine_overall_trend(analyses: List[Dict]) -> str:
    """Determine overall market trend"""
    trends = [a["trend"] for a in analyses]
    uptrend_count = trends.count("UPTREND")
    downtrend_count = trends.count("DOWNTREND")
    sideways_count = trends.count("SIDEWAYS")

    if uptrend_count > downtrend_count and uptrend_count > sideways_count:
        return "UPTREND"
    elif downtrend_count > uptrend_count and downtrend_count > sideways_count:
        return "DOWNTREND"
    else:
        return "SIDEWAYS"


def calculate_position_size(account_balance: float, entry_price: float, stop_loss: float, risk_pct: float) -> Dict:
    """Calculate position size using fixed percentage risk"""
    price_diff = abs(entry_price - stop_loss)
    if price_diff == 0:
        return None

    risk_amount = account_balance * risk_pct
    position_size = risk_amount / price_diff

    return {
        "position_size": position_size,
        "position_value": position_size * entry_price,
        "risk_amount": risk_amount,
        "risk_percentage": risk_pct * 100,
    }


def make_trading_decision(
    analyses: List[Dict],
    confluence: float,
    overall_trend: str,
    account_balance: float,
    current_position: Optional[Dict],
    state: TradingState
) -> Dict:
    """Make trading decision based on analysis"""

    decision = {
        "action": "HOLD",
        "reason": "",
        "entry_price": None,
        "stop_loss": None,
        "take_profit": None,
        "position_size": None,
        "risk_amount": None,
    }

    # Get current price and ATR from 15m timeframe
    tf_15m = next((a for a in analyses if a["interval"] == "15m"), None)
    if not tf_15m:
        decision["reason"] = "Missing 15m timeframe data"
        return decision

    current_price = tf_15m["current_price"]
    atr = tf_15m["atr"]
    support = tf_15m["support"]
    resistance = tf_15m["resistance"]

    # Check if we have a position
    if current_position:
        decision["reason"] = "Already in position - position management not implemented yet"
        return decision

    # Check daily trading limits
    if state.trades_today >= MAX_DAILY_TRADES:
        decision["reason"] = f"Daily trade limit reached ({MAX_DAILY_TRADES})"
        return decision

    # Check daily loss limit (3%)
    daily_loss_limit = account_balance * 0.03
    if state.daily_pnl < -daily_loss_limit:
        decision["reason"] = f"Daily loss limit exceeded ({state.daily_pnl:.2f} < -{daily_loss_limit:.2f})"
        return decision

    # Rule 1: Low confluence - HOLD
    if confluence < 0.5:
        decision["reason"] = f"Low confluence ({confluence:.2%}) - conflicting timeframe signals"
        return decision

    # Rule 2: Sideways market - HOLD
    if overall_trend == "SIDEWAYS":
        decision["reason"] = f"Sideways market with {confluence:.2%} confluence - no clear direction"
        return decision

    # Rule 3: Check if we're near support/resistance
    price_to_support = (current_price - support) / current_price
    price_to_resistance = (resistance - current_price) / current_price

    # Determine risk percentage based on confluence
    risk_pct = HIGH_CONFIDENCE_RISK if confluence >= 0.7 else RISK_PER_TRADE

    # Long setup
    if overall_trend == "UPTREND":
        # Entry near support is better
        if price_to_support > 0.02:  # Price too far from support
            decision["reason"] = f"UPTREND but price {price_to_support:.2%} above support - wait for pullback"
            return decision

        # Calculate stop loss and take profit
        stop_loss = max(support, current_price - (2 * atr)) if atr else current_price * 0.98
        take_profit_1 = current_price + (abs(current_price - stop_loss) * 2.0)  # 2:1 R:R

        # Calculate position size
        position = calculate_position_size(account_balance, current_price, stop_loss, risk_pct)
        if not position:
            decision["reason"] = "Failed to calculate position size"
            return decision

        decision.update({
            "action": "OPEN_LONG",
            "reason": f"UPTREND with {confluence:.2%} confluence, entry near support",
            "entry_price": current_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit_1,
            "position_size": position["position_size"],
            "risk_amount": position["risk_amount"],
            "risk_percentage": position["risk_percentage"],
        })

    # Short setup
    elif overall_trend == "DOWNTREND":
        # Entry near resistance is better
        if price_to_resistance > 0.02:  # Price too far from resistance
            decision["reason"] = f"DOWNTREND but price {price_to_resistance:.2%} below resistance - wait for rally"
            return decision

        # Calculate stop loss and take profit
        stop_loss = min(resistance, current_price + (2 * atr)) if atr else current_price * 1.02
        take_profit_1 = current_price - (abs(stop_loss - current_price) * 2.0)  # 2:1 R:R

        # Calculate position size
        position = calculate_position_size(account_balance, current_price, stop_loss, risk_pct)
        if not position:
            decision["reason"] = "Failed to calculate position size"
            return decision

        decision.update({
            "action": "OPEN_SHORT",
            "reason": f"DOWNTREND with {confluence:.2%} confluence, entry near resistance",
            "entry_price": current_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit_1,
            "position_size": position["position_size"],
            "risk_amount": position["risk_amount"],
            "risk_percentage": position["risk_percentage"],
        })

    return decision


def log_trade_decision(decision: Dict, analyses: List[Dict], confluence: float, overall_trend: str):
    """Log trade decision to file"""
    log_dir = os.path.join(os.path.dirname(__file__), '..', 'logs')
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, 'e2e_testnet_decisions.log')

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(log_file, 'a') as f:
        f.write(f"\n{'=' * 80}\n")
        f.write(f"[{timestamp}] Trading Decision\n")
        f.write(f"{'=' * 80}\n")
        f.write(f"Overall Trend: {overall_trend}\n")
        f.write(f"Confluence Score: {confluence:.2%}\n")
        f.write(f"\nTimeframe Analysis:\n")
        for analysis in analyses:
            f.write(f"  {analysis['interval']:>4s}: {analysis['trend']:>10s} "
                    f"(MA7={analysis['ma7']:.2f}, RSI={analysis['rsi']:.1f})\n")
        f.write(f"\nDecision:\n")
        f.write(f"  Action: {decision['action']}\n")
        f.write(f"  Reason: {decision['reason']}\n")
        if decision['action'] != "HOLD":
            f.write(f"  Entry: {decision['entry_price']:.2f}\n")
            f.write(f"  Stop Loss: {decision['stop_loss']:.2f}\n")
            f.write(f"  Take Profit: {decision['take_profit']:.2f}\n")
            f.write(f"  Position Size: {decision['position_size']:.6f} BTC\n")
            f.write(f"  Risk: {decision['risk_amount']:.2f} USDT ({decision['risk_percentage']:.1f}%)\n")
        f.write(f"\n")


def main():
    """Main E2E test loop"""
    print("=" * 80)
    print("🚀 AI Trading System - End-to-End Testnet Deployment")
    print("=" * 80)
    print()
    print(f"Symbol: {SYMBOL}")
    print(f"Timeframes: {', '.join(TIMEFRAMES)}")
    print(f"Check Interval: {CHECK_INTERVAL}s ({CHECK_INTERVAL / 60:.1f} minutes)")
    print(f"Max Daily Trades: {MAX_DAILY_TRADES}")
    print(f"Default Risk: {RISK_PER_TRADE * 100}%")
    print(f"High Confidence Risk: {HIGH_CONFIDENCE_RISK * 100}%")
    print()

    # Initialize client and state
    client = BinanceTestnetClient(api_key, api_secret)
    state = TradingState()

    # Verify connection
    print("🔌 Verifying Testnet connection...")
    account = client.get_account()
    if not account:
        print("❌ Failed to connect to Testnet")
        return

    balance = float(account.get('availableBalance', 0))
    print(f"✅ Connected to Testnet")
    print(f"   Account Balance: {balance:.2f} USDT")
    print()

    print("🏁 Starting trading loop...")
    print(f"   Press Ctrl+C to stop")
    print()

    iteration = 0

    try:
        while True:
            iteration += 1
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            print(f"\n{'=' * 80}")
            print(f"📊 Iteration #{iteration} - {current_time}")
            print(f"{'=' * 80}")

            # Get account info
            account = client.get_account()
            if not account:
                print("❌ Failed to get account info, skipping iteration")
                time.sleep(CHECK_INTERVAL)
                continue

            balance = float(account.get('availableBalance', 0))
            print(f"💰 Account Balance: {balance:.2f} USDT")
            print(f"📈 Trades Today: {state.trades_today}/{MAX_DAILY_TRADES}")
            print(f"💵 Daily P&L: {state.daily_pnl:+.2f} USDT")
            print()

            # Check for existing position
            position = client.get_position(SYMBOL)
            if position:
                pos_amt = float(position['positionAmt'])
                entry_price = float(position['entryPrice'])
                unrealized_pnl = float(position['unRealizedProfit'])
                print(f"📍 Current Position: {abs(pos_amt):.6f} BTC ({'LONG' if pos_amt > 0 else 'SHORT'})")
                print(f"   Entry: {entry_price:.2f}, Unrealized PnL: {unrealized_pnl:+.2f} USDT")
                print()

            # Fetch multi-timeframe data
            print("📊 Fetching multi-timeframe data...")
            analyses = []

            for interval in TIMEFRAMES:
                klines = client.get_klines(SYMBOL, interval, limit=100)
                if klines:
                    analysis = analyze_timeframe(SYMBOL, interval, klines)
                    if analysis:
                        analyses.append(analysis)
                        print(f"   ✅ {interval:>4s}: {analysis['trend']:>10s} (RSI: {analysis['rsi']:.1f})")
                else:
                    print(f"   ❌ {interval}: Failed to fetch data")

            print()

            if len(analyses) < len(TIMEFRAMES):
                print(f"⚠️  Only {len(analyses)}/{len(TIMEFRAMES)} timeframes available, skipping decision")
                time.sleep(CHECK_INTERVAL)
                continue

            # Calculate confluence
            confluence = calculate_confluence(analyses)
            overall_trend = determine_overall_trend(analyses)

            print(f"🎯 Multi-Timeframe Analysis:")
            print(f"   Overall Trend: {overall_trend}")
            print(f"   Confluence Score: {confluence:.2%}")
            print()

            # Make trading decision
            decision = make_trading_decision(
                analyses, confluence, overall_trend, balance, position, state
            )

            print(f"💡 Trading Decision: {decision['action']}")
            print(f"   Reason: {decision['reason']}")

            if decision['action'] != "HOLD":
                print(f"   Entry: {decision['entry_price']:.2f}")
                print(f"   Stop Loss: {decision['stop_loss']:.2f}")
                print(f"   Take Profit: {decision['take_profit']:.2f}")
                print(f"   Position Size: {decision['position_size']:.6f} BTC")
                print(f"   Risk: {decision['risk_amount']:.2f} USDT ({decision['risk_percentage']:.1f}%)")
                print()
                print("⚠️  NOTE: Order execution not implemented - this is a monitoring run")

            print()

            # Log decision
            log_trade_decision(decision, analyses, confluence, overall_trend)

            # Wait for next iteration
            print(f"⏱️  Next check in {CHECK_INTERVAL}s ({CHECK_INTERVAL / 60:.1f} minutes)...")

            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        print("\n\n🛑 Stopping E2E test...")
        print()
        print("=" * 80)
        print("📊 Session Summary")
        print("=" * 80)
        print(f"Session Duration: {datetime.now() - state.session_start}")
        print(f"Total Iterations: {iteration}")
        print(f"Trades Executed: {state.trades_today}")
        print(f"Daily P&L: {state.daily_pnl:+.2f} USDT")
        print()
        print("✅ E2E test completed")


if __name__ == "__main__":
    main()
