#!/usr/bin/env python3
"""
WEEX 统一交易服务器

集成以下功能模块：
1. 网格交易系统 (Grid Trading)
2. 刷量交易系统 (Volume Maker)
3. 套利监控与执行系统 (Arbitrage Monitor)
4. 网格波动率扫描器 (Volatility Scanner)
5. 价格提醒系统 (Price Alert)

通过WebSocket与浏览器油猴脚本通信，执行实际交易操作。
"""

import asyncio
import json
import logging
import uuid
import yaml
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from collections import deque
import time

try:
    import websockets
except ImportError:
    print("正在安装 websockets 库...")
    import subprocess
    subprocess.run(["pip", "install", "websockets"], check=True)
    import websockets

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# 数据模型
# ============================================================================

class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    LIMIT = "limit"
    MARKET = "market"


class GridType(Enum):
    NORMAL = "normal"           # 普通网格
    FOLLOW_LONG = "follow_long"  # 跟随做多
    FOLLOW_SHORT = "follow_short"  # 跟随做空


@dataclass
class Order:
    """订单数据"""
    id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    price: Decimal
    quantity: Decimal
    status: str = "pending"
    filled_quantity: Decimal = Decimal("0")
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class Position:
    """持仓数据"""
    symbol: str
    side: str
    quantity: Decimal
    entry_price: Decimal
    unrealized_pnl: Decimal = Decimal("0")


@dataclass
class GridLevel:
    """网格层级"""
    price: Decimal
    buy_order_id: Optional[str] = None
    sell_order_id: Optional[str] = None
    is_filled: bool = False


@dataclass
class MarketData:
    """市场数据"""
    symbol: str
    current_price: Decimal
    bid_price: Decimal
    ask_price: Decimal
    high_24h: Decimal
    low_24h: Decimal
    volume_24h: Decimal
    funding_rate: Decimal
    timestamp: datetime


# ============================================================================
# WebSocket 通信层
# ============================================================================

class WeexWebSocketServer:
    """WEEX WebSocket 服务器"""

    def __init__(self, host: str = "0.0.0.0", port: int = 8766):
        self.host = host
        self.port = port
        self.clients = set()
        self.pending_requests: Dict[str, asyncio.Future] = {}
        self.message_handlers: List[Callable] = []
        self._running = False

    def add_message_handler(self, handler: Callable):
        """添加消息处理器"""
        self.message_handlers.append(handler)

    async def register(self, websocket):
        """注册客户端"""
        self.clients.add(websocket)
        logger.info(f"客户端已连接，当前连接数: {len(self.clients)}")

    async def unregister(self, websocket):
        """注销客户端"""
        self.clients.discard(websocket)
        logger.info(f"客户端已断开，当前连接数: {len(self.clients)}")

    async def send_command(self, action: str, params: Dict = None, timeout: float = 10.0) -> Optional[Dict]:
        """发送命令并等待响应"""
        if not self.clients:
            logger.warning("没有连接的客户端")
            return None

        request_id = str(uuid.uuid4())
        command = {
            "id": request_id,
            "action": action,
            "params": params or {},
            "timestamp": datetime.now().isoformat()
        }

        # 创建Future等待响应
        future = asyncio.get_event_loop().create_future()
        self.pending_requests[request_id] = future

        # 发送命令
        message = json.dumps(command)
        await asyncio.gather(
            *[client.send(message) for client in self.clients],
            return_exceptions=True
        )

        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            logger.warning(f"命令 {action} 响应超时")
            return None
        finally:
            self.pending_requests.pop(request_id, None)

    async def handle_message(self, websocket, message: str):
        """处理消息"""
        try:
            data = json.loads(message)
            msg_type = data.get('type', 'unknown')

            if msg_type == 'connected':
                logger.info("油猴脚本已连接")
            elif msg_type == 'response':
                request_id = data.get('id')
                if request_id and request_id in self.pending_requests:
                    self.pending_requests[request_id].set_result(data)
            elif msg_type == 'event':
                # 处理事件（如价格更新、订单成交等）
                for handler in self.message_handlers:
                    await handler(data)
            else:
                logger.debug(f"收到消息: {data}")

        except json.JSONDecodeError:
            logger.error(f"无法解析消息: {message}")

    async def handler(self, websocket):
        """WebSocket连接处理器"""
        await self.register(websocket)
        try:
            async for message in websocket:
                await self.handle_message(websocket, message)
        except websockets.exceptions.ConnectionClosed:
            logger.info("连接已关闭")
        finally:
            await self.unregister(websocket)

    async def start(self):
        """启动服务器"""
        self._running = True
        logger.info(f"启动WebSocket服务器: ws://{self.host}:{self.port}")
        async with websockets.serve(self.handler, self.host, self.port):
            while self._running:
                await asyncio.sleep(1)

    def stop(self):
        """停止服务器"""
        self._running = False


# ============================================================================
# 统一交易控制器
# ============================================================================

class WeexController:
    """WEEX 统一交易控制器"""

    def __init__(self, ws_server: WeexWebSocketServer):
        self.ws = ws_server
        self.current_symbol = "BTCUSDT"
        self.market_data: Dict[str, MarketData] = {}
        self.positions: Dict[str, Position] = {}
        self.orders: Dict[str, Order] = {}

    async def get_current_price(self) -> Optional[Decimal]:
        """获取当前价格"""
        result = await self.ws.send_command("get_price")
        if result and result.get('result', {}).get('success'):
            return Decimal(str(result['result']['price']))
        return None

    async def get_market_data(self) -> Optional[MarketData]:
        """获取市场数据"""
        result = await self.ws.send_command("get_kline")
        if result and result.get('result', {}).get('success'):
            data = result['result']['data']
            return MarketData(
                symbol=self.current_symbol,
                current_price=Decimal(str(data.get('currentPrice', 0))),
                bid_price=Decimal(str(data.get('bidPrice', 0))),
                ask_price=Decimal(str(data.get('askPrice', 0))),
                high_24h=Decimal(str(data.get('high24h', 0))),
                low_24h=Decimal(str(data.get('low24h', 0))),
                volume_24h=Decimal(str(data.get('volume24h', '0').replace(',', ''))),
                funding_rate=Decimal(str(data.get('fundingRate', '0').replace('%', ''))),
                timestamp=datetime.now()
            )
        return None

    async def get_account_status(self) -> Optional[Dict]:
        """获取账户状态"""
        result = await self.ws.send_command("get_account")
        if result and result.get('result', {}).get('success'):
            return result['result']['data']
        return None

    async def place_order(self, side: OrderSide, order_type: OrderType,
                          quantity: int, price: Optional[Decimal] = None) -> Optional[str]:
        """下单"""
        params = {
            "type": order_type.value,
            "side": side.value,
            "quantity": quantity
        }
        if price and order_type == OrderType.LIMIT:
            params["price"] = float(price)

        result = await self.ws.send_command("place_order", params)
        if result and result.get('result', {}).get('success'):
            order_id = str(uuid.uuid4())
            self.orders[order_id] = Order(
                id=order_id,
                symbol=self.current_symbol,
                side=side,
                order_type=order_type,
                price=price or Decimal("0"),
                quantity=Decimal(str(quantity))
            )
            return order_id
        return None

    async def cancel_order(self, order_id: str) -> bool:
        """撤单"""
        result = await self.ws.send_command("cancel_order", {"order_id": order_id})
        if result and result.get('result', {}).get('success'):
            if order_id in self.orders:
                self.orders[order_id].status = "cancelled"
            return True
        return False

    async def cancel_all_orders(self) -> bool:
        """撤销所有订单"""
        result = await self.ws.send_command("cancel_all")
        return result and result.get('result', {}).get('success', False)

    async def close_position(self, symbol: str = None) -> bool:
        """平仓"""
        result = await self.ws.send_command("close_position", {
            "symbol": symbol or self.current_symbol,
            "type": "market"
        })
        return result and result.get('result', {}).get('success', False)

    async def switch_symbol(self, symbol: str) -> bool:
        """切换交易对"""
        result = await self.ws.send_command("switch_symbol", {"symbol": symbol})
        if result and result.get('result', {}).get('success'):
            self.current_symbol = symbol
            return True
        return False


# ============================================================================
# 1. 网格交易系统
# ============================================================================

class GridTradingSystem:
    """网格交易系统"""

    def __init__(self, controller: WeexController, config: Dict):
        self.controller = controller
        self.config = config
        self.grid_levels: List[GridLevel] = []
        self.is_running = False
        self.total_profit = Decimal("0")
        self.completed_cycles = 0

        # 配置参数
        self.symbol = config.get('symbol', 'BTCUSDT')
        self.grid_type = GridType(config.get('grid_type', 'normal'))
        self.lower_price = Decimal(str(config.get('lower_price', 80000)))
        self.upper_price = Decimal(str(config.get('upper_price', 100000)))
        self.grid_count = config.get('grid_count', 10)
        self.order_amount = config.get('order_amount', 20)  # 张
        self.leverage = config.get('leverage', 20)

    def calculate_grid_levels(self) -> List[Decimal]:
        """计算网格价位"""
        price_range = self.upper_price - self.lower_price
        grid_interval = price_range / self.grid_count
        
        levels = []
        for i in range(self.grid_count + 1):
            price = self.lower_price + (grid_interval * i)
            levels.append(price)
        
        return levels

    async def initialize_grid(self):
        """初始化网格"""
        logger.info(f"初始化网格交易: {self.symbol}")
        logger.info(f"价格区间: {self.lower_price} - {self.upper_price}")
        logger.info(f"网格数量: {self.grid_count}")
        logger.info(f"每格数量: {self.order_amount} 张")

        # 计算网格价位
        prices = self.calculate_grid_levels()
        self.grid_levels = [GridLevel(price=p) for p in prices]

        # 获取当前价格
        current_price = await self.controller.get_current_price()
        if not current_price:
            logger.error("无法获取当前价格")
            return False

        logger.info(f"当前价格: {current_price}")

        # 在当前价格下方挂买单，上方挂卖单
        for level in self.grid_levels:
            if level.price < current_price:
                # 挂买单
                order_id = await self.controller.place_order(
                    OrderSide.BUY, OrderType.LIMIT,
                    self.order_amount, level.price
                )
                if order_id:
                    level.buy_order_id = order_id
                    logger.info(f"挂买单: {level.price} x {self.order_amount}张")
            elif level.price > current_price:
                # 挂卖单
                order_id = await self.controller.place_order(
                    OrderSide.SELL, OrderType.LIMIT,
                    self.order_amount, level.price
                )
                if order_id:
                    level.sell_order_id = order_id
                    logger.info(f"挂卖单: {level.price} x {self.order_amount}张")

        return True

    async def run(self):
        """运行网格交易"""
        self.is_running = True
        
        if not await self.initialize_grid():
            logger.error("网格初始化失败")
            return

        logger.info("网格交易开始运行...")

        while self.is_running:
            try:
                # 检查订单状态
                await self.check_orders()
                await asyncio.sleep(5)  # 每5秒检查一次
            except Exception as e:
                logger.error(f"网格交易错误: {e}")
                await asyncio.sleep(10)

    async def check_orders(self):
        """检查订单状态并处理成交"""
        # 获取当前价格
        current_price = await self.controller.get_current_price()
        if not current_price:
            return

        for level in self.grid_levels:
            # 检查买单是否成交（价格跌破买单价格）
            if level.buy_order_id and current_price <= level.price:
                # 买单可能已成交，挂反向卖单
                grid_interval = (self.upper_price - self.lower_price) / self.grid_count
                sell_price = level.price + grid_interval
                
                order_id = await self.controller.place_order(
                    OrderSide.SELL, OrderType.LIMIT,
                    self.order_amount, sell_price
                )
                if order_id:
                    level.sell_order_id = order_id
                    level.buy_order_id = None
                    logger.info(f"买单成交，挂卖单: {sell_price}")

            # 检查卖单是否成交（价格突破卖单价格）
            if level.sell_order_id and current_price >= level.price:
                # 卖单可能已成交，挂反向买单
                grid_interval = (self.upper_price - self.lower_price) / self.grid_count
                buy_price = level.price - grid_interval
                
                order_id = await self.controller.place_order(
                    OrderSide.BUY, OrderType.LIMIT,
                    self.order_amount, buy_price
                )
                if order_id:
                    level.buy_order_id = order_id
                    level.sell_order_id = None
                    self.completed_cycles += 1
                    logger.info(f"卖单成交，挂买单: {buy_price}，完成循环: {self.completed_cycles}")

    def stop(self):
        """停止网格交易"""
        self.is_running = False
        logger.info("网格交易已停止")

    def get_status(self) -> Dict:
        """获取状态"""
        return {
            "symbol": self.symbol,
            "grid_type": self.grid_type.value,
            "is_running": self.is_running,
            "grid_count": self.grid_count,
            "completed_cycles": self.completed_cycles,
            "total_profit": str(self.total_profit)
        }


# ============================================================================
# 2. 刷量交易系统
# ============================================================================

class VolumeMakerSystem:
    """刷量交易系统"""

    def __init__(self, controller: WeexController, config: Dict):
        self.controller = controller
        self.config = config
        self.is_running = False
        self.total_volume = Decimal("0")
        self.trade_count = 0

        # 配置参数
        self.symbol = config.get('symbol', 'BTCUSDT')
        self.order_size = config.get('order_size', 20)  # 张
        self.interval = config.get('interval', 10)  # 秒
        self.spread_tolerance = Decimal(str(config.get('spread_tolerance', 0.001)))
        self.daily_target = Decimal(str(config.get('daily_target', 1000000)))

    async def run(self):
        """运行刷量交易"""
        self.is_running = True
        logger.info(f"刷量交易开始: {self.symbol}")
        logger.info(f"单笔数量: {self.order_size} 张")
        logger.info(f"交易间隔: {self.interval} 秒")

        while self.is_running:
            try:
                await self.execute_volume_trade()
                await asyncio.sleep(self.interval)
            except Exception as e:
                logger.error(f"刷量交易错误: {e}")
                await asyncio.sleep(self.interval * 2)

    async def execute_volume_trade(self):
        """执行一次刷量交易"""
        # 获取市场数据
        market_data = await self.controller.get_market_data()
        if not market_data:
            logger.warning("无法获取市场数据")
            return

        current_price = market_data.current_price
        
        # 计算买卖价格（在当前价格附近）
        buy_price = current_price * (Decimal("1") - self.spread_tolerance)
        sell_price = current_price * (Decimal("1") + self.spread_tolerance)

        # 下买单
        buy_order_id = await self.controller.place_order(
            OrderSide.BUY, OrderType.LIMIT,
            self.order_size, buy_price
        )

        # 下卖单
        sell_order_id = await self.controller.place_order(
            OrderSide.SELL, OrderType.LIMIT,
            self.order_size, sell_price
        )

        if buy_order_id and sell_order_id:
            self.trade_count += 1
            volume = current_price * Decimal(str(self.order_size)) * 2
            self.total_volume += volume
            logger.info(f"刷量交易 #{self.trade_count}: 买@{buy_price:.2f}, 卖@{sell_price:.2f}")

        # 等待一小段时间后撤销未成交订单
        await asyncio.sleep(3)
        await self.controller.cancel_all_orders()

    def stop(self):
        """停止刷量交易"""
        self.is_running = False
        logger.info("刷量交易已停止")

    def get_status(self) -> Dict:
        """获取状态"""
        return {
            "symbol": self.symbol,
            "is_running": self.is_running,
            "trade_count": self.trade_count,
            "total_volume": str(self.total_volume),
            "daily_target": str(self.daily_target)
        }


# ============================================================================
# 3. 套利监控与执行系统
# ============================================================================

class ArbitrageSystem:
    """套利监控与执行系统"""

    def __init__(self, controller: WeexController, config: Dict):
        self.controller = controller
        self.config = config
        self.is_running = False
        self.opportunities_found = 0
        self.executed_trades = 0

        # 配置参数
        self.symbol = config.get('symbol', 'BTCUSDT')
        self.reference_prices: Dict[str, Decimal] = {}  # 其他交易所价格
        self.min_spread = Decimal(str(config.get('min_spread', 0.005)))  # 0.5%
        self.order_size = config.get('order_size', 20)
        self.auto_execute = config.get('auto_execute', False)

        # 价格回调
        self.price_callbacks: List[Callable] = []

    def set_reference_price(self, exchange: str, price: Decimal):
        """设置参考价格（来自其他交易所）"""
        self.reference_prices[exchange] = price

    def add_price_callback(self, callback: Callable):
        """添加价格回调"""
        self.price_callbacks.append(callback)

    async def run(self):
        """运行套利监控"""
        self.is_running = True
        logger.info(f"套利监控开始: {self.symbol}")
        logger.info(f"最小价差阈值: {self.min_spread * 100}%")
        logger.info(f"自动执行: {'是' if self.auto_execute else '否'}")

        while self.is_running:
            try:
                await self.check_arbitrage_opportunity()
                await asyncio.sleep(1)  # 每秒检查一次
            except Exception as e:
                logger.error(f"套利监控错误: {e}")
                await asyncio.sleep(5)

    async def check_arbitrage_opportunity(self):
        """检查套利机会"""
        # 获取WEEX价格
        weex_price = await self.controller.get_current_price()
        if not weex_price:
            return

        # 与其他交易所价格比较
        for exchange, ref_price in self.reference_prices.items():
            spread = (weex_price - ref_price) / ref_price

            if abs(spread) >= self.min_spread:
                self.opportunities_found += 1
                
                if spread > 0:
                    # WEEX价格高，在WEEX卖出
                    direction = "WEEX卖出"
                    action_side = OrderSide.SELL
                else:
                    # WEEX价格低，在WEEX买入
                    direction = "WEEX买入"
                    action_side = OrderSide.BUY

                logger.info(f"🎯 套利机会 #{self.opportunities_found}: "
                           f"WEEX={weex_price}, {exchange}={ref_price}, "
                           f"价差={spread*100:.3f}%, {direction}")

                # 触发回调
                for callback in self.price_callbacks:
                    await callback({
                        "type": "arbitrage_opportunity",
                        "weex_price": str(weex_price),
                        "exchange": exchange,
                        "ref_price": str(ref_price),
                        "spread": str(spread),
                        "direction": direction
                    })

                # 自动执行
                if self.auto_execute:
                    await self.execute_arbitrage(action_side, weex_price)

    async def execute_arbitrage(self, side: OrderSide, price: Decimal):
        """执行套利交易"""
        order_id = await self.controller.place_order(
            side, OrderType.MARKET, self.order_size
        )
        if order_id:
            self.executed_trades += 1
            logger.info(f"套利交易执行: {side.value} {self.order_size}张 @ 市价")

    def stop(self):
        """停止套利监控"""
        self.is_running = False
        logger.info("套利监控已停止")

    def get_status(self) -> Dict:
        """获取状态"""
        return {
            "symbol": self.symbol,
            "is_running": self.is_running,
            "opportunities_found": self.opportunities_found,
            "executed_trades": self.executed_trades,
            "reference_prices": {k: str(v) for k, v in self.reference_prices.items()}
        }


# ============================================================================
# 4. 网格波动率扫描器
# ============================================================================

class VolatilityScannerSystem:
    """网格波动率扫描器"""

    def __init__(self, controller: WeexController, config: Dict):
        self.controller = controller
        self.config = config
        self.is_running = False
        self.scan_results: Dict[str, Dict] = {}

        # 配置参数
        self.symbols = config.get('symbols', ['BTCUSDT', 'ETHUSDT'])
        self.scan_interval = config.get('scan_interval', 300)  # 5分钟
        self.min_volatility = Decimal(str(config.get('min_volatility', 0.01)))
        self.max_volatility = Decimal(str(config.get('max_volatility', 0.10)))

    async def run(self):
        """运行波动率扫描"""
        self.is_running = True
        logger.info("波动率扫描器开始运行")
        logger.info(f"扫描交易对: {self.symbols}")
        logger.info(f"扫描间隔: {self.scan_interval} 秒")

        while self.is_running:
            try:
                await self.scan_all_symbols()
                self.print_recommendations()
                await asyncio.sleep(self.scan_interval)
            except Exception as e:
                logger.error(f"波动率扫描错误: {e}")
                await asyncio.sleep(60)

    async def scan_all_symbols(self):
        """扫描所有交易对"""
        for symbol in self.symbols:
            try:
                # 切换到该交易对
                await self.controller.switch_symbol(symbol)
                await asyncio.sleep(1)

                # 获取市场数据
                market_data = await self.controller.get_market_data()
                if market_data:
                    # 计算波动率
                    volatility = self.calculate_volatility(market_data)
                    
                    self.scan_results[symbol] = {
                        "volatility": volatility,
                        "current_price": market_data.current_price,
                        "high_24h": market_data.high_24h,
                        "low_24h": market_data.low_24h,
                        "volume_24h": market_data.volume_24h,
                        "recommended": self.min_volatility <= volatility <= self.max_volatility,
                        "timestamp": datetime.now()
                    }

                    logger.info(f"扫描 {symbol}: 波动率={volatility*100:.2f}%")

            except Exception as e:
                logger.error(f"扫描 {symbol} 失败: {e}")

    def calculate_volatility(self, market_data: MarketData) -> Decimal:
        """计算波动率"""
        if market_data.low_24h == 0:
            return Decimal("0")
        
        price_range = market_data.high_24h - market_data.low_24h
        volatility = price_range / market_data.low_24h
        return volatility

    def print_recommendations(self):
        """打印推荐结果"""
        logger.info("\n" + "=" * 60)
        logger.info("📊 波动率扫描结果")
        logger.info("=" * 60)

        # 按波动率排序
        sorted_results = sorted(
            self.scan_results.items(),
            key=lambda x: x[1]['volatility'],
            reverse=True
        )

        for symbol, data in sorted_results:
            status = "✅ 推荐" if data['recommended'] else "❌ 不推荐"
            logger.info(f"{symbol}: 波动率={data['volatility']*100:.2f}% {status}")

        logger.info("=" * 60 + "\n")

    def get_recommendations(self) -> List[str]:
        """获取推荐的交易对"""
        return [
            symbol for symbol, data in self.scan_results.items()
            if data.get('recommended', False)
        ]

    def stop(self):
        """停止扫描"""
        self.is_running = False
        logger.info("波动率扫描器已停止")

    def get_status(self) -> Dict:
        """获取状态"""
        return {
            "is_running": self.is_running,
            "symbols_count": len(self.symbols),
            "scan_results": {
                k: {
                    "volatility": str(v['volatility']),
                    "recommended": v['recommended']
                }
                for k, v in self.scan_results.items()
            }
        }


# ============================================================================
# 5. 价格提醒系统
# ============================================================================

class PriceAlertSystem:
    """价格提醒系统"""

    def __init__(self, controller: WeexController, config: Dict):
        self.controller = controller
        self.config = config
        self.is_running = False
        self.alerts_triggered = 0
        self.price_history: deque = deque(maxlen=100)

        # 配置参数
        self.symbol = config.get('symbol', 'BTCUSDT')
        self.upper_limit = Decimal(str(config.get('upper_limit', 100000)))
        self.lower_limit = Decimal(str(config.get('lower_limit', 80000)))
        self.change_threshold = Decimal(str(config.get('change_threshold', 0.02)))  # 2%
        self.check_interval = config.get('check_interval', 5)  # 秒

        # 提醒回调
        self.alert_callbacks: List[Callable] = []

    def add_alert_callback(self, callback: Callable):
        """添加提醒回调"""
        self.alert_callbacks.append(callback)

    async def run(self):
        """运行价格提醒"""
        self.is_running = True
        logger.info(f"价格提醒系统开始: {self.symbol}")
        logger.info(f"上限: {self.upper_limit}, 下限: {self.lower_limit}")
        logger.info(f"变动阈值: {self.change_threshold * 100}%")

        while self.is_running:
            try:
                await self.check_price()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"价格提醒错误: {e}")
                await asyncio.sleep(self.check_interval * 2)

    async def check_price(self):
        """检查价格"""
        current_price = await self.controller.get_current_price()
        if not current_price:
            return

        # 记录价格历史
        self.price_history.append({
            "price": current_price,
            "timestamp": datetime.now()
        })

        # 检查上下限
        if current_price >= self.upper_limit:
            await self.trigger_alert("upper_limit", current_price)
        elif current_price <= self.lower_limit:
            await self.trigger_alert("lower_limit", current_price)

        # 检查价格变动
        if len(self.price_history) >= 2:
            oldest = self.price_history[0]
            change = (current_price - oldest['price']) / oldest['price']
            
            if abs(change) >= self.change_threshold:
                await self.trigger_alert("price_change", current_price, change)

    async def trigger_alert(self, alert_type: str, price: Decimal, change: Decimal = None):
        """触发提醒"""
        self.alerts_triggered += 1

        alert_data = {
            "type": alert_type,
            "symbol": self.symbol,
            "price": str(price),
            "timestamp": datetime.now().isoformat()
        }

        if alert_type == "upper_limit":
            message = f"🔔 价格突破上限! {self.symbol} = {price} (上限: {self.upper_limit})"
        elif alert_type == "lower_limit":
            message = f"🔔 价格跌破下限! {self.symbol} = {price} (下限: {self.lower_limit})"
        elif alert_type == "price_change":
            alert_data["change"] = str(change)
            direction = "上涨" if change > 0 else "下跌"
            message = f"🔔 价格大幅{direction}! {self.symbol} = {price} ({change*100:.2f}%)"
        else:
            message = f"🔔 价格提醒: {self.symbol} = {price}"

        logger.warning(message)

        # 触发回调
        for callback in self.alert_callbacks:
            await callback(alert_data)

    def stop(self):
        """停止价格提醒"""
        self.is_running = False
        logger.info("价格提醒系统已停止")

    def get_status(self) -> Dict:
        """获取状态"""
        latest_price = self.price_history[-1]['price'] if self.price_history else None
        return {
            "symbol": self.symbol,
            "is_running": self.is_running,
            "alerts_triggered": self.alerts_triggered,
            "upper_limit": str(self.upper_limit),
            "lower_limit": str(self.lower_limit),
            "latest_price": str(latest_price) if latest_price else None
        }


# ============================================================================
# 主应用
# ============================================================================

class WeexTradingApp:
    """WEEX 交易应用"""

    def __init__(self, config_path: str = None):
        self.config_path = config_path
        self.config = {}
        self.ws_server = WeexWebSocketServer()
        self.controller = WeexController(self.ws_server)
        
        # 交易系统
        self.grid_trading: Optional[GridTradingSystem] = None
        self.volume_maker: Optional[VolumeMakerSystem] = None
        self.arbitrage: Optional[ArbitrageSystem] = None
        self.volatility_scanner: Optional[VolatilityScannerSystem] = None
        self.price_alert: Optional[PriceAlertSystem] = None

        self._running = False

    def load_config(self, config_path: str = None):
        """加载配置"""
        path = config_path or self.config_path
        if path and Path(path).exists():
            with open(path, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)
            logger.info(f"配置已加载: {path}")
        else:
            # 使用默认配置
            self.config = self.get_default_config()
            logger.info("使用默认配置")

    def get_default_config(self) -> Dict:
        """获取默认配置"""
        return {
            "grid_trading": {
                "enabled": True,
                "symbol": "BTCUSDT",
                "grid_type": "normal",
                "lower_price": 85000,
                "upper_price": 95000,
                "grid_count": 10,
                "order_amount": 20,
                "leverage": 20
            },
            "volume_maker": {
                "enabled": False,
                "symbol": "BTCUSDT",
                "order_size": 20,
                "interval": 10,
                "spread_tolerance": 0.001,
                "daily_target": 1000000
            },
            "arbitrage": {
                "enabled": False,
                "symbol": "BTCUSDT",
                "min_spread": 0.005,
                "order_size": 20,
                "auto_execute": False
            },
            "volatility_scanner": {
                "enabled": False,
                "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
                "scan_interval": 300,
                "min_volatility": 0.01,
                "max_volatility": 0.10
            },
            "price_alert": {
                "enabled": True,
                "symbol": "BTCUSDT",
                "upper_limit": 100000,
                "lower_limit": 80000,
                "change_threshold": 0.02,
                "check_interval": 5
            }
        }

    def initialize_systems(self):
        """初始化各交易系统"""
        # 网格交易
        if self.config.get('grid_trading', {}).get('enabled', False):
            self.grid_trading = GridTradingSystem(
                self.controller, self.config['grid_trading']
            )
            logger.info("✅ 网格交易系统已初始化")

        # 刷量交易
        if self.config.get('volume_maker', {}).get('enabled', False):
            self.volume_maker = VolumeMakerSystem(
                self.controller, self.config['volume_maker']
            )
            logger.info("✅ 刷量交易系统已初始化")

        # 套利监控
        if self.config.get('arbitrage', {}).get('enabled', False):
            self.arbitrage = ArbitrageSystem(
                self.controller, self.config['arbitrage']
            )
            logger.info("✅ 套利监控系统已初始化")

        # 波动率扫描
        if self.config.get('volatility_scanner', {}).get('enabled', False):
            self.volatility_scanner = VolatilityScannerSystem(
                self.controller, self.config['volatility_scanner']
            )
            logger.info("✅ 波动率扫描器已初始化")

        # 价格提醒
        if self.config.get('price_alert', {}).get('enabled', False):
            self.price_alert = PriceAlertSystem(
                self.controller, self.config['price_alert']
            )
            logger.info("✅ 价格提醒系统已初始化")

    async def run(self):
        """运行应用"""
        self._running = True
        
        # 加载配置
        self.load_config()
        
        # 初始化系统
        self.initialize_systems()

        # 启动任务列表
        tasks = [
            asyncio.create_task(self.ws_server.start())
        ]

        # 等待浏览器连接
        logger.info("\n" + "=" * 60)
        logger.info("WEEX 统一交易服务器已启动")
        logger.info("=" * 60)
        logger.info("等待浏览器连接...")
        logger.info("请在浏览器中执行: weexBot.connect('ws://localhost:8766')")
        logger.info("=" * 60 + "\n")

        while not self.ws_server.clients and self._running:
            await asyncio.sleep(1)

        if not self._running:
            return

        logger.info("浏览器已连接，启动交易系统...")

        # 启动各交易系统
        if self.grid_trading:
            tasks.append(asyncio.create_task(self.grid_trading.run()))
        if self.volume_maker:
            tasks.append(asyncio.create_task(self.volume_maker.run()))
        if self.arbitrage:
            tasks.append(asyncio.create_task(self.arbitrage.run()))
        if self.volatility_scanner:
            tasks.append(asyncio.create_task(self.volatility_scanner.run()))
        if self.price_alert:
            tasks.append(asyncio.create_task(self.price_alert.run()))

        # 等待所有任务
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass

    def stop(self):
        """停止应用"""
        self._running = False
        self.ws_server.stop()
        
        if self.grid_trading:
            self.grid_trading.stop()
        if self.volume_maker:
            self.volume_maker.stop()
        if self.arbitrage:
            self.arbitrage.stop()
        if self.volatility_scanner:
            self.volatility_scanner.stop()
        if self.price_alert:
            self.price_alert.stop()

        logger.info("应用已停止")

    def get_all_status(self) -> Dict:
        """获取所有系统状态"""
        status = {}
        if self.grid_trading:
            status['grid_trading'] = self.grid_trading.get_status()
        if self.volume_maker:
            status['volume_maker'] = self.volume_maker.get_status()
        if self.arbitrage:
            status['arbitrage'] = self.arbitrage.get_status()
        if self.volatility_scanner:
            status['volatility_scanner'] = self.volatility_scanner.get_status()
        if self.price_alert:
            status['price_alert'] = self.price_alert.get_status()
        return status


# ============================================================================
# 入口点
# ============================================================================

async def main():
    """主函数"""
    import sys
    
    # 获取配置文件路径
    config_path = None
    if len(sys.argv) > 1:
        config_path = sys.argv[1]

    print("=" * 60)
    print("🚀 WEEX 统一交易服务器 v1.0")
    print("=" * 60)
    print()
    print("功能模块:")
    print("  1. 网格交易系统 (Grid Trading)")
    print("  2. 刷量交易系统 (Volume Maker)")
    print("  3. 套利监控与执行系统 (Arbitrage)")
    print("  4. 网格波动率扫描器 (Volatility Scanner)")
    print("  5. 价格提醒系统 (Price Alert)")
    print()
    print("=" * 60)
    print()

    app = WeexTradingApp(config_path)

    try:
        await app.run()
    except KeyboardInterrupt:
        print("\n\n⚠️  收到中断信号...")
    finally:
        app.stop()
        print("\n✅ 程序已退出")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n程序被用户中断")
