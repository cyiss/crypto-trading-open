"""
WEEX 交易所适配器使用示例

本示例展示如何使用 WEEX 适配器进行交易所连接、数据获取和订单操作。
"""

import asyncio
import logging
from decimal import Decimal

from core.adapters.exchanges.interface import ExchangeConfig, ExchangeType
from core.adapters.exchanges.adapters import WeexAdapter


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """主函数"""
    
    # 创建 WEEX 配置
    config = ExchangeConfig(
        exchange_id="weex",
        name="WEEX",
        exchange_type=ExchangeType.PERPETUAL_FUTURES,
        api_key="weex_d0649c112185fb5a0aeb13846fe915ac",
        api_secret="a041e89a40dba5c2a8ae80ec12d2a51ece7026ab378f21bad74fcb1e984f3a61",
        api_passphrase="manus_auto",
        testnet=False,
        enable_websocket=True,
    )
    
    # 创建适配器
    adapter = WeexAdapter(config)
    
    try:
        # 连接到交易所
        logger.info("连接到 WEEX...")
        connected = await adapter.connect()
        if not connected:
            logger.error("连接失败")
            return
        
        logger.info("连接成功")
        
        # 进行身份认证
        logger.info("进行身份认证...")
        authenticated = await adapter.authenticate()
        if not authenticated:
            logger.error("认证失败")
            return
        
        logger.info("认证成功")
        
        # 获取交易所信息
        logger.info("获取交易所信息...")
        exchange_info = await adapter.get_exchange_info()
        logger.info(f"支持的交易对数: {len(exchange_info.supported_symbols)}")
        logger.info(f"支持的交易对: {exchange_info.supported_symbols[:5]}")  # 显示前 5 个
        
        # 获取行情数据
        if exchange_info.supported_symbols:
            symbol = exchange_info.supported_symbols[0]
            logger.info(f"获取 {symbol} 的行情数据...")
            ticker = await adapter.get_ticker(symbol)
            logger.info(f"最新价格: {ticker.last}")
            logger.info(f"买价: {ticker.bid}")
            logger.info(f"卖价: {ticker.ask}")
        
        # 获取账户信息
        logger.info("获取账户信息...")
        balance = await adapter.get_balance()
        logger.info(f"账户资产数: {len(balance)}")
        for currency, bal in list(balance.items())[:3]:
            logger.info(f"{currency}: 可用={bal.free}, 冻结={bal.used}, 总计={bal.total}")
        
        # 获取持仓
        logger.info("获取持仓...")
        positions = await adapter.get_positions()
        logger.info(f"持仓数: {len(positions)}")
        for symbol, pos in list(positions.items())[:3]:
            logger.info(f"{symbol}: 方向={pos.side}, 数量={pos.quantity}, 杠杆={pos.leverage}")
        
        # 获取开放订单
        logger.info("获取开放订单...")
        open_orders = await adapter.get_open_orders()
        logger.info(f"开放订单数: {len(open_orders)}")
        for order in open_orders[:3]:
            logger.info(f"订单 {order.order_id}: {order.symbol} {order.side} {order.quantity} @ {order.price}")
        
        # 健康检查
        logger.info("进行健康检查...")
        health = await adapter.health_check()
        logger.info(f"健康状态: {health}")
        
    except Exception as e:
        logger.error(f"发生错误: {e}", exc_info=True)
    finally:
        # 断开连接
        logger.info("断开连接...")
        await adapter.disconnect()
        logger.info("已断开连接")


if __name__ == "__main__":
    asyncio.run(main())
