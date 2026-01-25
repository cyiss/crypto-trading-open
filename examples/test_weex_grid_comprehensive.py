#!/usr/bin/env python3
"""
WEEX 网格交易综合测试框架

本脚本提供完整的网格交易测试流程，包括：
1. 订单计算和生成
2. 订单验证
3. 下单执行模拟
4. 成交监控
5. 数据收集和报告生成

这是一个独立的Python系统，可以与浏览器端脚本协作。
"""

import asyncio
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import List, Dict, Any, Optional, Tuple

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class OrderSide(Enum):
    """订单方向"""
    BUY = "buy"
    SELL = "sell"


class OrderStatus(Enum):
    """订单状态"""
    PENDING = "pending"
    PLACED = "placed"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class GridOrder:
    """网格订单"""
    order_id: str
    side: OrderSide
    price: Decimal
    quantity: Decimal
    status: OrderStatus = OrderStatus.PENDING
    created_at: str = None
    placed_at: str = None
    filled_at: str = None
    filled_quantity: Decimal = Decimal("0")
    avg_price: Decimal = Decimal("0")
    commission: Decimal = Decimal("0")
    pnl: Decimal = Decimal("0")
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()


@dataclass
class GridConfig:
    """网格配置"""
    symbol: str = "BTC/USDT"
    grid_count: int = 10
    grid_spacing: Decimal = Decimal("500")
    order_quantity: Decimal = Decimal("20")
    current_price: Decimal = Decimal("87868")
    max_leverage: int = 200


class GridCalculator:
    """网格计算器"""
    
    def __init__(self, config: GridConfig):
        self.config = config
    
    def calculate_grid_levels(self) -> Tuple[List[Decimal], List[Decimal]]:
        """
        计算网格价格水平
        
        Returns:
            Tuple: (买入价格列表, 卖出价格列表)
        """
        half_grid = self.config.grid_count // 2
        
        # 计算买入价格（当前价格以下）
        buy_prices = []
        for i in range(1, half_grid + 1):
            price = self.config.current_price - (self.config.grid_spacing * i)
            if price > 0:
                buy_prices.append(price)
        
        # 计算卖出价格（当前价格以上）
        sell_prices = []
        for i in range(1, half_grid + 1):
            price = self.config.current_price + (self.config.grid_spacing * i)
            sell_prices.append(price)
        
        return sorted(buy_prices, reverse=True), sorted(sell_prices)
    
    def generate_orders(self) -> List[GridOrder]:
        """
        生成网格订单
        
        Returns:
            List: 网格订单列表
        """
        buy_prices, sell_prices = self.calculate_grid_levels()
        orders = []
        
        # 生成买单
        for i, price in enumerate(buy_prices, 1):
            order = GridOrder(
                order_id=f"BUY_{i:02d}",
                side=OrderSide.BUY,
                price=price,
                quantity=self.config.order_quantity
            )
            orders.append(order)
        
        # 生成卖单
        for i, price in enumerate(sell_prices, 1):
            order = GridOrder(
                order_id=f"SELL_{i:02d}",
                side=OrderSide.SELL,
                price=price,
                quantity=self.config.order_quantity
            )
            orders.append(order)
        
        return orders


class GridTrader:
    """网格交易机器人"""
    
    def __init__(self, config: GridConfig):
        self.config = config
        self.calculator = GridCalculator(config)
        self.orders: List[GridOrder] = []
        self.filled_orders: List[GridOrder] = []
        self.stats = {
            "total_orders": 0,
            "placed_orders": 0,
            "failed_orders": 0,
            "filled_orders": 0,
            "total_pnl": Decimal("0"),
            "total_commission": Decimal("0"),
            "start_time": None,
            "end_time": None
        }
    
    async def initialize(self) -> bool:
        """初始化交易机器人"""
        logger.info("=" * 70)
        logger.info("初始化网格交易机器人")
        logger.info("=" * 70)
        
        try:
            logger.info(f"交易对: {self.config.symbol}")
            logger.info(f"网格数量: {self.config.grid_count}")
            logger.info(f"网格间距: {self.config.grid_spacing} USDT")
            logger.info(f"单笔数量: {self.config.order_quantity} 张")
            logger.info(f"当前价格: {self.config.current_price} USDT")
            
            # 生成网格订单
            self.orders = self.calculator.generate_orders()
            self.stats["total_orders"] = len(self.orders)
            
            logger.info(f"✓ 已生成 {len(self.orders)} 个网格订单")
            return True
        except Exception as e:
            logger.error(f"✗ 初始化失败: {e}")
            return False
    
    async def place_orders(self) -> int:
        """
        下单
        
        Returns:
            int: 成功下单数
        """
        logger.info("=" * 70)
        logger.info("开始下单")
        logger.info("=" * 70)
        
        self.stats["start_time"] = datetime.now().isoformat()
        placed_count = 0
        
        # 分别下买单和卖单
        buy_orders = [o for o in self.orders if o.side == OrderSide.BUY]
        sell_orders = [o for o in self.orders if o.side == OrderSide.SELL]
        
        # 下买单
        logger.info(f"\n下买单 (共 {len(buy_orders)} 个):")
        for order in buy_orders:
            success = await self._place_single_order(order)
            if success:
                placed_count += 1
            await asyncio.sleep(0.5)  # 防止过快
        
        # 下卖单
        logger.info(f"\n下卖单 (共 {len(sell_orders)} 个):")
        for order in sell_orders:
            success = await self._place_single_order(order)
            if success:
                placed_count += 1
            await asyncio.sleep(0.5)  # 防止过快
        
        self.stats["placed_orders"] = placed_count
        logger.info(f"\n✓ 成功下单 {placed_count}/{len(self.orders)} 个订单")
        
        return placed_count
    
    async def _place_single_order(self, order: GridOrder) -> bool:
        """
        下单个订单
        
        Args:
            order: 订单对象
            
        Returns:
            bool: 是否成功
        """
        try:
            side_str = "买入" if order.side == OrderSide.BUY else "卖出"
            logger.info(f"  {order.order_id}: {side_str} {order.quantity} @ {order.price} USDT")
            
            # 模拟下单
            order.status = OrderStatus.PLACED
            order.placed_at = datetime.now().isoformat()
            
            return True
        except Exception as e:
            logger.error(f"    下单失败: {e}")
            order.status = OrderStatus.FAILED
            self.stats["failed_orders"] += 1
            return False
    
    async def simulate_price_movement(self, price_changes: List[Decimal]) -> None:
        """
        模拟价格变动并触发成交
        
        Args:
            price_changes: 价格变动列表
        """
        logger.info("=" * 70)
        logger.info("模拟价格变动")
        logger.info("=" * 70)
        
        current_price = self.config.current_price
        
        for i, change in enumerate(price_changes, 1):
            current_price += change
            logger.info(f"\n[变动 {i}] 价格: {current_price} USDT (变化: {change:+.0f} USDT)")
            
            # 检查订单是否应该成交
            filled_count = 0
            for order in self.orders:
                if order.status == OrderStatus.PLACED:
                    should_fill = False
                    
                    if order.side == OrderSide.BUY and current_price <= order.price:
                        should_fill = True
                    elif order.side == OrderSide.SELL and current_price >= order.price:
                        should_fill = True
                    
                    if should_fill:
                        await self._fill_order(order, current_price)
                        filled_count += 1
            
            if filled_count > 0:
                logger.info(f"  成交订单: {filled_count} 个")
            
            await asyncio.sleep(1)
    
    async def _fill_order(self, order: GridOrder, fill_price: Decimal) -> None:
        """
        成交订单
        
        Args:
            order: 订单对象
            fill_price: 成交价格
        """
        try:
            order.status = OrderStatus.FILLED
            order.filled_quantity = order.quantity
            order.avg_price = fill_price
            order.filled_at = datetime.now().isoformat()
            
            # 计算手续费（0.05%）
            commission_rate = Decimal("0.0005")
            order.commission = order.quantity * fill_price * commission_rate
            
            # 计算盈亏
            if order.side == OrderSide.BUY:
                order.pnl = (fill_price - order.price) * order.quantity - order.commission
            else:
                order.pnl = (order.price - fill_price) * order.quantity - order.commission
            
            self.filled_orders.append(order)
            self.stats["filled_orders"] += 1
            self.stats["total_pnl"] += order.pnl
            self.stats["total_commission"] += order.commission
            
            side_str = "买入" if order.side == OrderSide.BUY else "卖出"
            logger.info(f"    ✓ {order.order_id} 成交: {side_str} {order.quantity} @ {fill_price}")
        except Exception as e:
            logger.error(f"    成交失败: {e}")
    
    async def monitor_grid(self, duration: int = 60) -> None:
        """
        监控网格交易
        
        Args:
            duration: 监控时长（秒）
        """
        logger.info("=" * 70)
        logger.info(f"监控网格交易 ({duration}秒)")
        logger.info("=" * 70)
        
        start_time = datetime.now()
        check_interval = 5
        
        while (datetime.now() - start_time).total_seconds() < duration:
            pending = len([o for o in self.orders if o.status == OrderStatus.PLACED])
            filled = len(self.filled_orders)
            
            elapsed = int((datetime.now() - start_time).total_seconds())
            logger.info(f"[{elapsed}s] 待成交: {pending}, 已成交: {filled}, 累计盈亏: {self.stats['total_pnl']:.2f} USDT")
            
            await asyncio.sleep(check_interval)
    
    async def generate_report(self) -> Dict[str, Any]:
        """
        生成测试报告
        
        Returns:
            Dict: 测试报告
        """
        self.stats["end_time"] = datetime.now().isoformat()
        
        logger.info("=" * 70)
        logger.info("测试报告")
        logger.info("=" * 70)
        
        logger.info(f"\n订单统计:")
        logger.info(f"  总订单数: {self.stats['total_orders']}")
        logger.info(f"  已下单: {self.stats['placed_orders']}")
        logger.info(f"  失败: {self.stats['failed_orders']}")
        logger.info(f"  已成交: {self.stats['filled_orders']}")
        
        logger.info(f"\n财务统计:")
        logger.info(f"  累计盈亏: {self.stats['total_pnl']:.2f} USDT")
        logger.info(f"  总手续费: {self.stats['total_commission']:.2f} USDT")
        
        if self.filled_orders:
            logger.info(f"\n成交订单详情:")
            for order in self.filled_orders[:5]:
                side_str = "买入" if order.side == OrderSide.BUY else "卖出"
                logger.info(f"  {order.order_id}: {side_str} {order.quantity} @ {order.avg_price} (盈亏: {order.pnl:.2f})")
        
        return self.stats
    
    async def run(self) -> None:
        """运行完整的网格交易流程"""
        try:
            # 初始化
            if not await self.initialize():
                return
            
            # 下单
            await self.place_orders()
            
            # 模拟价格变动
            price_changes = [
                Decimal("-100"),  # 价格下跌
                Decimal("-100"),
                Decimal("-100"),
                Decimal("200"),   # 价格上升
                Decimal("200"),
                Decimal("100"),
            ]
            await self.simulate_price_movement(price_changes)
            
            # 监控
            await self.monitor_grid(duration=30)
            
            # 生成报告
            await self.generate_report()
            
            logger.info("\n" + "=" * 70)
            logger.info("✅ 网格交易测试完成！")
            logger.info("=" * 70)
            
        except Exception as e:
            logger.error(f"测试失败: {e}", exc_info=True)


async def main():
    """主函数"""
    config = GridConfig(
        symbol="BTC/USDT",
        grid_count=10,
        grid_spacing=Decimal("500"),
        order_quantity=Decimal("20"),
        current_price=Decimal("87868")
    )
    
    trader = GridTrader(config)
    await trader.run()


if __name__ == "__main__":
    asyncio.run(main())
