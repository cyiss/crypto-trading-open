#!/usr/bin/env python3
"""
WEEX Bot 控制器 - 控制浏览器中的油猴脚本进行网格交易

这个脚本通过 WebSocket 或 HTTP 与浏览器中的油猴脚本通信，
实现远程控制网格交易。
"""

import asyncio
import json
import logging
import uuid
from typing import Dict, Any, Optional

import aiohttp
import websockets

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WEEXBotController:
    """WEEX Bot 控制器"""

    def __init__(
        self,
        ws_url: str = "ws://localhost:8765",
        http_url: str = "http://localhost:8080",
        use_websocket: bool = True,
    ):
        """
        初始化控制器

        Args:
            ws_url: WebSocket 服务器地址
            http_url: HTTP 服务器地址
            use_websocket: 是否使用 WebSocket（否则使用 HTTP）
        """
        self.ws_url = ws_url
        self.http_url = http_url
        self.use_websocket = use_websocket
        self.ws_connection = None
        self.pending_responses: Dict[str, asyncio.Future] = {}
        self.is_connected = False

    async def connect(self) -> bool:
        """连接到油猴脚本"""
        if self.use_websocket:
            return await self._connect_websocket()
        else:
            return await self._connect_http()

    async def _connect_websocket(self) -> bool:
        """连接到 WebSocket 服务器"""
        try:
            logger.info(f"连接到 WebSocket: {self.ws_url}")
            self.ws_connection = await websockets.connect(self.ws_url)
            self.is_connected = True
            logger.info("WebSocket 连接成功")

            # 启动消息接收循环
            asyncio.create_task(self._receive_websocket_messages())
            return True

        except Exception as e:
            logger.error(f"WebSocket 连接失败: {e}")
            self.is_connected = False
            return False

    async def _connect_http(self) -> bool:
        """连接到 HTTP 服务器"""
        try:
            logger.info(f"连接到 HTTP: {self.http_url}")
            # HTTP 不需要持久连接，只需验证服务器可访问
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.http_url}/health") as resp:
                    if resp.status == 200:
                        self.is_connected = True
                        logger.info("HTTP 连接成功")
                        return True
                    else:
                        logger.error(f"HTTP 服务器返回状态码: {resp.status}")
                        return False

        except Exception as e:
            logger.error(f"HTTP 连接失败: {e}")
            self.is_connected = False
            return False

    async def _receive_websocket_messages(self):
        """接收 WebSocket 消息"""
        try:
            async for message in self.ws_connection:
                try:
                    data = json.loads(message)
                    message_id = data.get('id')

                    if message_id in self.pending_responses:
                        future = self.pending_responses.pop(message_id)
                        future.set_result(data)
                    else:
                        logger.info(f"收到消息: {data}")

                except json.JSONDecodeError:
                    logger.error(f"无法解析消息: {message}")

        except websockets.exceptions.ConnectionClosed:
            logger.warning("WebSocket 连接已关闭")
            self.is_connected = False

        except Exception as e:
            logger.error(f"接收消息时出错: {e}")
            self.is_connected = False

    async def _send_websocket_command(
        self,
        command: str,
        **kwargs
    ) -> Dict[str, Any]:
        """发送 WebSocket 命令"""
        if not self.is_connected:
            raise RuntimeError("未连接到 WebSocket 服务器")

        message_id = str(uuid.uuid4())
        message = {
            'id': message_id,
            'command': command,
            **kwargs
        }

        # 创建响应 Future
        response_future = asyncio.Future()
        self.pending_responses[message_id] = response_future

        try:
            # 发送命令
            await self.ws_connection.send(json.dumps(message))
            logger.info(f"发送命令: {command}")

            # 等待响应（超时 30 秒）
            response = await asyncio.wait_for(response_future, timeout=30)
            logger.info(f"收到响应: {response}")
            return response

        except asyncio.TimeoutError:
            logger.error(f"命令超时: {command}")
            self.pending_responses.pop(message_id, None)
            raise

        except Exception as e:
            logger.error(f"发送命令失败: {e}")
            self.pending_responses.pop(message_id, None)
            raise

    async def _send_http_command(
        self,
        command: str,
        **kwargs
    ) -> Dict[str, Any]:
        """发送 HTTP 命令"""
        if not self.is_connected:
            raise RuntimeError("未连接到 HTTP 服务器")

        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.http_url}/command/{command}"
                async with session.post(url, json=kwargs) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        logger.info(f"收到响应: {data}")
                        return data
                    else:
                        error_text = await resp.text()
                        logger.error(f"HTTP 错误 {resp.status}: {error_text}")
                        raise RuntimeError(f"HTTP 错误 {resp.status}")

        except Exception as e:
            logger.error(f"发送命令失败: {e}")
            raise

    async def send_command(
        self,
        command: str,
        **kwargs
    ) -> Dict[str, Any]:
        """发送命令（自动选择 WebSocket 或 HTTP）"""
        if self.use_websocket:
            return await self._send_websocket_command(command, **kwargs)
        else:
            return await self._send_http_command(command, **kwargs)

    async def start_grid_trading(
        self,
        symbol: str = "cmt_btcusdt",
        grid_levels: int = 5,
        grid_spacing: float = 1000,
    ) -> Dict[str, Any]:
        """启动网格交易"""
        logger.info(f"启动网格交易: {symbol}, {grid_levels} 档, 间距 {grid_spacing}")
        return await self.send_command(
            'start_grid_trading',
            symbol=symbol,
            gridLevels=grid_levels,
            gridSpacing=grid_spacing,
        )

    async def stop_grid_trading(self) -> Dict[str, Any]:
        """停止网格交易"""
        logger.info("停止网格交易")
        return await self.send_command('stop_grid_trading')

    async def get_account_info(self) -> Dict[str, Any]:
        """获取账户信息"""
        logger.info("获取账户信息")
        return await self.send_command('get_account_info')

    async def get_ticker(self, symbol: str = "cmt_btcusdt") -> Dict[str, Any]:
        """获取行情"""
        logger.info(f"获取行情: {symbol}")
        return await self.send_command('get_ticker', symbol=symbol)

    async def place_order(
        self,
        symbol: str,
        size: str,
        order_type: str,
        price: str,
        order_type_code: str = '0',
        match_price: str = '0',
    ) -> Dict[str, Any]:
        """下单"""
        logger.info(f"下单: {symbol} {size} {order_type} @ {price}")
        return await self.send_command(
            'place_order',
            symbol=symbol,
            size=size,
            type=order_type,
            price=price,
            orderType=order_type_code,
            matchPrice=match_price,
        )

    async def cancel_order(
        self,
        symbol: str,
        order_id: str,
    ) -> Dict[str, Any]:
        """撤单"""
        logger.info(f"撤单: {symbol} {order_id}")
        return await self.send_command(
            'cancel_order',
            symbol=symbol,
            orderId=order_id,
        )

    async def get_status(self) -> Dict[str, Any]:
        """获取状态"""
        logger.info("获取状态")
        return await self.send_command('get_status')

    async def disconnect(self):
        """断开连接"""
        if self.use_websocket and self.ws_connection:
            await self.ws_connection.close()
            self.is_connected = False
            logger.info("WebSocket 已断开")


async def main():
    """主函数 - 演示如何使用控制器"""

    # 创建控制器（使用 WebSocket）
    controller = WEEXBotController(
        ws_url="ws://localhost:8765",
        use_websocket=True,
    )

    try:
        # 连接到油猴脚本
        if not await controller.connect():
            logger.error("连接失败")
            return

        # 等待连接建立
        await asyncio.sleep(1)

        # 获取状态
        status = await controller.get_status()
        logger.info(f"当前状态: {status}")

        # 获取账户信息
        account = await controller.get_account_info()
        logger.info(f"账户信息: {account}")

        # 获取行情
        ticker = await controller.get_ticker("cmt_btcusdt")
        logger.info(f"BTC 行情: {ticker}")

        # 启动网格交易
        logger.info("启动网格交易...")
        result = await controller.start_grid_trading(
            symbol="cmt_btcusdt",
            grid_levels=5,
            grid_spacing=1000,
        )
        logger.info(f"网格交易结果: {result}")

        # 运行 30 秒
        await asyncio.sleep(30)

        # 停止网格交易
        logger.info("停止网格交易...")
        result = await controller.stop_grid_trading()
        logger.info(f"停止结果: {result}")

        # 获取最终状态
        status = await controller.get_status()
        logger.info(f"最终状态: {status}")

    except Exception as e:
        logger.error(f"错误: {e}")

    finally:
        await controller.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
