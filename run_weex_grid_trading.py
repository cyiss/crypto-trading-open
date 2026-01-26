#!/usr/bin/env python3
"""
WEEX网格交易系统启动脚本

使用WEEX油猴适配器运行网格交易策略。
通过浏览器中的油猴脚本执行实际的交易操作。

使用方法:
    python run_weex_grid_trading.py [配置文件路径]
    
示例:
    python run_weex_grid_trading.py config/grid/weex_grid_config.yaml
"""

import asyncio
import sys
import signal
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core.logging import get_logger, setup_logging
from core.adapters.exchanges import ExchangeFactory, ExchangeConfig, ExchangeType
from core.services.grid.coordinator.grid_coordinator import GridCoordinator


# 全局变量
logger = None
coordinator = None
exchange = None


async def main(config_path: str = None):
    """
    主函数
    
    Args:
        config_path: 配置文件路径
    """
    global logger, coordinator, exchange
    
    # 设置日志
    setup_logging()
    logger = get_logger(__name__)
    
    logger.info("=" * 60)
    logger.info("WEEX 网格交易系统启动")
    logger.info("=" * 60)
    
    try:
        # 创建交易所工厂
        factory = ExchangeFactory()
        
        # 创建WEEX适配器配置
        config = ExchangeConfig(
            exchange_id="weex",
            name="WEEX",
            exchange_type=ExchangeType.PERPETUAL,
            api_key="",  # WEEX通过浏览器登录，不需要API密钥
            api_secret="",
            testnet=False,
            default_leverage=20,
            enable_websocket=False,
            extra_params={
                "ws_host": "0.0.0.0",
                "ws_port": 8766,
                "command_timeout": 10,
                "connection_timeout": 300,
                "default_symbol": "BTCUSDT",
                "poll_interval": 1.0,
                "user_data_poll_interval": 5.0
            }
        )
        
        # 创建WEEX适配器
        logger.info("正在创建WEEX适配器...")
        exchange = factory.create_adapter("weex", config)
        
        if not exchange:
            logger.error("创建WEEX适配器失败")
            return
        
        # 连接到WEEX（启动WebSocket服务器）
        logger.info("正在启动WebSocket服务器...")
        connected = await exchange.connect()
        
        if not connected:
            logger.error("启动WebSocket服务器失败")
            return
        
        logger.info("")
        logger.info("=" * 60)
        logger.info("WebSocket服务器已启动，等待油猴脚本连接...")
        logger.info("请在浏览器中执行: weexBot.connect('ws://localhost:8766')")
        logger.info("=" * 60)
        logger.info("")
        
        # 等待油猴脚本连接
        while not exchange.is_browser_connected():
            await asyncio.sleep(1)
        
        logger.info("✅ 油猴脚本已连接")
        
        # 验证登录状态
        authenticated = await exchange.authenticate()
        if not authenticated:
            logger.warning("⚠️ WEEX未登录，请在浏览器中登录后继续")
            logger.info("等待登录...")
            
            # 等待用户登录
            while True:
                await asyncio.sleep(5)
                authenticated = await exchange.authenticate()
                if authenticated:
                    logger.info("✅ WEEX登录成功")
                    break
        
        # 加载网格配置
        if config_path:
            grid_config = load_grid_config(config_path)
        else:
            # 使用默认配置
            grid_config = get_default_grid_config()
        
        logger.info(f"网格配置: {grid_config}")
        
        # 创建网格协调器
        coordinator = GridCoordinator(
            exchange=exchange,
            config=grid_config,
            logger=logger
        )
        
        # 启动网格交易
        logger.info("正在启动网格交易...")
        await coordinator.start()
        
        # 保持运行
        logger.info("网格交易系统运行中，按 Ctrl+C 停止...")
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("收到停止信号...")
    except Exception as e:
        logger.error(f"运行出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await shutdown()


def load_grid_config(config_path: str) -> dict:
    """
    加载网格配置
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        配置字典
    """
    import yaml
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    return config


def get_default_grid_config() -> dict:
    """
    获取默认网格配置
    
    Returns:
        默认配置字典
    """
    return {
        "symbol": "BTCUSDT",
        "grid_type": "arithmetic",  # 等差网格
        "upper_price": 110000,      # 网格上限
        "lower_price": 80000,       # 网格下限
        "grid_count": 20,           # 网格数量
        "total_investment": 1000,   # 总投资额 (USDT)
        "order_size": 20,           # 每单数量 (张)
        "leverage": 20,             # 杠杆倍数
        "take_profit_percentage": 0.05,  # 止盈百分比 (5%)
        "stop_loss_percentage": 0.10,    # 止损百分比 (10%)
    }


async def shutdown():
    """关闭系统"""
    global coordinator, exchange, logger
    
    if logger:
        logger.info("正在关闭系统...")
    
    try:
        # 停止网格协调器
        if coordinator:
            await coordinator.stop()
        
        # 断开交易所连接
        if exchange:
            await exchange.disconnect()
            
    except Exception as e:
        if logger:
            logger.error(f"关闭时出错: {e}")
    
    if logger:
        logger.info("系统已关闭")


def signal_handler(sig, frame):
    """信号处理器"""
    print("\n收到中断信号，正在关闭...")
    asyncio.get_event_loop().stop()


if __name__ == "__main__":
    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 获取配置文件路径
    config_path = sys.argv[1] if len(sys.argv) > 1 else None
    
    # 运行主函数
    asyncio.run(main(config_path))
