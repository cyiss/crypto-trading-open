#!/usr/bin/env python3
"""
WEEX BTC 合约网格交易示例

本示例展示如何使用 WEEX 适配器实现 BTC/USDT 永续合约的网格交易策略。

网格交易原理：
- 在价格区间内设置多个买卖订单
- 当价格上升时，卖出获利
- 当价格下降时，买入摊低成本
- 通过多次小额交易实现利润累积
"""

import asyncio
import logging
from decimal import Decimal
from typing import List, Dict, Any

from core.adapters.exchanges.interface import ExchangeConfig, ExchangeType
from core.adapters.exchanges.adapters import WeexAdapter
from core.adapters.exchanges.models import OrderSide, OrderType, OrderData

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BTCGridTrader:
    """BTC 网格交易机器人"""

    def __init__(
        self,
        adapter: WeexAdapter,
        symbol: str = "cmt_btcusdt",
        grid_count: int = 10,
        grid_spacing: Decimal = Decimal("1000"),  # 每个网格间隔 1000 USDT
        order_amount: Decimal = Decimal("0.01"),  # 每个订单 0.01 BTC
    ):
        """
        初始化网格交易机器人
        
        Args:
            adapter: WEEX 交易所适配器
            symbol: 交易对
            grid_count: 网格数量
            grid_spacing: 网格间隔（USDT）
            order_amount: 每个订单的数量（BTC）
        """
        self.adapter = adapter
        self.symbol = symbol
        self.grid_count = grid_count
        self.grid_spacing = grid_spacing
        self.order_amount = order_amount
        self.orders: Dict[str, OrderData] = {}
        self.pnl = Decimal("0")  # 累计利润

    async def initialize(self) -> bool:
        """初始化交易机器人"""
        try:
            logger.info("初始化 BTC 网格交易机器人...")
            
            # 连接到交易所
            if not await self.adapter.connect():
                logger.error("连接失败")
                return False
            
            logger.info("✓ 连接成功")
            return True
        except Exception as e:
            logger.error(f"初始化失败: {e}")
            return False

    async def get_current_price(self) -> Decimal:
        """获取当前 BTC 价格"""
        try:
            ticker = await self.adapter.get_ticker(self.symbol)
            return ticker.last
        except Exception as e:
            logger.error(f"获取价格失败: {e}")
            raise

    async def calculate_grid_levels(self, current_price: Decimal) -> Dict[str, Decimal]:
        """
        计算网格价格水平
        
        Args:
            current_price: 当前价格
            
        Returns:
            网格价格字典 {'buy': [价格列表], 'sell': [价格列表]}
        """
        half_grid = self.grid_count // 2
        
        # 计算买入价格（当前价格以下）
        buy_prices = []
        for i in range(1, half_grid + 1):
            price = current_price - (self.grid_spacing * i)
            if price > 0:
                buy_prices.append(price)
        
        # 计算卖出价格（当前价格以上）
        sell_prices = []
        for i in range(1, half_grid + 1):
            price = current_price + (self.grid_spacing * i)
            sell_prices.append(price)
        
        return {
            "buy": sorted(buy_prices, reverse=True),  # 从高到低
            "sell": sorted(sell_prices),  # 从低到高
        }

    async def place_grid_orders(self, grid_levels: Dict[str, List[Decimal]]) -> None:
        """
        下单网格订单
        
        Args:
            grid_levels: 网格价格水平
        """
        logger.info("=" * 60)
        logger.info("下单网格订单...")
        logger.info("=" * 60)
        
        # 下买单
        logger.info(f"\n买入订单 (共 {len(grid_levels['buy'])} 个):")
        for i, price in enumerate(grid_levels["buy"], 1):
            logger.info(f"  {i}. 价格: {price} USDT, 数量: {self.order_amount} BTC")
            # 实际下单（注释掉以防止意外交易）
            # try:
            #     order = await self.adapter.create_order(
            #         symbol=self.symbol,
            #         side=OrderSide.BUY,
            #         order_type=OrderType.LIMIT,
            #         amount=self.order_amount,
            #         price=price,
            #     )
            #     self.orders[order.order_id] = order
            #     logger.info(f"    订单已下: {order.order_id}")
            # except Exception as e:
            #     logger.error(f"    下单失败: {e}")
        
        # 下卖单
        logger.info(f"\n卖出订单 (共 {len(grid_levels['sell'])} 个):")
        for i, price in enumerate(grid_levels["sell"], 1):
            logger.info(f"  {i}. 价格: {price} USDT, 数量: {self.order_amount} BTC")
            # 实际下单（注释掉以防止意外交易）
            # try:
            #     order = await self.adapter.create_order(
            #         symbol=self.symbol,
            #         side=OrderSide.SELL,
            #         order_type=OrderType.LIMIT,
            #         amount=self.order_amount,
            #         price=price,
            #     )
            #     self.orders[order.order_id] = order
            #     logger.info(f"    订单已下: {order.order_id}")
            # except Exception as e:
            #     logger.error(f"    下单失败: {e}")

    async def monitor_grid(self) -> None:
        """监控网格交易"""
        logger.info("\n" + "=" * 60)
        logger.info("监控网格交易...")
        logger.info("=" * 60)
        
        try:
            # 获取开放订单
            open_orders = await self.adapter.get_open_orders(self.symbol)
            logger.info(f"开放订单数: {len(open_orders)}")
            
            for order in open_orders[:5]:
                logger.info(f"  订单 {order.order_id}: {order.side} {order.amount} @ {order.price}")
            
            # 获取持仓
            positions = await self.adapter.get_positions()
            if positions:
                logger.info(f"\n持仓数: {len(positions)}")
                for pos in positions[:5]:
                    logger.info(f"  {pos.symbol}: {pos.side} {pos.quantity} @ {pos.entry_price}")
            else:
                logger.info("\n暂无持仓")
        except Exception as e:
            logger.error(f"监控失败: {e}")

    async def run(self) -> None:
        """运行网格交易机器人"""
        try:
            # 初始化
            if not await self.initialize():
                return
            
            # 获取当前价格
            logger.info("\n获取当前 BTC 价格...")
            current_price = await self.get_current_price()
            logger.info(f"当前价格: {current_price} USDT")
            
            # 计算网格价格
            logger.info("\n计算网格价格...")
            grid_levels = await self.calculate_grid_levels(current_price)
            logger.info(f"买入价格范围: {grid_levels['buy'][0]} - {grid_levels['buy'][-1]} USDT")
            logger.info(f"卖出价格范围: {grid_levels['sell'][0]} - {grid_levels['sell'][-1]} USDT")
            
            # 下单
            await self.place_grid_orders(grid_levels)
            
            # 监控
            await self.monitor_grid()
            
            logger.info("\n" + "=" * 60)
            logger.info("✅ 网格交易机器人运行完成！")
            logger.info("=" * 60)
            logger.info("\n注意: 示例中的下单操作已注释，以防止意外交易。")
            logger.info("如需实际下单，请取消注释 place_grid_orders 方法中的下单代码。")
            
        except Exception as e:
            logger.error(f"运行失败: {e}", exc_info=True)
        finally:
            await self.adapter.disconnect()


async def main():
    """主函数"""
    
    # 创建 WEEX 配置
    config = ExchangeConfig(
        exchange_id="weex",
        name="WEEX",
        exchange_type=ExchangeType.PERPETUAL,
        api_key="weex_d0649c112185fb5a0aeb13846fe915ac",
        api_secret="a041e89a40dba5c2a8ae80ec12d2a51ece7026ab378f21bad74fcb1e984f3a61",
        api_passphrase="manus_auto",
        testnet=False,
        enable_websocket=True,
    )
    
    # 创建适配器
    adapter = WeexAdapter(config)
    
    # 创建网格交易机器人
    trader = BTCGridTrader(
        adapter=adapter,
        symbol="cmt_btcusdt",
        grid_count=10,
        grid_spacing=Decimal("1000"),
        order_amount=Decimal("0.01"),
    )
    
    # 运行
    await trader.run()


if __name__ == "__main__":
    asyncio.run(main())
