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

# 🔥 加载环境变量（必须在其他导入之前）
from dotenv import load_dotenv
from pathlib import Path as EnvPath
env_path = EnvPath(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

import sys
import asyncio
import yaml
import signal
from pathlib import Path
from decimal import Decimal

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core.adapters.exchanges.utils import setup_optimized_logging
from core.adapters.exchanges.models import ExchangeType
from core.adapters.exchanges import ExchangeFactory, ExchangeConfig
from core.services.grid.terminal_ui import GridTerminalUI
from core.services.grid.coordinator import GridCoordinator
from core.services.grid.implementations import (
    GridStrategyImpl,
    GridEngineImpl,
    PositionTrackerImpl
)
from core.services.grid.models import GridConfig, GridType, GridState
from core.logging import get_system_logger, get_logger

# 🔥 配置优化的日志系统（简洁清晰，不丢失信息）
setup_optimized_logging(use_colored=True)


async def load_config(config_path: str) -> dict:
    """
    加载配置文件
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        配置字典
    """
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return config
    except Exception as e:
        print(f"❌ 加载配置文件失败: {e}")
        raise


def create_grid_config(config_data: dict) -> GridConfig:
    """
    从WEEX配置格式创建GridConfig对象
    
    Args:
        config_data: 配置数据
        
    Returns:
        网格配置对象
    """
    # 从WEEX配置格式转换为GridConfig格式
    symbol = config_data.get('symbol', 'BTCUSDT')
    grid = config_data.get('grid', {})
    order = config_data.get('order', {})
    leverage_config = config_data.get('leverage', {})
    risk = config_data.get('risk', {})
    
    # 确定网格类型
    grid_type_str = grid.get('type', 'arithmetic')
    if grid_type_str == 'arithmetic':
        grid_type = GridType.LONG  # 默认做多网格
    else:
        grid_type = GridType.LONG
    
    # 计算网格间隔
    upper_price = Decimal(str(grid.get('upper_price', 110000)))
    lower_price = Decimal(str(grid.get('lower_price', 80000)))
    grid_count = grid.get('count', 20)
    grid_interval = (upper_price - lower_price) / grid_count
    
    # 构建参数
    params = {
        'exchange': 'weex',
        'symbol': symbol,
        'grid_type': grid_type,
        'lower_price': lower_price,
        'upper_price': upper_price,
        'grid_interval': grid_interval,
        'order_amount': Decimal(str(order.get('size', 20))),
        'leverage': leverage_config.get('multiplier', 20),
        'margin_mode': leverage_config.get('margin_mode', 'cross'),
        'quantity_precision': 0,  # WEEX使用张为单位，整数
        'price_decimals': 1,
    }
    
    # 止盈配置
    take_profit = risk.get('take_profit', {})
    if take_profit.get('enabled', False):
        params['take_profit_enabled'] = True
        params['take_profit_percentage'] = Decimal(str(take_profit.get('percentage', 0.05)))
    
    # 止损配置
    stop_loss = risk.get('stop_loss', {})
    if stop_loss.get('enabled', False):
        params['stop_loss_protection_enabled'] = True
        # 止损触发百分比（从网格顶部往不利方向移动的百分比）
        params['stop_loss_trigger_percent'] = Decimal(str(stop_loss.get('percentage', 0.10) * 100))
    
    # 本金保护配置
    capital_protection = risk.get('capital_protection', {})
    if capital_protection.get('enabled', False):
        params['capital_protection_enabled'] = True
        params['capital_protection_trigger_percent'] = int(capital_protection.get('threshold', 0.20) * 100)
    
    return GridConfig(**params)


async def create_weex_adapter():
    """
    创建WEEX交易所适配器
    
    Returns:
        WEEX适配器实例
    """
    exchange_config = ExchangeConfig(
        exchange_id="weex",
        name="WEEX",
        exchange_type=ExchangeType.PERPETUAL,
        api_key="",  # WEEX通过浏览器登录，不需要API密钥
        api_secret="",
        testnet=False,
        default_leverage=20,
        enable_websocket=False,  # 使用油猴脚本通信
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
    
    # 使用工厂创建适配器
    factory = ExchangeFactory()
    adapter = factory.create_adapter(
        exchange_id="weex",
        config=exchange_config
    )
    
    return adapter


async def main(config_path: str = "config/grid/weex_grid_config.yaml"):
    """
    主函数
    
    Args:
        config_path: 配置文件路径
    """
    print("=" * 70)
    print("🎯 WEEX 网格交易系统启动")
    print("=" * 70)
    
    logger = get_system_logger()
    exchange_adapter = None
    coordinator = None
    
    try:
        # 1. 加载配置
        print("\n📋 步骤 1/6: 加载配置文件...")
        config_data = await load_config(config_path)
        grid_config = create_grid_config(config_data)
        print(f"✅ 配置加载成功")
        print(f"   - 交易所: WEEX")
        print(f"   - 交易对: {grid_config.symbol}")
        print(f"   - 网格类型: {grid_config.grid_type.value}")
        print(f"   - 价格区间: ${grid_config.lower_price:,.2f} - ${grid_config.upper_price:,.2f}")
        print(f"   - 网格间隔: ${grid_config.grid_interval}")
        print(f"   - 网格数量: {grid_config.grid_count}个")
        print(f"   - 订单数量: {grid_config.order_amount}张")
        
        # 2. 创建交易所适配器
        print("\n🔌 步骤 2/6: 创建WEEX适配器...")
        exchange_adapter = await create_weex_adapter()
        print(f"✅ WEEX适配器创建成功")
        
        # 3. 连接交易所（启动WebSocket服务器）
        print("\n🌐 步骤 3/6: 启动WebSocket服务器...")
        await exchange_adapter.connect()
        print(f"✅ WebSocket服务器已启动")
        print("")
        print("=" * 70)
        print("⏳ 等待油猴脚本连接...")
        print("   请在浏览器中执行: weexBot.connect('ws://localhost:8766')")
        print("=" * 70)
        print("")
        
        # 等待油猴脚本连接
        while not exchange_adapter.is_browser_connected():
            await asyncio.sleep(1)
        
        print("✅ 油猴脚本已连接")
        
        # 验证登录状态
        authenticated = await exchange_adapter.authenticate()
        if not authenticated:
            print("⚠️  WEEX未登录，请在浏览器中登录后继续")
            print("   等待登录...")
            
            while True:
                await asyncio.sleep(5)
                authenticated = await exchange_adapter.authenticate()
                if authenticated:
                    print("✅ WEEX登录成功")
                    break
        else:
            print("✅ WEEX已登录")
        
        # 4. 创建核心组件
        print("\n⚙️  步骤 4/6: 初始化核心组件...")
        
        # 创建策略
        strategy = GridStrategyImpl()
        print("   ✓ 网格策略已创建")
        
        # 创建执行引擎
        engine = GridEngineImpl(exchange_adapter)
        print("   ✓ 执行引擎已创建")
        
        # 创建网格状态
        grid_state = GridState()
        
        # 创建持仓跟踪器
        tracker = PositionTrackerImpl(grid_config, grid_state)
        print("   ✓ 持仓跟踪器已创建")
        
        # 5. 创建协调器
        print("\n🎮 步骤 5/6: 创建系统协调器...")
        coordinator = GridCoordinator(
            config=grid_config,
            strategy=strategy,
            engine=engine,
            tracker=tracker,
            grid_state=grid_state
        )
        print("✅ 协调器创建成功")
        
        # 6. 启动网格系统
        print("\n🚀 步骤 6/6: 启动网格系统...")
        print(f"   - 准备批量挂单：{grid_config.grid_count}个订单")
        print(f"   - 覆盖价格区间：${grid_config.lower_price:,.2f} - ${grid_config.upper_price:,.2f}")
        
        await coordinator.start()
        print("✅ 网格系统已启动")
        print(f"   - 已成功挂出{grid_config.grid_count}个订单")
        print(f"   - 所有网格已就位，等待成交...")
        
        # 启动终端界面
        print("\n🖥️  启动监控界面...")
        terminal_ui = GridTerminalUI(coordinator)
        
        print("=" * 70)
        print("✅ WEEX 网格交易系统完全启动")
        print("=" * 70)
        print()
        
        # 运行终端界面
        await terminal_ui.run()
        
    except KeyboardInterrupt:
        print("\n\n⚠️  收到退出信号，正在停止系统...")
        
    except Exception as e:
        logger.error(f"❌ 系统错误: {e}", exc_info=True)
        print(f"\n❌ 系统错误: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # 清理资源
        print("\n🧹 正在清理资源...")
        try:
            if coordinator:
                await coordinator.stop()
                print("   ✓ 协调器已停止")
            
            if exchange_adapter:
                await exchange_adapter.disconnect()
                print("   ✓ 交易所连接已断开")
                
        except Exception as e:
            print(f"   ⚠️  清理时出错: {e}")
        
        print("✅ 系统已关闭")


if __name__ == "__main__":
    # 获取配置文件路径
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config/grid/weex_grid_config.yaml"
    
    # 运行主函数
    asyncio.run(main(config_path))
