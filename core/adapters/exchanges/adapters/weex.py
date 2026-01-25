"""
WEEX 交易所适配器

本文件实现 `ExchangeInterface`（通过继承 `ExchangeAdapter`），用于让 WEEX 以"统一交易所"的方式接入
当前系统的套利 / 网格 / 做市等模块。

### 文档来源
- WEEX API 文档: https://www.weex.com/api-doc/zh-CN/contract/Websocket/websocket-intro

### 关键协议/模型约定
- **REST API**: 基础 URL `https://api-contract.weex.com/capi/v2`
- **WebSocket**: 公有频道 `wss://ws-contract.weex.com/v2/ws/public`，私有频道 `wss://ws-contract.weex.com/v2/ws/private`
- **认证方式**: HMAC SHA256 签名 + Base64 编码
- **交易对格式**: `cmt_btcusdt` 等
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional

from ..adapter import ExchangeAdapter
from ..interface import ExchangeConfig
from ..models import (
    BalanceData,
    ExchangeInfo,
    ExchangeType,
    MarginMode,
    OHLCVData,
    OrderBookData,
    OrderBookLevel,
    OrderData,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionData,
    PositionSide,
    TickerData,
    TradeData,
)

from .weex_base import WeexBase, WeexEnv, datetime_to_unix_ms, unix_ms_to_datetime
from .weex_rest import WeexRest
from .weex_websocket import WeexWebSocket


class WeexAdapter(ExchangeAdapter):
    """
    WEEX 适配器（永续合约）

    结构分层（与其它交易所适配器保持一致）：
    - `WeexBase`：环境/域名/符号规范化/缓存容器
    - `WeexRest`：REST 调用（market/trade）+ API Key 认证
    - `WeexWebSocket`：WS 订阅（行情/订单/持仓）+ 推送分发
    """

    def __init__(self, config: ExchangeConfig, event_bus: Optional[Any] = None):
        super().__init__(config, event_bus)
        
        # 将统一配置对象转换为轻量 dict（供 WEEX 子模块读取）
        self._config_dict = self._convert_config_to_dict(config)
        self._base = WeexBase(self._config_dict)
        self._rest = WeexRest(self._config_dict)
        self._websocket = WeexWebSocket(self._config_dict) if config.enable_websocket else None

        # 暴露 base_url/ws_url（便于外部查看或调试）
        self.base_url = self._base.rest_endpoint
        self.ws_url = self._base.ws_endpoint

        # 缓存
        self._supported_symbols: List[str] = []
        self._market_info: Dict[str, Any] = {}
        self._order_cache: Dict[str, OrderData] = {}
        self._position_cache: Dict[str, PositionData] = {}

    def _convert_config_to_dict(self, config: ExchangeConfig) -> Dict[str, Any]:
        """
        将统一的 ExchangeConfig 转换为 WEEX 子模块可读的 dict
        """
        extra = dict(config.extra_params or {})
        if config.testnet and "env" not in extra:
            extra["env"] = "testnet"
        
        return {
            "exchange_id": config.exchange_id,
            "testnet": bool(config.testnet),
            "request_timeout": int(getattr(config, "request_timeout", 10) or 10),
            "enable_websocket": bool(getattr(config, "enable_websocket", True)),
            "api_key": config.api_key,
            "api_secret": config.api_secret,
            "api_passphrase": config.api_passphrase,
            "extra_params": extra,
        }

    # === 生命周期钩子 ===

    async def _do_connect(self) -> bool:
        """连接到交易所"""
        try:
            await self._refresh_contracts()
            return True
        except Exception as e:
            if self.logger:
                self.logger.warning(f"[WEEX] connect: 预热合约信息失败（不影响继续连接）: {e}")
            return True

    async def _do_disconnect(self) -> None:
        """断开与交易所的连接"""
        if self._websocket:
            await self._websocket.disconnect()
        await self._rest.close()

    async def _do_authenticate(self) -> bool:
        """进行身份认证"""
        try:
            # WEEX 认证是通过 API 签名完成的，这里简单验证一下
            await self._rest.get_account_info()
            return True
        except Exception as e:
            if self.logger:
                self.logger.error(f"[WEEX] authenticate failed: {e}")
            return False

    async def _do_health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            server_time = await self._rest.get_server_time()
            return {"ok": True, "server_time": server_time}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # === 市场数据接口 ===

    async def get_exchange_info(self) -> ExchangeInfo:
        """获取交易所信息"""
        await self._refresh_contracts()
        
        return ExchangeInfo(
            exchange_id=self.config.exchange_id,
            name=self.config.name,
            exchange_type=ExchangeType.PERPETUAL_FUTURES,
            markets=self._market_info,
            supported_symbols=self._supported_symbols,
            rate_limits={},
            precision={},
            features={
                "spot": False,
                "margin": False,
                "futures": True,
                "options": False,
            }
        )

    async def get_supported_symbols(self) -> List[str]:
        """获取支持的交易对"""
        if not self._supported_symbols:
            await self._refresh_contracts()
        return self._supported_symbols

    async def get_ticker(self, symbol: str) -> TickerData:
        """获取行情数据"""
        normalized_symbol = self._base.normalize_symbol(symbol)
        
        try:
            ticker = await self._rest.get_ticker(normalized_symbol)
            
            return TickerData(
                symbol=symbol,
                exchange=self.config.exchange_id,
                timestamp=datetime.now(timezone.utc),
                last=Decimal(str(ticker.get("lastPrice", 0))),
                bid=Decimal(str(ticker.get("bestBidPrice", 0))),
                ask=Decimal(str(ticker.get("bestAskPrice", 0))),
                high=Decimal(str(ticker.get("highPrice", 0))),
                low=Decimal(str(ticker.get("lowPrice", 0))),
                volume=Decimal(str(ticker.get("volume", 0))),
                quote_volume=Decimal(str(ticker.get("quoteAssetVolume", 0))),
            )
        except Exception as e:
            self.logger.error(f"获取行情失败: {symbol} - {e}")
            raise

    async def get_order_book(self, symbol: str, limit: int = 20) -> OrderBookData:
        """获取订单簿"""
        normalized_symbol = self._base.normalize_symbol(symbol)
        
        try:
            book = await self._rest.get_order_book(normalized_symbol, limit)
            
            bids = []
            for bid in book.get("bids", [])[:limit]:
                bids.append(OrderBookLevel(
                    price=Decimal(str(bid[0])),
                    quantity=Decimal(str(bid[1]))
                ))
            
            asks = []
            for ask in book.get("asks", [])[:limit]:
                asks.append(OrderBookLevel(
                    price=Decimal(str(ask[0])),
                    quantity=Decimal(str(ask[1]))
                ))
            
            return OrderBookData(
                symbol=symbol,
                exchange=self.config.exchange_id,
                timestamp=datetime.now(timezone.utc),
                bids=bids,
                asks=asks,
            )
        except Exception as e:
            self.logger.error(f"获取订单簿失败: {symbol} - {e}")
            raise

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1m",
        limit: int = 100,
        since: Optional[int] = None
    ) -> List[OHLCVData]:
        """获取 K 线数据"""
        # WEEX 的 K 线接口需要进一步实现
        raise NotImplementedError("WEEX 适配器暂未实现 get_ohlcv")

    # === 账户数据接口 ===

    async def get_balance(self) -> Dict[str, BalanceData]:
        """获取账户余额"""
        try:
            balance_info = await self._rest.get_balance()
            
            balances = {}
            for asset in balance_info.get("assets", []):
                currency = asset.get("currency", "").upper()
                if not currency:
                    continue
                
                balances[currency] = BalanceData(
                    currency=currency,
                    free=Decimal(str(asset.get("available", 0))),
                    used=Decimal(str(asset.get("hold", 0))),
                    total=Decimal(str(asset.get("total", 0))),
                )
            
            return balances
        except Exception as e:
            self.logger.error(f"获取余额失败: {e}")
            raise

    async def get_positions(self, symbol: Optional[str] = None) -> Dict[str, PositionData]:
        """获取持仓"""
        try:
            positions_data = await self._rest.get_positions(symbol)
            
            positions = {}
            for pos in positions_data:
                symbol_key = pos.get("symbol", "")
                if not symbol_key:
                    continue
                
                side = PositionSide.LONG if pos.get("side") == "long" else PositionSide.SHORT
                
                positions[symbol_key] = PositionData(
                    symbol=symbol_key,
                    side=side,
                    quantity=Decimal(str(pos.get("quantity", 0))),
                    entry_price=Decimal(str(pos.get("entryPrice", 0))),
                    current_price=Decimal(str(pos.get("currentPrice", 0))),
                    unrealized_pnl=Decimal(str(pos.get("unrealizedPnl", 0))),
                    margin=Decimal(str(pos.get("margin", 0))),
                    leverage=int(pos.get("leverage", 1)),
                )
            
            return positions
        except Exception as e:
            self.logger.error(f"获取持仓失败: {e}")
            raise

    # === 订单接口 ===

    async def create_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: Decimal,
        price: Optional[Decimal] = None,
        **kwargs
    ) -> OrderData:
        """创建订单"""
        normalized_symbol = self._base.normalize_symbol(symbol)
        
        try:
            order_side = "buy" if side == OrderSide.BUY else "sell"
            order_type_str = "limit" if order_type == OrderType.LIMIT else "market"
            
            result = await self._rest.place_order(
                symbol=normalized_symbol,
                side=order_side,
                order_type=order_type_str,
                quantity=str(quantity),
                price=str(price) if price else None,
                **kwargs
            )
            
            return self._to_order_data(result)
        except Exception as e:
            self.logger.error(f"创建订单失败: {symbol} - {e}")
            raise

    async def cancel_order(self, symbol: str, order_id: str) -> OrderData:
        """取消订单"""
        normalized_symbol = self._base.normalize_symbol(symbol)
        
        try:
            result = await self._rest.cancel_order(normalized_symbol, order_id)
            return self._to_order_data(result)
        except Exception as e:
            self.logger.error(f"取消订单失败: {symbol} {order_id} - {e}")
            raise

    async def cancel_all_orders(self, symbol: Optional[str] = None) -> List[OrderData]:
        """取消所有订单"""
        try:
            if symbol:
                normalized_symbol = self._base.normalize_symbol(symbol)
                orders = await self._rest.get_orders(normalized_symbol, status="open")
            else:
                # 获取所有开放订单
                symbols = await self.get_supported_symbols()
                orders = []
                for sym in symbols:
                    try:
                        sym_orders = await self._rest.get_orders(sym, status="open")
                        orders.extend(sym_orders)
                    except Exception:
                        continue
            
            cancelled_orders = []
            for order in orders:
                try:
                    order_id = order.get("orderId")
                    order_symbol = order.get("symbol")
                    if order_id and order_symbol:
                        result = await self._rest.cancel_order(order_symbol, order_id)
                        cancelled_orders.append(self._to_order_data(result))
                except Exception as e:
                    self.logger.warning(f"取消订单失败: {order.get('orderId')} - {e}")
            
            return cancelled_orders
        except Exception as e:
            self.logger.error(f"取消所有订单失败: {e}")
            raise

    async def get_order(self, symbol: str, order_id: str) -> OrderData:
        """获取订单信息"""
        normalized_symbol = self._base.normalize_symbol(symbol)
        
        try:
            result = await self._rest.get_order(normalized_symbol, order_id)
            return self._to_order_data(result)
        except Exception as e:
            self.logger.error(f"获取订单失败: {symbol} {order_id} - {e}")
            raise

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[OrderData]:
        """获取开放订单"""
        try:
            if symbol:
                normalized_symbol = self._base.normalize_symbol(symbol)
                orders = await self._rest.get_orders(normalized_symbol, status="open")
            else:
                orders = []
                symbols = await self.get_supported_symbols()
                for sym in symbols:
                    try:
                        sym_orders = await self._rest.get_orders(sym, status="open")
                        orders.extend(sym_orders)
                    except Exception:
                        continue
            
            return [self._to_order_data(order) for order in orders]
        except Exception as e:
            self.logger.error(f"获取开放订单失败: {e}")
            raise

    async def get_closed_orders(self, symbol: Optional[str] = None) -> List[OrderData]:
        """获取已关闭订单"""
        try:
            if symbol:
                normalized_symbol = self._base.normalize_symbol(symbol)
                orders = await self._rest.get_orders(normalized_symbol, status="closed")
            else:
                orders = []
                symbols = await self.get_supported_symbols()
                for sym in symbols:
                    try:
                        sym_orders = await self._rest.get_orders(sym, status="closed")
                        orders.extend(sym_orders)
                    except Exception:
                        continue
            
            return [self._to_order_data(order) for order in orders]
        except Exception as e:
            self.logger.error(f"获取已关闭订单失败: {e}")
            raise

    # === WebSocket 订阅接口 ===

    async def subscribe_ticker(self, symbol: str, callback: Callable) -> bool:
        """订阅行情"""
        if not self._websocket:
            return False
        
        normalized_symbol = self._base.normalize_symbol(symbol)
        channel = f"ticker:{normalized_symbol}"
        
        def wrapper(data: Dict[str, Any]) -> None:
            try:
                ticker = self._parse_ticker_data(data)
                if ticker:
                    callback(ticker)
            except Exception as e:
                self.logger.error(f"处理行情数据失败: {e}")
        
        return await self._websocket.subscribe(channel, wrapper)

    async def subscribe_order_book(self, symbol: str, callback: Callable, limit: int = 20) -> bool:
        """订阅订单簿"""
        if not self._websocket:
            return False
        
        normalized_symbol = self._base.normalize_symbol(symbol)
        channel = f"depth:{normalized_symbol}:{limit}"
        
        def wrapper(data: Dict[str, Any]) -> None:
            try:
                book = self._parse_orderbook_data(data)
                if book:
                    callback(book)
            except Exception as e:
                self.logger.error(f"处理订单簿数据失败: {e}")
        
        return await self._websocket.subscribe(channel, wrapper)

    async def subscribe_user_data(self, callback: Callable) -> bool:
        """订阅用户数据（订单、持仓、余额）"""
        if not self._websocket:
            return False
        
        # 订阅私有频道
        await self._websocket.connect_private()
        
        # 订阅订单更新
        await self._websocket.subscribe_private("order", callback)
        # 订阅持仓更新
        await self._websocket.subscribe_private("position", callback)
        # 订阅余额更新
        await self._websocket.subscribe_private("balance", callback)
        
        return True

    # === 内部辅助方法 ===

    async def _refresh_contracts(self) -> None:
        """刷新合约信息"""
        try:
            contracts = await self._rest.get_contracts_info()
            
            symbols = []
            market_info = {}
            
            for contract in contracts:
                symbol = contract.get("symbol", "")
                if symbol:
                    symbols.append(symbol)
                    market_info[symbol] = contract
            
            self._supported_symbols = sorted(symbols)
            self._market_info = market_info
        except Exception as e:
            self.logger.warning(f"刷新合约信息失败: {e}")

    def _to_order_data(self, order: Dict[str, Any]) -> OrderData:
        """将 WEEX 订单转换为统一的 OrderData"""
        status_map = {
            "open": OrderStatus.OPEN,
            "filled": OrderStatus.CLOSED,
            "cancelled": OrderStatus.CANCELLED,
            "rejected": OrderStatus.REJECTED,
        }
        
        side_map = {
            "buy": OrderSide.BUY,
            "sell": OrderSide.SELL,
        }
        
        order_type_map = {
            "limit": OrderType.LIMIT,
            "market": OrderType.MARKET,
        }
        
        return OrderData(
            order_id=str(order.get("orderId", "")),
            symbol=order.get("symbol", ""),
            exchange=self.config.exchange_id,
            side=side_map.get(order.get("side", ""), OrderSide.BUY),
            order_type=order_type_map.get(order.get("type", ""), OrderType.LIMIT),
            quantity=Decimal(str(order.get("quantity", 0))),
            price=Decimal(str(order.get("price", 0))) if order.get("price") else None,
            filled=Decimal(str(order.get("filled", 0))),
            status=status_map.get(order.get("status", ""), OrderStatus.OPEN),
            timestamp=unix_ms_to_datetime(order.get("createTime")),
            update_time=unix_ms_to_datetime(order.get("updateTime")),
            fee=Decimal(str(order.get("fee", 0))),
        )

    def _parse_ticker_data(self, data: Dict[str, Any]) -> Optional[TickerData]:
        """解析 WebSocket 行情数据"""
        try:
            return TickerData(
                symbol=data.get("symbol", ""),
                exchange=self.config.exchange_id,
                timestamp=datetime.now(timezone.utc),
                last=Decimal(str(data.get("lastPrice", 0))),
                bid=Decimal(str(data.get("bestBidPrice", 0))),
                ask=Decimal(str(data.get("bestAskPrice", 0))),
                high=Decimal(str(data.get("highPrice", 0))),
                low=Decimal(str(data.get("lowPrice", 0))),
                volume=Decimal(str(data.get("volume", 0))),
            )
        except Exception as e:
            self.logger.error(f"解析行情数据失败: {e}")
            return None

    def _parse_orderbook_data(self, data: Dict[str, Any]) -> Optional[OrderBookData]:
        """解析 WebSocket 订单簿数据"""
        try:
            bids = []
            for bid in data.get("bids", []):
                bids.append(OrderBookLevel(
                    price=Decimal(str(bid[0])),
                    quantity=Decimal(str(bid[1]))
                ))
            
            asks = []
            for ask in data.get("asks", []):
                asks.append(OrderBookLevel(
                    price=Decimal(str(ask[0])),
                    quantity=Decimal(str(ask[1]))
                ))
            
            return OrderBookData(
                symbol=data.get("symbol", ""),
                exchange=self.config.exchange_id,
                timestamp=datetime.now(timezone.utc),
                bids=bids,
                asks=asks,
            )
        except Exception as e:
            self.logger.error(f"解析订单簿数据失败: {e}")
            return None
