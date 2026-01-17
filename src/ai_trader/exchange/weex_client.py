"""WEEX 交易所客户端 - 基于 httpx 异步实现"""

import hmac
import hashlib
import time
import json
import os
import httpx
import asyncio
from typing import Optional, Dict, Any, List, Union
from ..config import config
from ..utils.logger import logger


class WeexClient:
    """WEEX 合约 API 客户端"""

    def __init__(self):
        self.base_url = config.weex_api_url
        self.api_key = config.weex_api_key
        self.api_secret = config.weex_api_secret
        self.passphrase = config.weex_passphrase

        # Configure proxy from .env if set
        proxy = None
        if config.proxy_url:
            proxy = config.proxy_url
            logger.info(f"Using proxy from .env: {config.proxy_url}")

        self._client = httpx.AsyncClient(timeout=30.0, proxy=proxy)

    def _sign(self, timestamp: str, method: str, path: str, body: str = "") -> str:
        """生成 HMAC-SHA256 签名，然后 Base64 编码

        WEEX 签名规则: timestamp + method + path (+ ? + query_string for GET) + body
        """
        import base64

        message = timestamp + method.upper() + path + body
        signature = hmac.new(
            self.api_secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
        ).digest()

        # WEEX requires Base64 encoded signature
        sign_b64 = base64.b64encode(signature).decode()

        # Debug logging
        logger.debug(f"Sign input: {message}")
        logger.debug(f"Sign output (Base64): {sign_b64}")

        return sign_b64

    def _headers(
        self, method: str, path: str, body: str = "", query_string: str = ""
    ) -> Dict[str, str]:
        """构造请求头

        Args:
            method: GET/POST
            path: API path (e.g., /capi/v2/position/getPositions)
            body: Request body for POST
            query_string: Query string for GET (e.g., symbol=xxx&limit=10)
        """
        ts = str(int(time.time() * 1000))

        # For GET requests with params, include query_string in signature
        sign_path = path
        if query_string:
            sign_path = path + "?" + query_string

        logger.debug(
            f"Headers - method={method}, path={path}, query={query_string}, sign_path={sign_path}"
        )

        return {
            "ACCESS-KEY": self.api_key,
            "ACCESS-SIGN": self._sign(ts, method, sign_path, body),
            "ACCESS-PASSPHRASE": self.passphrase,
            "ACCESS-TIMESTAMP": ts,
            "Content-Type": "application/json",
        }

    async def get_account(self) -> Dict[str, Any]:
        """获取账户信息"""
        path = "/capi/v2/account/getAccounts"
        try:
            r = await self._client.get(
                f"{self.base_url}{path}", headers=self._headers("GET", path)
            )
            r.raise_for_status()
            data = r.json()

            # Debug: Log response structure
            logger.debug(f"Account response: {data}")

            return data
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error getting account: {e.response.status_code} - {e.response.text}"
            )
            return {"code": "HTTP_ERROR", "msg": str(e)}
        except Exception as e:
            logger.error(f"Failed to get account: {e}")
            return {"code": "ERROR", "msg": str(e)}

    async def get_klines(
        self, symbol: str, interval: str = "15m", limit: int = 100
    ) -> List[Any]:
        """获取K线数据

        WEEX API: /capi/v2/market/candles
        - interval is mapped to 'granularity'
        - Returns raw array, not wrapped in {"code": "00000", "data": [...]}
        """
        path = "/capi/v2/market/candles"
        try:
            r = await self._client.get(
                f"{self.base_url}{path}",
                params={"symbol": symbol, "granularity": interval, "limit": limit},
            )
            r.raise_for_status()

            raw_text = r.text
            logger.debug(f"Raw klines response: {raw_text[:200]}...")

            if not raw_text:
                logger.warning("Empty response for klines")
                return []

            data = r.json()

            # WEEX candles endpoint returns raw array: [[ts, open, high, low, close, vol, value], ...]
            if isinstance(data, list):
                return data

            # Fallback: if wrapped
            if data.get("code") == "00000":
                return data.get("data", [])

            logger.warning(f"Get klines unexpected format: {data[:100]}")
            return []

        except Exception as e:
            logger.error(f"Failed to get klines: {e}")
            return []

    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """获取最新价格"""
        path = "/capi/v2/market/ticker"
        try:
            r = await self._client.get(
                f"{self.base_url}{path}", params={"symbol": symbol}
            )
            r.raise_for_status()
            raw_text = r.text
            logger.debug(f"Raw ticker response: {raw_text[:200]}...")

            if not raw_text:
                return {
                    "code": "EMPTY_RESPONSE",
                    "msg": "Response body is empty",
                    "data": None,
                }

            data = r.json()

            # Weex ticker endpoint returns data directly
            if "code" in data:
                return data
            else:
                return {"code": "00000", "data": data}

        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error getting ticker: {e.response.status_code} - {e.response.text}"
            )
            return {"code": "HTTP_ERROR", "msg": str(e), "data": None}
        except Exception as e:
            logger.error(f"Failed to get ticker: {e}")
            return {"code": "ERROR", "msg": str(e), "data": None}

    async def get_positions(self, symbol: str) -> List[Any]:
        """获取当前持仓

        WEEX API: /capi/v2/account/position/singlePosition (单合约)
        """
        # Use single contract position endpoint
        path = "/capi/v2/account/position/singlePosition"
        query_string = f"symbol={symbol}"
        try:
            r = await self._client.get(
                f"{self.base_url}{path}",
                headers=self._headers("GET", path, query_string=query_string),
                params={"symbol": symbol},
            )
            r.raise_for_status()
            data = r.json()

            # Position API returns raw array: [Pos{...}]
            if isinstance(data, list):
                return data

            # Fallback: wrapped format
            if data.get("code") == "00000":
                result = data.get("data", {})
                if isinstance(result, dict):
                    positions = result.get("positions", [])
                    if isinstance(positions, list) and len(positions) > 0:
                        return positions
                elif isinstance(result, list):
                    return result

            logger.warning(f"Get positions (singlePosition) returned empty: {data}")
            return []

        except Exception as e:
            logger.error(f"Failed to get positions (singlePosition): {e}")
            return []

    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """设置杠杆"""
        path = "/capi/v2/account/leverage"
        # marginMode: 1=Cross, 3=Isolated
        body = json.dumps(
            {
                "symbol": symbol,
                "marginMode": 1,  # Cross mode
                "longLeverage": str(leverage),
                "shortLeverage": str(leverage),
            }
        )
        try:
            r = await self._client.post(
                f"{self.base_url}{path}",
                headers=self._headers("POST", path, body),
                content=body,
            )
            data = r.json()
            success = data.get("code") == "200" or data.get("code") == "00000"
            if not success:
                logger.warning(f"Set leverage failed: {data}")
            return success
        except Exception as e:
            logger.error(f"Failed to set leverage: {e}")
            return False

    async def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        size: float,
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> Dict[str, Any]:
        """创建订单"""
        # 生成唯一的 client_oid
        import uuid

        client_oid = str(uuid.uuid4())[:40]

        # 映射 side 到 type
        # 1: Open long, 2: Open short, 3: Close long, 4: Close short
        side_to_type = {
            "open_long": "1",
            "open_short": "2",
            "close_long": "3",
            "close_short": "4",
        }

        # 映射 order_type 到 order_type
        # 0: Normal, 1: Post-Only, 2: Fill-Or-Kill, 3: Immediate Or Cancel
        type_to_order_type = {
            "market": "0",
            "limit": "0",  # 普通限价单
        }

        # match_price: 0=限价, 1=市价
        match_price = "1" if order_type == "market" else "0"

        body_dict = {
            "symbol": symbol,
            "client_oid": client_oid,
            "size": str(size),
            "type": side_to_type.get(side, "1"),
            "order_type": type_to_order_type.get(order_type, "0"),
            "match_price": match_price,
        }

        # 市价单不需要价格，但限价单需要
        if order_type == "limit" and price is None:
            raise ValueError("Price is required for limit orders")

        if price:
            body_dict["price"] = str(round(price, 2))
        if stop_loss:
            body_dict["presetStopLossPrice"] = str(round(stop_loss, 2))
        if take_profit:
            body_dict["presetTakeProfitPrice"] = str(round(take_profit, 2))

        body = json.dumps(body_dict)
        try:
            # 正确的端点
            path = "/capi/v2/order/placeOrder"
            r = await self._client.post(
                f"{self.base_url}{path}",
                headers=self._headers("POST", path, body),
                content=body,
            )
            logger.debug(f"Create order response status: {r.status_code}")
            logger.debug(f"Create order response body: {r.text[:500]}")

            if r.status_code >= 400:
                logger.error(
                    f"Create order failed with status {r.status_code}: {r.text}"
                )
                raise Exception(f"HTTP {r.status_code}: {r.text}")

            if not r.text.strip():
                logger.error("Create order returned empty response")
                raise Exception("Empty response from API")

            return r.json()
        except json.JSONDecodeError as e:
            response_text = r.text if "r" in locals() else "N/A"
            logger.error(
                f"Failed to decode JSON response: {e}, response: {response_text[:500]}"
            )
            raise
        except Exception as e:
            logger.error(f"Failed to create order: {e}")
            raise

    async def close(self):
        await self._client.aclose()
