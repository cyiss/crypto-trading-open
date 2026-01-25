"""
WEEX 交易所适配器 - WebSocket 模块

本模块职责：
- 管理 WebSocket 连接（公有和私有频道）
- 处理 WebSocket 认证
- 订阅和推送数据处理
- Ping/Pong 心跳管理
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Callable, List

import aiohttp

from .weex_base import WeexBase, datetime_to_unix_ms


class WeexWebSocket(WeexBase):
    """WEEX WebSocket 客户端"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化 WEEX WebSocket 客户端
        
        Args:
            config: 配置字典
        """
        super().__init__(config)
        self.logger = logging.getLogger(f"WeexWebSocket.{config.get('exchange_id', 'weex')}")
        
        self._ws_public: Optional[aiohttp.ClientWebSocketResponse] = None
        self._ws_private: Optional[aiohttp.ClientWebSocketResponse] = None
        self._session: Optional[aiohttp.ClientSession] = None
        
        # 订阅管理
        self._subscriptions: Dict[str, List[Callable]] = {}
        self._private_subscriptions: Dict[str, List[Callable]] = {}
        
        # 心跳管理
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._reconnect_task: Optional[asyncio.Task] = None
        
        # 连接状态
        self._connected = False
        self._authenticated = False
        
        # 消息处理器
        self._message_handlers: Dict[str, Callable] = {}

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取/懒加载 aiohttp 会话"""
        if self._session and not self._session.closed:
            return self._session
        self._session = aiohttp.ClientSession()
        return self._session

    def _generate_auth_headers(self) -> Dict[str, str]:
        """
        生成 WebSocket 认证头
        
        Returns:
            认证头字典
        """
        timestamp = datetime_to_unix_ms(datetime.now(timezone.utc))
        request_path = "/v2/ws/private"
        
        import hmac
        import hashlib
        import base64
        
        message = str(timestamp) + request_path
        signature = hmac.new(
            self.api_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).digest()
        signature_b64 = base64.b64encode(signature).decode()
        
        return {
            "User-Agent": "crypto-trading-weex-adapter/1.0",
            "ACCESS-KEY": self.api_key,
            "ACCESS-SIGN": signature_b64,
            "ACCESS-TIMESTAMP": str(timestamp),
            "ACCESS-PASSPHRASE": self.api_passphrase or "",
        }

    async def connect_public(self) -> bool:
        """
        连接到公有频道
        
        Returns:
            连接是否成功
        """
        try:
            session = await self._get_session()
            url = f"{self.ws_endpoint}/v2/ws/public"
            
            self._ws_public = await session.ws_connect(
                url,
                headers={"User-Agent": "crypto-trading-weex-adapter/1.0"},
                heartbeat=30
            )
            
            self.logger.info(f"连接到 WEEX 公有频道: {url}")
            
            # 启动消息接收循环
            asyncio.create_task(self._handle_public_messages())
            
            return True
        except Exception as e:
            self.logger.error(f"连接公有频道失败: {e}")
            return False

    async def connect_private(self) -> bool:
        """
        连接到私有频道
        
        Returns:
            连接是否成功
        """
        try:
            session = await self._get_session()
            url = f"{self.ws_endpoint}/v2/ws/private"
            headers = self._generate_auth_headers()
            
            self._ws_private = await session.ws_connect(
                url,
                headers=headers,
                heartbeat=30
            )
            
            self.logger.info(f"连接到 WEEX 私有频道: {url}")
            self._authenticated = True
            
            # 启动消息接收循环
            asyncio.create_task(self._handle_private_messages())
            
            return True
        except Exception as e:
            self.logger.error(f"连接私有频道失败: {e}")
            return False

    async def subscribe(self, channel: str, callback: Optional[Callable] = None) -> bool:
        """
        订阅公有频道
        
        Args:
            channel: 频道名称
            callback: 消息回调函数
            
        Returns:
            订阅是否成功
        """
        if not self._ws_public:
            self.logger.error("公有频道未连接")
            return False
        
        try:
            message = {
                "event": "subscribe",
                "channel": channel
            }
            
            await self._ws_public.send_json(message)
            
            # 注册回调
            if callback:
                if channel not in self._subscriptions:
                    self._subscriptions[channel] = []
                self._subscriptions[channel].append(callback)
            
            self.logger.debug(f"订阅公有频道: {channel}")
            return True
        except Exception as e:
            self.logger.error(f"订阅公有频道失败: {channel} - {e}")
            return False

    async def subscribe_private(self, channel: str, callback: Optional[Callable] = None) -> bool:
        """
        订阅私有频道
        
        Args:
            channel: 频道名称
            callback: 消息回调函数
            
        Returns:
            订阅是否成功
        """
        if not self._ws_private:
            self.logger.error("私有频道未连接")
            return False
        
        try:
            message = {
                "event": "subscribe",
                "channel": channel
            }
            
            await self._ws_private.send_json(message)
            
            # 注册回调
            if callback:
                if channel not in self._private_subscriptions:
                    self._private_subscriptions[channel] = []
                self._private_subscriptions[channel].append(callback)
            
            self.logger.debug(f"订阅私有频道: {channel}")
            return True
        except Exception as e:
            self.logger.error(f"订阅私有频道失败: {channel} - {e}")
            return False

    async def unsubscribe(self, channel: str) -> bool:
        """
        取消订阅公有频道
        
        Args:
            channel: 频道名称
            
        Returns:
            取消订阅是否成功
        """
        if not self._ws_public:
            return False
        
        try:
            message = {
                "event": "unsubscribe",
                "channel": channel
            }
            
            await self._ws_public.send_json(message)
            
            # 移除回调
            if channel in self._subscriptions:
                del self._subscriptions[channel]
            
            self.logger.debug(f"取消订阅公有频道: {channel}")
            return True
        except Exception as e:
            self.logger.error(f"取消订阅公有频道失败: {channel} - {e}")
            return False

    async def unsubscribe_private(self, channel: str) -> bool:
        """
        取消订阅私有频道
        
        Args:
            channel: 频道名称
            
        Returns:
            取消订阅是否成功
        """
        if not self._ws_private:
            return False
        
        try:
            message = {
                "event": "unsubscribe",
                "channel": channel
            }
            
            await self._ws_private.send_json(message)
            
            # 移除回调
            if channel in self._private_subscriptions:
                del self._private_subscriptions[channel]
            
            self.logger.debug(f"取消订阅私有频道: {channel}")
            return True
        except Exception as e:
            self.logger.error(f"取消订阅私有频道失败: {channel} - {e}")
            return False

    async def _handle_public_messages(self) -> None:
        """处理公有频道消息"""
        if not self._ws_public:
            return
        
        try:
            async for msg in self._ws_public:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        await self._process_message(data, is_private=False)
                    except json.JSONDecodeError as e:
                        self.logger.error(f"JSON 解析失败: {e}")
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    self.logger.error(f"WebSocket 错误: {msg}")
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    self.logger.info("公有频道连接已关闭")
                    break
        except Exception as e:
            self.logger.error(f"处理公有频道消息失败: {e}")

    async def _handle_private_messages(self) -> None:
        """处理私有频道消息"""
        if not self._ws_private:
            return
        
        try:
            async for msg in self._ws_private:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        await self._process_message(data, is_private=True)
                    except json.JSONDecodeError as e:
                        self.logger.error(f"JSON 解析失败: {e}")
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    self.logger.error(f"WebSocket 错误: {msg}")
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    self.logger.info("私有频道连接已关闭")
                    break
        except Exception as e:
            self.logger.error(f"处理私有频道消息失败: {e}")

    async def _process_message(self, data: Dict[str, Any], is_private: bool = False) -> None:
        """
        处理 WebSocket 消息
        
        Args:
            data: 消息数据
            is_private: 是否为私有频道消息
        """
        event = data.get("event")
        
        # 处理 Ping 消息
        if event == "ping":
            ws = self._ws_private if is_private else self._ws_public
            if ws:
                pong_msg = {
                    "event": "pong",
                    "time": data.get("time")
                }
                try:
                    await ws.send_json(pong_msg)
                except Exception as e:
                    self.logger.error(f"发送 Pong 消息失败: {e}")
            return
        
        # 处理订阅确认
        if event == "subscribe":
            channel = data.get("channel")
            self.logger.debug(f"订阅确认: {channel}")
            return
        
        # 处理取消订阅确认
        if event == "unsubscribe":
            channel = data.get("channel")
            self.logger.debug(f"取消订阅确认: {channel}")
            return
        
        # 处理数据消息
        channel = data.get("channel")
        if channel:
            subscriptions = self._private_subscriptions if is_private else self._subscriptions
            callbacks = subscriptions.get(channel, [])
            
            for callback in callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(data)
                    else:
                        callback(data)
                except Exception as e:
                    self.logger.error(f"处理回调失败: {e}")

    async def disconnect(self) -> None:
        """断开 WebSocket 连接"""
        if self._ws_public:
            await self._ws_public.close()
            self._ws_public = None
        
        if self._ws_private:
            await self._ws_private.close()
            self._ws_private = None
        
        if self._session:
            await self._session.close()
            self._session = None
        
        self._connected = False
        self._authenticated = False
        self.logger.info("WebSocket 连接已断开")
