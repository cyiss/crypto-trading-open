"""
WEEX油猴适配器 - 主适配器类

通过WebSocket与浏览器中的油猴脚本通信，实现WEEX交易所的交易功能。
这是一个特殊的适配器，不直接调用交易所API，而是通过油猴脚本在浏览器中执行操作。

使用方法：
1. 启动此适配器（会启动WebSocket服务器）
2. 在浏览器中打开WEEX交易页面
3. 油猴脚本自动连接到WebSocket服务器
4. 通过适配器接口进行交易操作
"""

import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from decimal import Decimal

from ....logging import get_logger

from ..adapter import ExchangeAdapter
from ..interface import ExchangeConfig, ExchangeStatus
from ..models import (
    ExchangeType,
    OrderSide,
    OrderType,
    OrderData,
    PositionData,
    BalanceData,
    TickerData,
    OHLCVData,
    OrderBookData,
    TradeData,
    ExchangeInfo
)

from .weex_tampermonkey_base import WeexTampermonkeyBase
from .weex_tampermonkey_rest import WeexTampermonkeyRest


class WeexTampermonkeyAdapter(ExchangeAdapter):
    """
    WEEX油猴适配器
    
    通过油猴脚本在浏览器中执行WEEX交易操作。
    实现了ExchangeInterface接口，可以与现有的网格交易系统无缝集成。
    """
    
    def __init__(self, config: ExchangeConfig, event_bus=None):
        """
        初始化适配器
        
        Args:
            config: 交易所配置
            event_bus: 事件总线（可选）
        """
        super().__init__(config, event_bus)
        
        # 初始化各个模块
        self._base = WeexTampermonkeyBase(config, self.logger)
        self._rest = WeexTampermonkeyRest(self._base, self.logger)
        
        # 连接状态
        self._connected = False
        self._authenticated = False
        
        # 符号映射
        self._symbol_mapping = getattr(config, 'symbol_mapping', {})
        
        # 缓存
        self._market_info: Dict[str, Any] = {}
        
        if self.logger:
            self.logger.info(f"📝 WeexTampermonkeyAdapter 初始化完成")
    
    # ==================== 生命周期管理 ====================
    
    async def _do_connect(self) -> bool:
        """
        连接实现
        
        启动WebSocket服务器并等待油猴脚本连接。
        """
        try:
            # 启动WebSocket服务器
            server_started = await self._base.start_server()
            if not server_started:
                self.logger.error("❌ 启动WebSocket服务器失败")
                return False
            
            self.logger.info("✅ WEEX油猴WebSocket服务器已启动")
            self.logger.info(f"📡 等待油猴脚本连接: ws://{self._base.ws_host}:{self._base.ws_port}")
            self.logger.info("请在浏览器中执行: weexBot.connect('ws://localhost:8766')")
            
            # 等待油猴脚本连接
            wait_timeout = self.config.extra_params.get('connection_timeout', 300)
            connected = await self._base.wait_for_connection(timeout=wait_timeout)
            
            if not connected:
                self.logger.warning("⚠️ 等待油猴脚本连接超时，服务器将继续运行")
                # 不返回False，让服务器继续运行等待连接
            else:
                self.logger.info("✅ 油猴脚本已连接")
            
            # 初始化REST模块
            await self._rest.initialize()
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ WEEX连接失败: {str(e)}")
            return False
    
    async def _do_disconnect(self) -> None:
        """断开连接实现"""
        try:
            await self._base.stop_server()
            self.logger.info("✅ WEEX连接已断开")
        except Exception as e:
            self.logger.error(f"❌ 断开WEEX连接失败: {str(e)}")
    
    async def _do_authenticate(self) -> bool:
        """
        认证实现
        
        WEEX通过浏览器登录，无需API认证。
        """
        try:
            # 检查油猴脚本是否连接
            if not self._base.is_connected:
                self.logger.warning("⚠️ 油猴脚本未连接，无法认证")
                return False
            
            # 尝试获取账户信息验证登录状态
            result = await self._base.send_command("get_account")
            
            if result and result.get('result', {}).get('success'):
                self.logger.info("✅ WEEX认证成功（浏览器已登录）")
                return True
            else:
                self.logger.warning("⚠️ WEEX未登录，请在浏览器中登录WEEX账户")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ WEEX认证失败: {str(e)}")
            return False
    
    async def _do_health_check(self) -> Dict[str, Any]:
        """健康检查实现"""
        try:
            return await self._rest.health_check()
        except Exception as e:
            return {
                'api_accessible': False,
                'error': str(e)
            }
    
    async def _do_heartbeat(self) -> None:
        """心跳实现"""
        try:
            await self._rest.heartbeat()
        except Exception as e:
            self.logger.error(f"❌ WEEX心跳失败: {str(e)}")
    
    # ==================== 市场数据接口 ====================
    
    async def get_exchange_info(self) -> ExchangeInfo:
        """获取交易所信息"""
        return await self._rest.get_exchange_info()
    
    async def get_ticker(self, symbol: str) -> TickerData:
        """获取行情数据"""
        return await self._rest.get_ticker(symbol)
    
    async def get_tickers(self, symbols: Optional[List[str]] = None) -> List[TickerData]:
        """获取多个行情数据"""
        return await self._rest.get_tickers(symbols)
    
    async def get_orderbook(self, symbol: str, limit: Optional[int] = None) -> OrderBookData:
        """获取订单簿"""
        return await self._rest.get_orderbook(symbol, limit)
    
    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> List[OHLCVData]:
        """获取K线数据"""
        return await self._rest.get_ohlcv(symbol, timeframe, since, limit)
    
    async def get_trades(
        self,
        symbol: str,
        since: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> List[TradeData]:
        """获取成交数据"""
        return await self._rest.get_trades(symbol, since, limit)
    
    # ==================== 账户接口 ====================
    
    async def get_balances(self) -> List[BalanceData]:
        """获取账户余额"""
        return await self._rest.get_balances()
    
    async def get_positions(self, symbols: Optional[List[str]] = None) -> List[PositionData]:
        """获取持仓信息"""
        return await self._rest.get_positions(symbols)
    
    # ==================== 交易接口 ====================
    
    async def create_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        amount: Decimal,
        price: Optional[Decimal] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> OrderData:
        """创建订单"""
        order = await self._rest.create_order(symbol, side, order_type, amount, price, params)
        
        # 触发订单创建事件
        await self._handle_order_update(order)
        
        return order
    
    async def cancel_order(self, order_id: str, symbol: str) -> OrderData:
        """取消订单"""
        order = await self._rest.cancel_order(order_id, symbol)
        
        # 触发订单更新事件
        await self._handle_order_update(order)
        
        return order
    
    async def cancel_all_orders(self, symbol: Optional[str] = None) -> List[OrderData]:
        """取消所有订单"""
        orders = await self._rest.cancel_all_orders(symbol)
        
        # 触发订单更新事件
        for order in orders:
            await self._handle_order_update(order)
        
        return orders
    
    async def get_order(self, order_id: str, symbol: str) -> OrderData:
        """获取订单信息"""
        return await self._rest.get_order(order_id, symbol)
    
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[OrderData]:
        """获取开放订单"""
        return await self._rest.get_open_orders(symbol)
    
    async def get_order_history(
        self,
        symbol: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> List[OrderData]:
        """获取历史订单"""
        return await self._rest.get_order_history(symbol, since, limit)
    
    # ==================== 设置接口 ====================
    
    async def set_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """设置杠杆倍数"""
        return await self._rest.set_leverage(symbol, leverage)
    
    async def set_margin_mode(self, symbol: str, margin_mode: str) -> Dict[str, Any]:
        """设置保证金模式"""
        return await self._rest.set_margin_mode(symbol, margin_mode)
    
    # ==================== 订阅接口 ====================
    
    async def subscribe_ticker(self, symbol: str, callback: Callable[[TickerData], None]) -> None:
        """订阅行情数据流"""
        # WEEX油猴适配器使用轮询模式
        self.logger.info(f"📡 订阅行情: {symbol} (轮询模式)")
        asyncio.create_task(self._poll_ticker(symbol, callback))
    
    async def subscribe_orderbook(self, symbol: str, callback: Callable[[OrderBookData], None]) -> None:
        """订阅订单簿数据流"""
        self.logger.info(f"📡 订阅订单簿: {symbol} (轮询模式)")
        asyncio.create_task(self._poll_orderbook(symbol, callback))
    
    async def subscribe_trades(self, symbol: str, callback: Callable[[TradeData], None]) -> None:
        """订阅成交数据流"""
        self.logger.warning(f"⚠️ WEEX油猴适配器暂不支持订阅成交数据")
    
    async def subscribe_user_data(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """订阅用户数据流"""
        self.logger.info(f"📡 订阅用户数据 (轮询模式)")
        asyncio.create_task(self._poll_user_data(callback))
    
    async def unsubscribe(self, symbol: Optional[str] = None) -> None:
        """取消订阅"""
        # 轮询模式下通过标志位控制
        pass
    
    # ==================== 轮询方法 ====================
    
    async def _poll_ticker(self, symbol: str, callback: Callable[[TickerData], None]) -> None:
        """轮询行情数据"""
        poll_interval = self.config.extra_params.get('poll_interval', 1.0)
        
        while self._base.is_connected:
            try:
                ticker = await self.get_ticker(symbol)
                callback(ticker)
            except Exception as e:
                self.logger.error(f"轮询行情失败: {e}")
            
            await asyncio.sleep(poll_interval)
    
    async def _poll_orderbook(self, symbol: str, callback: Callable[[OrderBookData], None]) -> None:
        """轮询订单簿数据"""
        poll_interval = self.config.extra_params.get('poll_interval', 1.0)
        
        while self._base.is_connected:
            try:
                orderbook = await self.get_orderbook(symbol)
                callback(orderbook)
            except Exception as e:
                self.logger.error(f"轮询订单簿失败: {e}")
            
            await asyncio.sleep(poll_interval)
    
    async def _poll_user_data(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """轮询用户数据"""
        poll_interval = self.config.extra_params.get('user_data_poll_interval', 5.0)
        
        while self._base.is_connected:
            try:
                # 获取余额
                balances = await self.get_balances()
                
                # 获取持仓
                positions = await self.get_positions()
                
                # 获取订单
                orders = await self.get_open_orders()
                
                callback({
                    'type': 'user_data',
                    'balances': [b.__dict__ for b in balances],
                    'positions': [p.__dict__ for p in positions],
                    'orders': [o.__dict__ for o in orders]
                })
                
            except Exception as e:
                self.logger.error(f"轮询用户数据失败: {e}")
            
            await asyncio.sleep(poll_interval)
    
    # ==================== 辅助方法 ====================
    
    async def switch_symbol(self, symbol: str) -> bool:
        """切换交易对"""
        return await self._rest.switch_symbol(symbol)
    
    async def close_position(self, symbol: str, order_type: str = "market") -> bool:
        """平仓"""
        return await self._rest.close_position(symbol, order_type)
    
    def get_current_symbol(self) -> str:
        """获取当前交易对"""
        return self._base.get_current_symbol()
    
    def is_browser_connected(self) -> bool:
        """检查浏览器是否已连接"""
        return self._base.is_connected
    
    async def _handle_order_update(self, order: OrderData) -> None:
        """处理订单更新事件"""
        # 子类可以重写此方法来处理订单事件
        pass
