# WEEX 交易所适配器

本文档介绍如何使用 WEEX 交易所适配器。

## 概述

WEEX 是一个中心化的永续合约交易所。本适配器提供了与 WEEX 交易所的完整集成，支持以下功能：

- **市场数据**: 获取行情、订单簿、K线数据
- **账户管理**: 查询余额、持仓、订单
- **交易执行**: 下单、撤单、批量撤单
- **实时推送**: WebSocket 订阅行情、订单、持仓更新

## 配置

### 基础配置

```python
from core.adapters.exchanges.interface import ExchangeConfig, ExchangeType
from core.adapters.exchanges.adapters import WeexAdapter

config = ExchangeConfig(
    exchange_id="weex",
    name="WEEX",
    exchange_type=ExchangeType.PERPETUAL_FUTURES,
    api_key="your_api_key",
    api_secret="your_api_secret",
    api_passphrase="your_api_passphrase",
    testnet=False,  # 设置为 True 使用测试网
    enable_websocket=True,
)

adapter = WeexAdapter(config)
```

### 环境变量配置

也可以通过环境变量配置：

```bash
export WEEX_API_KEY="your_api_key"
export WEEX_API_SECRET="your_api_secret"
export WEEX_API_PASSPHRASE="your_api_passphrase"
```

## 使用方法

### 连接和认证

```python
import asyncio

async def main():
    # 连接
    connected = await adapter.connect()
    if not connected:
        print("连接失败")
        return
    
    # 认证
    authenticated = await adapter.authenticate()
    if not authenticated:
        print("认证失败")
        return
    
    # 进行交易操作...
    
    # 断开连接
    await adapter.disconnect()

asyncio.run(main())
```

### 获取市场数据

```python
# 获取交易所信息
exchange_info = await adapter.get_exchange_info()
print(f"支持的交易对: {exchange_info.supported_symbols}")

# 获取行情
ticker = await adapter.get_ticker("cmt_btcusdt")
print(f"BTC/USDT 最新价: {ticker.last}")

# 获取订单簿
orderbook = await adapter.get_order_book("cmt_btcusdt", limit=20)
print(f"买价: {orderbook.bids[0].price}")
print(f"卖价: {orderbook.asks[0].price}")
```

### 账户管理

```python
# 获取余额
balance = await adapter.get_balance()
for currency, bal in balance.items():
    print(f"{currency}: {bal.total}")

# 获取持仓
positions = await adapter.get_positions()
for symbol, pos in positions.items():
    print(f"{symbol}: {pos.quantity} @ {pos.entry_price}")

# 获取订单
open_orders = await adapter.get_open_orders()
for order in open_orders:
    print(f"订单 {order.order_id}: {order.symbol} {order.side}")
```

### 交易执行

```python
from core.adapters.exchanges.models import OrderSide, OrderType
from decimal import Decimal

# 创建限价单
order = await adapter.create_order(
    symbol="cmt_btcusdt",
    side=OrderSide.BUY,
    order_type=OrderType.LIMIT,
    quantity=Decimal("0.1"),
    price=Decimal("50000")
)
print(f"订单已创建: {order.order_id}")

# 创建市价单
order = await adapter.create_order(
    symbol="cmt_btcusdt",
    side=OrderSide.SELL,
    order_type=OrderType.MARKET,
    quantity=Decimal("0.1")
)

# 取消订单
cancelled = await adapter.cancel_order("cmt_btcusdt", order.order_id)
print(f"订单已取消: {cancelled.order_id}")

# 取消所有订单
cancelled_orders = await adapter.cancel_all_orders("cmt_btcusdt")
print(f"已取消 {len(cancelled_orders)} 个订单")
```

### WebSocket 订阅

```python
# 订阅行情
async def on_ticker(ticker):
    print(f"{ticker.symbol}: {ticker.last}")

await adapter.subscribe_ticker("cmt_btcusdt", on_ticker)

# 订阅订单簿
async def on_orderbook(book):
    print(f"买价: {book.bids[0].price}, 卖价: {book.asks[0].price}")

await adapter.subscribe_order_book("cmt_btcusdt", on_orderbook)

# 订阅用户数据（订单、持仓、余额）
async def on_user_data(data):
    print(f"用户数据更新: {data}")

await adapter.subscribe_user_data(on_user_data)

# 保持连接
await asyncio.sleep(3600)  # 运行 1 小时

await adapter.disconnect()
```

## API 文档

### 交易对格式

WEEX 使用以下格式的交易对：

- 永续合约: `cmt_btcusdt`, `cmt_ethusdt` 等

适配器会自动将标准格式（如 `BTC/USDT`, `BTC-USDT`）转换为 WEEX 格式。

### 支持的订单类型

- `OrderType.LIMIT`: 限价单
- `OrderType.MARKET`: 市价单

### 支持的订单方向

- `OrderSide.BUY`: 买入
- `OrderSide.SELL`: 卖出

## 错误处理

```python
from core.adapters.exchanges.adapters import WeexAdapter

try:
    ticker = await adapter.get_ticker("cmt_btcusdt")
except Exception as e:
    print(f"获取行情失败: {e}")
```

## 限制

- **连接限制**: 300 次连接请求/IP/5 分钟，单个 IP 最多 100 个连接
- **订阅限制**: 240 次/小时/连接，单个连接最多 100 个频道
- **请求超时**: 默认 10 秒

## 测试账号

项目提供了一个测试账号供开发使用：

- **APIKey**: weex_d0649c112185fb5a0aeb13846fe915ac
- **SecretKey**: a041e89a40dba5c2a8ae80ec12d2a51ece7026ab378f21bad74fcb1e984f3a61
- **Phrase**: manus_auto

## 参考资源

- [WEEX API 文档](https://www.weex.com/api-doc/zh-CN/contract/Websocket/websocket-intro)
- [WEEX 官方网站](https://www.weex.com)

## 最佳实践

1. **错误处理**: 始终使用 try-except 包装 API 调用
2. **连接管理**: 在使用完后调用 `disconnect()` 关闭连接
3. **速率限制**: 注意 API 的速率限制，避免过于频繁的请求
4. **WebSocket 连接**: 使用 WebSocket 订阅实时数据而不是轮询
5. **日志记录**: 启用日志记录以便调试问题

## 贡献

如有任何问题或建议，欢迎提交 Issue 或 Pull Request。
