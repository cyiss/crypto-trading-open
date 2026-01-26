#!/usr/bin/env python3
"""
WEEX WebSocket 后端服务器

此服务器作为Python后端与浏览器油猴脚本之间的通信桥梁。
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional

try:
    import websockets
except ImportError:
    print("正在安装 websockets 库...")
    import subprocess
    subprocess.run(["sudo", "pip3", "install", "websockets"], check=True)
    import websockets

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WeexWebSocketServer:
    """WEEX WebSocket 服务器"""

    def __init__(self, host: str = "0.0.0.0", port: int = 8766):
        self.host = host
        self.port = port
        self.clients = set()
        self.last_response: Optional[Dict[str, Any]] = None
        self.response_event = asyncio.Event()

    async def register(self, websocket):
        """注册新的客户端连接"""
        self.clients.add(websocket)
        logger.info(f"客户端已连接，当前连接数: {len(self.clients)}")

    async def unregister(self, websocket):
        """注销客户端连接"""
        self.clients.discard(websocket)
        logger.info(f"客户端已断开，当前连接数: {len(self.clients)}")

    async def send_command(self, command: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """向所有连接的客户端发送命令并等待响应"""
        if not self.clients:
            logger.warning("没有连接的客户端")
            return None

        self.response_event.clear()
        self.last_response = None

        message = json.dumps(command)
        logger.info(f"发送命令: {command.get('action', 'unknown')}")

        await asyncio.gather(
            *[client.send(message) for client in self.clients],
            return_exceptions=True
        )

        try:
            await asyncio.wait_for(self.response_event.wait(), timeout=10.0)
            return self.last_response
        except asyncio.TimeoutError:
            logger.warning("等待响应超时")
            return None

    async def handle_message(self, websocket, message: str):
        """处理来自客户端的消息"""
        try:
            data = json.loads(message)
            msg_type = data.get('type', 'unknown')

            if msg_type == 'connected':
                logger.info("油猴脚本已连接")
            elif msg_type == 'response':
                logger.info(f"收到响应: {data.get('action', 'unknown')}")
                self.last_response = data
                self.response_event.set()
            else:
                logger.info(f"收到消息: {data}")

        except json.JSONDecodeError:
            logger.error(f"无法解析消息: {message}")

    async def handler(self, websocket):
        """WebSocket连接处理器 - 新版websockets API"""
        await self.register(websocket)
        try:
            async for message in websocket:
                await self.handle_message(websocket, message)
        except websockets.exceptions.ConnectionClosed:
            logger.info("连接已关闭")
        finally:
            await self.unregister(websocket)

    async def start(self):
        """启动WebSocket服务器"""
        logger.info(f"启动WebSocket服务器: ws://{self.host}:{self.port}")
        async with websockets.serve(self.handler, self.host, self.port):
            await asyncio.Future()


class WeexTradingController:
    """WEEX 交易控制器"""

    def __init__(self, server: WeexWebSocketServer):
        self.server = server

    async def get_current_price(self) -> Dict[str, Any]:
        """获取当前价格"""
        return await self.server.send_command({"action": "get_price"})

    async def get_kline_data(self) -> Dict[str, Any]:
        """获取K线数据"""
        return await self.server.send_command({"action": "get_kline"})

    async def get_account_status(self) -> Dict[str, Any]:
        """获取账户状态"""
        return await self.server.send_command({"action": "get_account"})

    async def place_limit_order(self, side: str, price: float, quantity: int = 20) -> Dict[str, Any]:
        """下限价单"""
        return await self.server.send_command({
            "action": "place_order",
            "type": "limit",
            "side": side,
            "price": price,
            "quantity": quantity
        })

    async def place_market_order(self, side: str, quantity: int = 20) -> Dict[str, Any]:
        """下市价单"""
        return await self.server.send_command({
            "action": "place_order",
            "type": "market",
            "side": side,
            "quantity": quantity
        })

    async def cancel_all_orders(self) -> Dict[str, Any]:
        """撤销所有订单"""
        return await self.server.send_command({"action": "cancel_all"})

    async def close_position(self, symbol: str = "BTCUSDT") -> Dict[str, Any]:
        """平仓"""
        return await self.server.send_command({
            "action": "close_position",
            "symbol": symbol,
            "type": "market"
        })

    async def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return await self.server.send_command({"action": "get_stats"})


async def interactive_demo(controller: WeexTradingController):
    """交互式演示"""
    logger.info("\n" + "=" * 50)
    logger.info("WEEX 交易控制器 - 交互式演示")
    logger.info("=" * 50)
    logger.info("等待浏览器连接...")
    logger.info("请在浏览器中执行: weexBot.connect()")
    logger.info("=" * 50 + "\n")

    # 等待客户端连接
    while not controller.server.clients:
        await asyncio.sleep(1)

    logger.info("客户端已连接，开始演示...\n")
    await asyncio.sleep(1)

    # 1. 获取当前价格
    logger.info("--- 步骤 1: 获取当前价格 ---")
    result = await controller.get_current_price()
    if result:
        logger.info(f"结果: {json.dumps(result.get('result', {}), indent=2)}")
    await asyncio.sleep(1)

    # 2. 获取K线数据
    logger.info("\n--- 步骤 2: 获取K线数据 ---")
    result = await controller.get_kline_data()
    if result:
        logger.info(f"结果: {json.dumps(result.get('result', {}), indent=2)}")
    await asyncio.sleep(1)

    # 3. 获取账户状态
    logger.info("\n--- 步骤 3: 获取账户状态 ---")
    result = await controller.get_account_status()
    if result:
        logger.info(f"结果: {json.dumps(result.get('result', {}), indent=2)}")
    await asyncio.sleep(1)

    # 4. 下限价买单
    logger.info("\n--- 步骤 4: 下限价买单 (87000 USDT, 20张) ---")
    result = await controller.place_limit_order("buy", 87000, 20)
    if result:
        logger.info(f"结果: {json.dumps(result.get('result', {}), indent=2)}")
    await asyncio.sleep(1)

    # 5. 获取统计信息
    logger.info("\n--- 步骤 5: 获取统计信息 ---")
    result = await controller.get_stats()
    if result:
        logger.info(f"结果: {json.dumps(result.get('result', {}), indent=2, default=str)}")

    logger.info("\n" + "=" * 50)
    logger.info("演示完成！服务器继续运行中...")
    logger.info("=" * 50 + "\n")


async def main():
    """主函数"""
    server = WeexWebSocketServer()
    controller = WeexTradingController(server)

    await asyncio.gather(
        server.start(),
        interactive_demo(controller)
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("服务器已停止")
