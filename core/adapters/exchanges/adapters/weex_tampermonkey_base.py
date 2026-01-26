"""
WEEX油猴适配器 - 基础模块

通过WebSocket与浏览器中的油猴脚本通信，实现WEEX交易所的交易功能。
这是一个特殊的适配器，不直接调用交易所API，而是通过油猴脚本在浏览器中执行操作。
"""

import asyncio
import json
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from decimal import Decimal
from dataclasses import dataclass
from enum import Enum

import websockets
from websockets.server import WebSocketServerProtocol

from ..interface import ExchangeConfig, ExchangeStatus


class WeexCommandType(Enum):
    """WEEX命令类型"""
    GET_PRICE = "get_price"
    GET_KLINE = "get_kline"
    GET_ACCOUNT = "get_account"
    GET_POSITIONS = "get_positions"
    GET_ORDERS = "get_orders"
    PLACE_ORDER = "place_order"
    CANCEL_ORDER = "cancel_order"
    CANCEL_ALL = "cancel_all"
    CLOSE_POSITION = "close_position"
    SWITCH_SYMBOL = "switch_symbol"


@dataclass
class WeexCommand:
    """WEEX命令数据结构"""
    id: str
    action: str
    params: Dict[str, Any]
    timestamp: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "action": self.action,
            "params": self.params,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class WeexResponse:
    """WEEX响应数据结构"""
    id: str
    success: bool
    result: Optional[Dict[str, Any]]
    error: Optional[str]
    timestamp: datetime


class WeexTampermonkeyBase:
    """
    WEEX油猴适配器基础类
    
    负责管理与油猴脚本的WebSocket通信。
    """
    
    def __init__(self, config: ExchangeConfig, logger=None):
        """
        初始化基础类
        
        Args:
            config: 交易所配置
            logger: 日志记录器
        """
        self.config = config
        self.logger = logger
        
        # WebSocket服务器配置
        self.ws_host = config.extra_params.get('ws_host', '0.0.0.0')
        self.ws_port = config.extra_params.get('ws_port', 8766)
        self.command_timeout = config.extra_params.get('command_timeout', 10)
        
        # 连接管理
        self._server = None
        self._clients: List[WebSocketServerProtocol] = []
        self._connected = False
        self._running = False
        
        # 命令管理
        self._pending_commands: Dict[str, asyncio.Future] = {}
        self._command_lock = asyncio.Lock()
        
        # 当前交易对
        self._current_symbol = config.extra_params.get('default_symbol', 'BTCUSDT')
        
        # 缓存数据
        self._last_price: Optional[Decimal] = None
        self._last_ticker: Optional[Dict] = None
        self._last_positions: List[Dict] = []
        self._last_orders: List[Dict] = []
        
    @property
    def is_connected(self) -> bool:
        """检查是否有客户端连接"""
        return len(self._clients) > 0
    
    async def start_server(self) -> bool:
        """
        启动WebSocket服务器
        
        Returns:
            bool: 是否启动成功
        """
        try:
            self._running = True
            self._server = await websockets.serve(
                self._handle_client,
                self.ws_host,
                self.ws_port
            )
            
            if self.logger:
                self.logger.info(f"WEEX油猴WebSocket服务器已启动: ws://{self.ws_host}:{self.ws_port}")
            
            return True
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"启动WebSocket服务器失败: {e}")
            return False
    
    async def stop_server(self) -> None:
        """停止WebSocket服务器"""
        self._running = False
        
        # 关闭所有客户端连接
        for client in self._clients:
            try:
                await client.close()
            except Exception:
                pass
        
        self._clients.clear()
        
        # 关闭服务器
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        
        if self.logger:
            self.logger.info("WEEX油猴WebSocket服务器已停止")
    
    async def _handle_client(self, websocket: WebSocketServerProtocol, path: str = None) -> None:
        """
        处理客户端连接
        
        Args:
            websocket: WebSocket连接
            path: 连接路径
        """
        # 注册客户端
        self._clients.append(websocket)
        if self.logger:
            self.logger.info(f"油猴脚本已连接，当前连接数: {len(self._clients)}")
        
        try:
            async for message in websocket:
                await self._handle_message(websocket, message)
        except websockets.exceptions.ConnectionClosed:
            if self.logger:
                self.logger.info("油猴脚本连接已关闭")
        except Exception as e:
            if self.logger:
                self.logger.error(f"处理消息时出错: {e}")
        finally:
            # 注销客户端
            if websocket in self._clients:
                self._clients.remove(websocket)
            if self.logger:
                self.logger.info(f"油猴脚本已断开，当前连接数: {len(self._clients)}")
    
    async def _handle_message(self, websocket: WebSocketServerProtocol, message: str) -> None:
        """
        处理接收到的消息
        
        Args:
            websocket: WebSocket连接
            message: 消息内容
        """
        try:
            data = json.loads(message)
            msg_type = data.get('type', '')
            
            if msg_type == 'response':
                # 处理命令响应
                cmd_id = data.get('id')
                if cmd_id and cmd_id in self._pending_commands:
                    future = self._pending_commands.pop(cmd_id)
                    if not future.done():
                        future.set_result(data)
            
            elif msg_type == 'event':
                # 处理事件推送
                await self._handle_event(data)
            
            elif msg_type == 'heartbeat':
                # 心跳响应
                await websocket.send(json.dumps({
                    "type": "heartbeat_ack",
                    "timestamp": datetime.now().isoformat()
                }))
            
            elif msg_type == 'connected':
                # 连接确认
                if self.logger:
                    self.logger.info("油猴脚本连接已确认")
                    
        except json.JSONDecodeError as e:
            if self.logger:
                self.logger.error(f"解析消息失败: {e}")
        except Exception as e:
            if self.logger:
                self.logger.error(f"处理消息失败: {e}")
    
    async def _handle_event(self, data: Dict[str, Any]) -> None:
        """
        处理事件推送
        
        Args:
            data: 事件数据
        """
        event_type = data.get('event')
        
        if event_type == 'price_update':
            # 价格更新
            self._last_price = Decimal(str(data.get('price', 0)))
            
        elif event_type == 'order_update':
            # 订单更新
            pass
            
        elif event_type == 'position_update':
            # 持仓更新
            pass
    
    async def send_command(
        self,
        action: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """
        发送命令到油猴脚本
        
        Args:
            action: 命令动作
            params: 命令参数
            timeout: 超时时间（秒）
            
        Returns:
            命令响应结果
        """
        if not self._clients:
            if self.logger:
                self.logger.warning("没有可用的油猴脚本连接")
            return None
        
        # 创建命令
        cmd_id = str(uuid.uuid4())
        command = WeexCommand(
            id=cmd_id,
            action=action,
            params=params or {},
            timestamp=datetime.now()
        )
        
        # 创建Future等待响应
        future = asyncio.get_event_loop().create_future()
        self._pending_commands[cmd_id] = future
        
        try:
            # 发送命令到所有客户端（通常只有一个）
            message = json.dumps(command.to_dict())
            for client in self._clients:
                await client.send(message)
            
            # 等待响应
            actual_timeout = timeout or self.command_timeout
            result = await asyncio.wait_for(future, timeout=actual_timeout)
            return result
            
        except asyncio.TimeoutError:
            if self.logger:
                self.logger.warning(f"命令 {action} 响应超时")
            return None
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"发送命令失败: {e}")
            return None
            
        finally:
            # 清理
            if cmd_id in self._pending_commands:
                del self._pending_commands[cmd_id]
    
    async def wait_for_connection(self, timeout: float = 60) -> bool:
        """
        等待油猴脚本连接
        
        Args:
            timeout: 超时时间（秒）
            
        Returns:
            bool: 是否连接成功
        """
        start_time = datetime.now()
        
        while (datetime.now() - start_time).total_seconds() < timeout:
            if self._clients:
                return True
            await asyncio.sleep(0.5)
        
        return False
    
    def get_current_symbol(self) -> str:
        """获取当前交易对"""
        return self._current_symbol
    
    def set_current_symbol(self, symbol: str) -> None:
        """设置当前交易对"""
        self._current_symbol = symbol
