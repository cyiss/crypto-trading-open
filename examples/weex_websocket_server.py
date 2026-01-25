#!/usr/bin/env python3
"""
WEEX WebSocket 服务器 - 接收来自 Python 的命令并转发到浏览器

这个服务器充当中间人，接收来自 Python 后端的命令，
然后通过 WebSocket 转发给浏览器中的油猴脚本。
"""

import asyncio
import json
import logging
from typing import Set

import websockets
from websockets.server import WebSocketServerProtocol

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WEEXWebSocketServer:
    """WEEX WebSocket 服务器"""

    def __init__(self, host: str = "localhost", port: int = 8765):
        """
        初始化服务器

        Args:
            host: 服务器地址
            port: 服务器端口
        """
        self.host = host
        self.port = port
        self.clients: Set[WebSocketServerProtocol] = set()
        self.pending_responses = {}

    async def register_client(self, websocket: WebSocketServerProtocol):
        """注册客户端"""
        self.clients.add(websocket)
        logger.info(f"客户端已连接: {websocket.remote_address}")
        logger.info(f"当前连接数: {len(self.clients)}")

    async def unregister_client(self, websocket: WebSocketServerProtocol):
        """注销客户端"""
        self.clients.discard(websocket)
        logger.info(f"客户端已断开: {websocket.remote_address}")
        logger.info(f"当前连接数: {len(self.clients)}")

    async def broadcast_message(self, message: dict):
        """广播消息给所有客户端"""
        if not self.clients:
            logger.warning("没有连接的客户端")
            return

        message_json = json.dumps(message)
        for client in self.clients:
            try:
                await client.send(message_json)
                logger.info(f"发送消息给 {client.remote_address}: {message}")
            except Exception as e:
                logger.error(f"发送消息失败: {e}")

    async def send_to_client(
        self,
        websocket: WebSocketServerProtocol,
        message: dict
    ):
        """发送消息给特定客户端"""
        try:
            await websocket.send(json.dumps(message))
            logger.info(f"发送消息给 {websocket.remote_address}: {message}")
        except Exception as e:
            logger.error(f"发送消息失败: {e}")

    async def handle_client(self, websocket: WebSocketServerProtocol, path: str):
        """处理客户端连接"""
        await self.register_client(websocket)

        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    logger.info(f"收到消息: {data}")

                    # 如果是响应消息，存储它
                    if 'id' in data and 'result' in data:
                        message_id = data['id']
                        self.pending_responses[message_id] = data
                        logger.info(f"收到响应: {message_id}")

                    # 广播消息给其他客户端
                    for client in self.clients:
                        if client != websocket:
                            await self.send_to_client(client, data)

                except json.JSONDecodeError:
                    logger.error(f"无法解析消息: {message}")

        except websockets.exceptions.ConnectionClosed:
            logger.info("客户端连接已关闭")

        except Exception as e:
            logger.error(f"处理客户端时出错: {e}")

        finally:
            await self.unregister_client(websocket)

    async def start(self):
        """启动服务器"""
        logger.info(f"启动 WebSocket 服务器: ws://{self.host}:{self.port}")

        async with websockets.serve(self.handle_client, self.host, self.port):
            logger.info("WebSocket 服务器已启动")
            await asyncio.Future()  # 永远运行


async def main():
    """主函数"""
    server = WEEXWebSocketServer(host="0.0.0.0", port=8765)
    await server.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("服务器已停止")
