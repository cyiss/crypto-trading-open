"""
WEEX 交易所适配器 - REST 模块

本模块职责：
- 管理 aiohttp session
- 处理 API 认证（签名）
- 封装 REST API 请求（行情、账户、交易）
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import base64
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import aiohttp

from .weex_base import WeexBase, datetime_to_unix_ms


class WeexRest(WeexBase):
    """WEEX REST API 客户端"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化 WEEX REST 客户端
        
        Args:
            config: 配置字典
        """
        super().__init__(config)
        timeout_s = int(config.get("request_timeout", 10))
        self._timeout = aiohttp.ClientTimeout(total=timeout_s)
        self._session: Optional[aiohttp.ClientSession] = None
        self._lock: asyncio.Lock = asyncio.Lock()

    async def close(self) -> None:
        """关闭底层 HTTP 会话"""
        if self._session:
            await self._session.close()
            self._session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取/懒加载 aiohttp 会话"""
        if self._session and not self._session.closed:
            return self._session
        self._session = aiohttp.ClientSession(
            timeout=self._timeout,
            headers={"Content-Type": "application/json"}
        )
        return self._session

    def _generate_signature(self, timestamp: int, request_path: str) -> str:
        """
        生成 WEEX API 签名
        
        Args:
            timestamp: 毫秒级时间戳
            request_path: 请求路径（如 /v2/ws/private）
            
        Returns:
            Base64 编码的签名
        """
        message = str(timestamp) + request_path
        signature = hmac.new(
            self.api_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).digest()
        return base64.b64encode(signature).decode()

    def _get_auth_headers(self, request_path: str = "/capi/v2") -> Dict[str, str]:
        """
        获取认证请求头
        
        Args:
            request_path: 请求路径
            
        Returns:
            认证请求头字典
        """
        timestamp = datetime_to_unix_ms(datetime.now(timezone.utc))
        signature = self._generate_signature(timestamp, request_path)
        
        return {
            "ACCESS-KEY": self.api_key,
            "ACCESS-SIGN": signature,
            "ACCESS-TIMESTAMP": str(timestamp),
            "ACCESS-PASSPHRASE": self.api_passphrase or "",
        }

    async def get_server_time(self) -> int:
        """
        获取服务器时间
        
        Returns:
            服务器时间戳（毫秒）
        """
        url = f"{self.rest_endpoint}/capi/v2/market/time"
        session = await self._get_session()
        
        async with session.get(url) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise RuntimeError(f"获取服务器时间失败: status={resp.status} body={text[:500]}")
            data = await resp.json()
            return int(data.get("serverTime", 0))

    async def get_contracts_info(self, symbol: Optional[str] = None) -> list:
        """
        获取合约信息
        
        Args:
            symbol: 交易对（可选）
            
        Returns:
            合约信息列表
        """
        url = f"{self.rest_endpoint}/capi/v2/market/contracts"
        session = await self._get_session()
        
        params = {}
        if symbol:
            params["symbol"] = symbol
        
        async with session.get(url, params=params) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise RuntimeError(f"获取合约信息失败: status={resp.status} body={text[:500]}")
            return await resp.json()

    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        获取单个交易对的行情
        
        Args:
            symbol: 交易对
            
        Returns:
            行情数据
        """
        url = f"{self.rest_endpoint}/capi/v2/market/ticker"
        session = await self._get_session()
        
        params = {"symbol": symbol}
        
        async with session.get(url, params=params) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise RuntimeError(f"获取行情失败: status={resp.status} body={text[:500]}")
            data = await resp.json()
            return data[0] if isinstance(data, list) and data else data

    async def get_order_book(self, symbol: str, limit: int = 20) -> Dict[str, Any]:
        """
        获取订单簿
        
        Args:
            symbol: 交易对
            limit: 深度限制
            
        Returns:
            订单簿数据
        """
        url = f"{self.rest_endpoint}/capi/v2/market/depth"
        session = await self._get_session()
        
        params = {"symbol": symbol, "limit": limit}
        
        async with session.get(url, params=params) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise RuntimeError(f"获取订单簿失败: status={resp.status} body={text[:500]}")
            return await resp.json()

    async def get_account_info(self) -> Dict[str, Any]:
        """
        获取账户信息
        
        Returns:
            账户信息
        """
        url = f"{self.rest_endpoint}/capi/v2/account/info"
        session = await self._get_session()
        headers = self._get_auth_headers("/capi/v2/account/info")
        
        async with session.get(url, headers=headers) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise RuntimeError(f"获取账户信息失败: status={resp.status} body={text[:500]}")
            return await resp.json()

    async def get_positions(self, symbol: Optional[str] = None) -> list:
        """
        获取持仓
        
        Args:
            symbol: 交易对（可选）
            
        Returns:
            持仓列表
        """
        url = f"{self.rest_endpoint}/capi/v2/account/positions"
        session = await self._get_session()
        headers = self._get_auth_headers("/capi/v2/account/positions")
        
        params = {}
        if symbol:
            params["symbol"] = symbol
        
        async with session.get(url, params=params, headers=headers) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise RuntimeError(f"获取持仓失败: status={resp.status} body={text[:500]}")
            return await resp.json()

    async def get_balance(self) -> Dict[str, Any]:
        """
        获取账户余额
        
        Returns:
            余额信息
        """
        url = f"{self.rest_endpoint}/capi/v2/account/balance"
        session = await self._get_session()
        headers = self._get_auth_headers("/capi/v2/account/balance")
        
        async with session.get(url, headers=headers) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise RuntimeError(f"获取余额失败: status={resp.status} body={text[:500]}")
            return await resp.json()

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: str,
        price: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        下单
        
        Args:
            symbol: 交易对
            side: 方向 (buy/sell)
            order_type: 订单类型 (limit/market)
            quantity: 数量
            price: 价格（限价单需要）
            **kwargs: 其他参数
            
        Returns:
            订单信息
        """
        url = f"{self.rest_endpoint}/capi/v2/trade/order"
        session = await self._get_session()
        headers = self._get_auth_headers("/capi/v2/trade/order")
        
        data = {
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "quantity": quantity,
        }
        
        if price:
            data["price"] = price
        
        # 添加其他参数
        data.update(kwargs)
        
        async with session.post(url, json=data, headers=headers) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise RuntimeError(f"下单失败: status={resp.status} body={text[:500]}")
            return await resp.json()

    async def cancel_order(self, symbol: str, order_id: str) -> Dict[str, Any]:
        """
        撤销订单
        
        Args:
            symbol: 交易对
            order_id: 订单 ID
            
        Returns:
            撤销结果
        """
        url = f"{self.rest_endpoint}/capi/v2/trade/order/{order_id}"
        session = await self._get_session()
        headers = self._get_auth_headers(f"/capi/v2/trade/order/{order_id}")
        
        params = {"symbol": symbol}
        
        async with session.delete(url, params=params, headers=headers) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise RuntimeError(f"撤销订单失败: status={resp.status} body={text[:500]}")
            return await resp.json()

    async def get_orders(self, symbol: str, status: Optional[str] = None) -> list:
        """
        获取订单列表
        
        Args:
            symbol: 交易对
            status: 订单状态（可选）
            
        Returns:
            订单列表
        """
        url = f"{self.rest_endpoint}/capi/v2/trade/orders"
        session = await self._get_session()
        headers = self._get_auth_headers("/capi/v2/trade/orders")
        
        params = {"symbol": symbol}
        if status:
            params["status"] = status
        
        async with session.get(url, params=params, headers=headers) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise RuntimeError(f"获取订单列表失败: status={resp.status} body={text[:500]}")
            return await resp.json()

    async def get_order(self, symbol: str, order_id: str) -> Dict[str, Any]:
        """
        获取单个订单信息
        
        Args:
            symbol: 交易对
            order_id: 订单 ID
            
        Returns:
            订单信息
        """
        url = f"{self.rest_endpoint}/capi/v2/trade/order/{order_id}"
        session = await self._get_session()
        headers = self._get_auth_headers(f"/capi/v2/trade/order/{order_id}")
        
        params = {"symbol": symbol}
        
        async with session.get(url, params=params, headers=headers) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise RuntimeError(f"获取订单信息失败: status={resp.status} body={text[:500]}")
            return await resp.json()
