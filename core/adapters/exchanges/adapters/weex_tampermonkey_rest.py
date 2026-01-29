"""
WEEX油猴适配器 - REST模块

通过油猴脚本实现REST API等效功能。
所有操作都通过WebSocket发送命令到油猴脚本执行。
"""

import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any
from decimal import Decimal

from ..interface import ExchangeConfig
from ..models import (
    OrderData,
    PositionData,
    BalanceData,
    TickerData,
    OHLCVData,
    OrderBookData,
    TradeData,
    ExchangeInfo,
    OrderSide,
    OrderType,
    OrderStatus,
    PositionSide
)
from .weex_tampermonkey_base import WeexTampermonkeyBase


class WeexTampermonkeyRest:
    """
    WEEX油猴适配器REST模块
    
    通过油猴脚本实现交易所REST API的等效功能。
    """
    
    def __init__(self, base: WeexTampermonkeyBase, logger=None):
        """
        初始化REST模块
        
        Args:
            base: 基础模块实例
            logger: 日志记录器
        """
        self._base = base
        self.logger = logger
        
        # 缓存
        self._market_info: Dict[str, Any] = {}
        self._exchange_info: Optional[ExchangeInfo] = None
    
    async def initialize(self) -> bool:
        """
        初始化REST模块
        
        Returns:
            bool: 是否初始化成功
        """
        try:
            # 等待油猴脚本连接
            if not self._base.is_connected:
                if self.logger:
                    self.logger.info("等待油猴脚本连接...")
                connected = await self._base.wait_for_connection(timeout=60)
                if not connected:
                    if self.logger:
                        self.logger.error("等待油猴脚本连接超时")
                    return False
            
            if self.logger:
                self.logger.info("WEEX油猴REST模块初始化成功")
            return True
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"初始化REST模块失败: {e}")
            return False
    
    async def close(self) -> None:
        """关闭REST模块"""
        pass
    
    async def health_check(self) -> Dict[str, Any]:
        """
        健康检查
        
        Returns:
            健康状态信息
        """
        return {
            'api_accessible': self._base.is_connected,
            'connected_clients': len(self._base._clients),
            'current_symbol': self._base.get_current_symbol()
        }
    
    async def heartbeat(self) -> None:
        """心跳检测"""
        if self._base.is_connected:
            await self._base.send_command("heartbeat", timeout=5)
    
    # ==================== 市场数据接口 ====================
    
    async def get_exchange_info(self) -> ExchangeInfo:
        """获取交易所信息"""
        if self._exchange_info:
            return self._exchange_info
        
        self._exchange_info = ExchangeInfo(
            exchange_id="weex",
            name="WEEX",
            symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"],
            timeframes=["1m", "5m", "15m", "1h", "4h", "1d"],
            rate_limits={},
            features=["perpetual_trading", "leverage", "websocket"]
        )
        return self._exchange_info
    
    async def get_ticker(self, symbol: str) -> TickerData:
        """
        获取行情数据
        
        Args:
            symbol: 交易对符号
            
        Returns:
            行情数据
        """
        # 切换到目标交易对
        if symbol != self._base.get_current_symbol():
            await self.switch_symbol(symbol)
        
        # 获取价格
        result = await self._base.send_command("get_price")
        
        if result and result.get('result', {}).get('success'):
            price_data = result['result']
            price = Decimal(str(price_data.get('price', 0)))
            
            return TickerData(
                symbol=symbol,
                timestamp=datetime.now(),
                last=price,
                bid=price,  # 简化处理
                ask=price,  # 简化处理
                high=Decimal("0"),
                low=Decimal("0"),
                volume=Decimal("0"),
                change=Decimal("0"),
                percentage=Decimal("0")
            )
        
        raise Exception(f"获取{symbol}行情失败")
    
    async def get_tickers(self, symbols: Optional[List[str]] = None) -> List[TickerData]:
        """
        获取多个行情数据
        
        Args:
            symbols: 交易对符号列表
            
        Returns:
            行情数据列表
        """
        if not symbols:
            symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        
        tickers = []
        for symbol in symbols:
            try:
                ticker = await self.get_ticker(symbol)
                tickers.append(ticker)
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"获取{symbol}行情失败: {e}")
        
        return tickers
    
    async def get_orderbook(self, symbol: str, limit: Optional[int] = None) -> OrderBookData:
        """
        获取订单簿
        
        Args:
            symbol: 交易对符号
            limit: 深度限制
            
        Returns:
            订单簿数据
        """
        # 切换到目标交易对
        if symbol != self._base.get_current_symbol():
            await self.switch_symbol(symbol)
        
        # 获取K线数据（包含买卖价）
        result = await self._base.send_command("get_kline")
        
        if result and result.get('result', {}).get('success'):
            data = result['result'].get('data', {})
            bid_price = Decimal(str(data.get('bidPrice', 0)))
            ask_price = Decimal(str(data.get('askPrice', 0)))
            
            return OrderBookData(
                symbol=symbol,
                timestamp=datetime.now(),
                bids=[[bid_price, Decimal("1")]],  # 简化处理
                asks=[[ask_price, Decimal("1")]]   # 简化处理
            )
        
        raise Exception(f"获取{symbol}订单簿失败")
    
    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> List[OHLCVData]:
        """
        获取K线数据
        
        Args:
            symbol: 交易对符号
            timeframe: 时间框架
            since: 开始时间
            limit: 数据条数限制
            
        Returns:
            K线数据列表
        """
        # 切换到目标交易对
        if symbol != self._base.get_current_symbol():
            await self.switch_symbol(symbol)
        
        # 获取K线数据
        result = await self._base.send_command("get_kline")
        
        if result and result.get('result', {}).get('success'):
            data = result['result'].get('data', {})
            
            # 从页面数据构造K线
            current_price = Decimal(str(data.get('currentPrice', 0)))
            high_24h = Decimal(str(data.get('high24h', current_price)))
            low_24h = Decimal(str(data.get('low24h', current_price)))
            
            # 返回简化的K线数据
            return [OHLCVData(
                timestamp=datetime.now(),
                open=current_price,
                high=high_24h,
                low=low_24h,
                close=current_price,
                volume=Decimal(str(data.get('volume24h', '0').replace(',', '') or '0'))
            )]
        
        return []
    
    async def get_trades(
        self,
        symbol: str,
        since: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> List[TradeData]:
        """
        获取成交数据
        
        Args:
            symbol: 交易对符号
            since: 开始时间
            limit: 数据条数限制
            
        Returns:
            成交数据列表
        """
        # WEEX油猴脚本暂不支持获取成交记录
        return []
    
    # ==================== 账户接口 ====================
    
    async def get_balances(self) -> List[BalanceData]:
        """
        获取账户余额
        
        Returns:
            余额数据列表
        """
        result = await self._base.send_command("get_account")
        
        if result and result.get('result', {}).get('success'):
            data = result['result'].get('data', {})
            
            # 🔍 调试日志：打印原始返回数据
            if self.logger:
                self.logger.debug(f"[WEEX] get_balances 原始数据: {data}")
            
            # 解析余额数据
            balances = []
            
            # 可用余额
            available = data.get('availableBalance')
            if self.logger:
                self.logger.info(f"[WEEX] 可用余额原始值: '{available}'")
            
            if available is not None:
                try:
                    # 转为字符串处理
                    available_str = str(available) if available else '0'
                    # 清理字符串，只保留数字和小数点
                    available_str = available_str.replace(',', '').replace('USDT', '').replace('USDC', '').replace(' ', '').strip()
                    # 移除所有非数字字符（除了小数点和负号）
                    import re
                    available_str = re.sub(r'[^\d.\-]', '', available_str)
                    # 处理空字符串或只有小数点的情况
                    if not available_str or available_str == '.' or available_str == '-' or available_str == '-.':
                        available_str = '0'
                    # 处理多个小数点的情况
                    if available_str.count('.') > 1:
                        parts = available_str.split('.')
                        available_str = parts[0] + '.' + ''.join(parts[1:])
                    
                    available_decimal = Decimal(available_str)
                except Exception as e:
                    if self.logger:
                        self.logger.warning(f"解析余额失败: '{available}', 错误: {e}")
                    available_decimal = Decimal("0")
                
                balances.append(BalanceData(
                    currency="USDT",
                    free=available_decimal,
                    used=Decimal("0"),
                    total=available_decimal,
                    usd_value=available_decimal,
                    timestamp=datetime.now(),
                    raw_data={"available": str(available)}
                ))
            
            return balances
        
        return []
    
    async def get_positions(self, symbols: Optional[List[str]] = None) -> List[PositionData]:
        """
        获取持仓信息
        
        Args:
            symbols: 交易对符号列表
            
        Returns:
            持仓数据列表
        """
        result = await self._base.send_command("get_account")
        
        if result and result.get('result', {}).get('success'):
            data = result['result'].get('data', {})
            positions = []
            
            # 🔍 调试日志：打印原始返回数据
            if self.logger:
                self.logger.debug(f"[WEEX] get_account 原始数据: {data}")
            
            # 解析持仓数据
            position_data = data.get('position', {})
            if position_data:
                # 🔍 调试日志：打印持仓原始数据
                if self.logger:
                    self.logger.info(f"[WEEX] 持仓原始数据: {position_data}")
                
                size_str = position_data.get('size', '0')
                size = Decimal(str(size_str).replace(',', '')) if size_str else Decimal("0")
                
                if size != 0:
                    entry_price_str = position_data.get('entryPrice', '0')
                    entry_price = Decimal(str(entry_price_str).replace(',', '')) if entry_price_str else Decimal("0")
                    
                    # 支持 unrealizedPnl 和 pnl 两种字段名（兼容性）
                    unrealized_pnl_str = position_data.get('unrealizedPnl') or position_data.get('pnl', '0')
                    unrealized_pnl = Decimal(str(unrealized_pnl_str).replace(',', '')) if unrealized_pnl_str else Decimal("0")
                    
                    # 从油猴脚本返回的 side 字段判断方向
                    side_str = position_data.get('side', '').lower()
                    if side_str == 'long':
                        position_side = PositionSide.LONG
                    elif side_str == 'short':
                        position_side = PositionSide.SHORT
                    else:
                        # 兼容旧版：如果 side 字段不是 long/short，用 size 的正负判断
                        position_side = PositionSide.LONG if size > 0 else PositionSide.SHORT
                    
                    # 🔍 调试日志：打印解析后的数据
                    if self.logger:
                        self.logger.info(f"[WEEX] 持仓解析: side={position_side.value}, size={size}, entry_price={entry_price}, unrealized_pnl={unrealized_pnl}")
                    
                    positions.append(PositionData(
                        symbol=self._base.get_current_symbol(),
                        side=position_side,
                        size=abs(size),
                        entry_price=entry_price,
                        mark_price=Decimal("0"),
                        liquidation_price=Decimal("0"),
                        unrealized_pnl=unrealized_pnl,
                        realized_pnl=Decimal("0"),
                        current_price=entry_price,  # 使用入场价作为当前价格
                        percentage=Decimal("0"),
                        margin=Decimal("0"),
                        leverage=20,  # 默认杠杆
                        margin_mode="cross",
                        timestamp=datetime.now(),
                        raw_data=position_data
                    ))
            
            return positions
        
        return []
    
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
        """
        创建订单
        
        Args:
            symbol: 交易对符号
            side: 订单方向
            order_type: 订单类型
            amount: 数量
            price: 价格（限价单必需）
            params: 额外参数
            
        Returns:
            订单数据
        """
        # 切换到目标交易对
        if symbol != self._base.get_current_symbol():
            await self.switch_symbol(symbol)
        
        # 构建下单参数
        order_params = {
            "type": "limit" if order_type == OrderType.LIMIT else "market",
            "side": "buy" if side == OrderSide.BUY else "sell",
            "quantity": int(amount),  # WEEX使用张数
        }
        
        if price and order_type == OrderType.LIMIT:
            order_params["price"] = float(price)
        
        # 🔥 下单前随机延迟1-3秒，避免触发风控
        import random
        delay = random.uniform(1, 3)
        self.logger.debug(f"下单前等待 {delay:.2f} 秒...")
        await asyncio.sleep(delay)
        
        # 发送下单命令
        result = await self._base.send_command("place_order", order_params)
        
        if result and result.get('result', {}).get('success'):
            # 生成订单ID
            import uuid
            order_id = str(uuid.uuid4())
            
            return OrderData(
                id=order_id,
                client_id=order_id,
                symbol=symbol,
                side=side,
                type=order_type,
                price=price or Decimal("0"),
                amount=amount,
                filled=Decimal("0"),
                remaining=amount,
                cost=Decimal("0"),
                average=None,
                status=OrderStatus.OPEN,
                timestamp=datetime.now(),
                updated=None,
                fee=None,
                trades=[],
                params={},
                raw_data={}
            )
        
        error_msg = result.get('result', {}).get('error', '下单失败') if result else '下单失败'
        raise Exception(f"创建订单失败: {error_msg}")
    
    async def cancel_order(self, order_id: str, symbol: str) -> OrderData:
        """
        取消订单
        
        Args:
            order_id: 订单ID
            symbol: 交易对符号
            
        Returns:
            订单数据
        """
        result = await self._base.send_command("cancel_order", {"order_id": order_id})
        
        if result and result.get('result', {}).get('success'):
            return OrderData(
                id=order_id,
                client_id=order_id,
                symbol=symbol,
                side=OrderSide.BUY,
                type=OrderType.LIMIT,
                price=Decimal("0"),
                amount=Decimal("0"),
                filled=Decimal("0"),
                remaining=Decimal("0"),
                cost=Decimal("0"),
                average=None,
                status=OrderStatus.CANCELLED,
                timestamp=datetime.now(),
                updated=None,
                fee=None,
                trades=[],
                params={},
                raw_data={}
            )
        
        raise Exception("取消订单失败")
    
    async def cancel_all_orders(self, symbol: Optional[str] = None) -> List[OrderData]:
        """
        取消所有订单
        
        Args:
            symbol: 交易对符号
            
        Returns:
            被取消的订单列表
        """
        result = await self._base.send_command("cancel_all")
        
        if result and result.get('result', {}).get('success'):
            return []  # 返回空列表表示成功
        
        raise Exception("取消所有订单失败")
    
    async def get_order(self, order_id: str, symbol: str) -> OrderData:
        """
        获取订单信息
        
        Args:
            order_id: 订单ID
            symbol: 交易对符号
            
        Returns:
            订单数据
        """
        # WEEX油猴脚本暂不支持查询单个订单
        raise NotImplementedError("WEEX油猴适配器暂不支持查询单个订单")
    
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[OrderData]:
        """
        获取开放订单
        
        Args:
            symbol: 交易对符号
            
        Returns:
            开放订单列表
        """
        result = await self._base.send_command("get_orders")
        
        if result and result.get('result', {}).get('success'):
            orders_data = result['result'].get('orders', [])
            orders = []
            
            for order_data in orders_data:
                try:
                    # 安全解析价格和数量
                    import re
                    price_str = str(order_data.get('price', '0'))
                    price_str = re.sub(r'[^\d.\-]', '', price_str) or '0'
                    quantity_str = str(order_data.get('quantity', '0'))
                    quantity_str = re.sub(r'[^\d.\-]', '', quantity_str) or '0'
                    
                    orders.append(OrderData(
                        id=order_data.get('id', ''),
                        client_id=order_data.get('id', ''),
                        symbol=symbol or self._base.get_current_symbol(),
                        side=OrderSide.BUY if order_data.get('side') == 'buy' else OrderSide.SELL,
                        type=OrderType.LIMIT if order_data.get('type') == 'limit' else OrderType.MARKET,
                        price=Decimal(price_str),
                        amount=Decimal(quantity_str),
                        filled=Decimal("0"),
                        remaining=Decimal(quantity_str),
                        cost=Decimal("0"),
                        average=None,
                        status=OrderStatus.OPEN,
                        timestamp=datetime.now(),
                        updated=None,
                        fee=None,
                        trades=[],
                        params={},
                        raw_data=order_data
                    ))
                except Exception as e:
                    self.logger.warning(f"解析订单失败: {order_data}, 错误: {e}")
            
            return orders
        
        return []
    
    async def get_order_history(
        self,
        symbol: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> List[OrderData]:
        """
        获取历史订单
        
        Args:
            symbol: 交易对符号
            since: 开始时间
            limit: 数据条数限制
            
        Returns:
            历史订单列表
        """
        # WEEX油猴脚本暂不支持查询历史订单
        return []
    
    # ==================== 设置接口 ====================
    
    async def set_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """
        设置杠杆倍数
        
        Args:
            symbol: 交易对符号
            leverage: 杠杆倍数
            
        Returns:
            设置结果
        """
        # WEEX需要在网页上手动设置杠杆
        if self.logger:
            self.logger.warning(f"WEEX杠杆需要在网页上手动设置: {leverage}x")
        return {"success": True, "leverage": leverage}
    
    async def set_margin_mode(self, symbol: str, margin_mode: str) -> Dict[str, Any]:
        """
        设置保证金模式
        
        Args:
            symbol: 交易对符号
            margin_mode: 保证金模式
            
        Returns:
            设置结果
        """
        # WEEX需要在网页上手动设置保证金模式
        if self.logger:
            self.logger.warning(f"WEEX保证金模式需要在网页上手动设置: {margin_mode}")
        return {"success": True, "margin_mode": margin_mode}
    
    # ==================== 辅助方法 ====================
    
    async def switch_symbol(self, symbol: str) -> bool:
        """
        切换交易对
        
        Args:
            symbol: 目标交易对
            
        Returns:
            bool: 是否切换成功
        """
        result = await self._base.send_command("switch_symbol", {"symbol": symbol})
        
        if result and result.get('result', {}).get('success'):
            self._base.set_current_symbol(symbol)
            return True
        
        return False
    
    async def close_position(self, symbol: str, order_type: str = "market") -> bool:
        """
        平仓
        
        Args:
            symbol: 交易对符号
            order_type: 订单类型
            
        Returns:
            bool: 是否平仓成功
        """
        result = await self._base.send_command("close_position", {
            "symbol": symbol,
            "type": order_type
        })
        
        return result and result.get('result', {}).get('success', False)
