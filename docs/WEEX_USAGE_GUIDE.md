# WEEX 交易系统使用指南

本指南详细说明如何使用 WEEX 统一交易系统，包括网格交易、刷量交易、套利监控、波动率扫描和价格提醒等功能。

## 目录

1. [系统概述](#系统概述)
2. [快速开始](#快速开始)
3. [功能模块](#功能模块)
4. [配置说明](#配置说明)
5. [API 参考](#api-参考)
6. [常见问题](#常见问题)

---

## 系统概述

WEEX 交易系统采用**浏览器端（油猴脚本）+ Python后端**的架构：

- **油猴脚本**：运行在浏览器中，负责与 WEEX 网页交互，执行实际的下单、撤单等操作
- **Python 后端**：运行交易策略逻辑，通过 WebSocket 向油猴脚本发送交易指令

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           WEEX 交易系统架构                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      Python 后端 (策略层)                            │   │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐   │   │
│  │  │ 网格交易    │ │ 刷量交易    │ │ 套利监控    │ │ 波动率扫描  │   │   │
│  │  │ GridTrading │ │ VolumeMaker │ │ Arbitrage   │ │ Scanner     │   │   │
│  │  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └──────┬──────┘   │   │
│  │         │               │               │               │          │   │
│  │  ┌──────┴───────────────┴───────────────┴───────────────┴──────┐   │   │
│  │  │                  统一交易控制器 (WeexController)              │   │   │
│  │  └──────────────────────────┬──────────────────────────────────┘   │   │
│  │                             │                                      │   │
│  │  ┌──────────────────────────┴──────────────────────────────────┐   │   │
│  │  │              WebSocket 服务器 (ws://localhost:8766)          │   │   │
│  │  └──────────────────────────┬──────────────────────────────────┘   │   │
│  └─────────────────────────────┼──────────────────────────────────────┘   │
│                                │                                          │
│                          WebSocket                                        │
│                                │                                          │
│  ┌─────────────────────────────┼──────────────────────────────────────┐   │
│  │                      浏览器端 (执行层)                              │   │
│  │  ┌──────────────────────────┴──────────────────────────────────┐   │   │
│  │  │              油猴脚本 (weex_unified_bot.user.js)             │   │   │
│  │  └──────────────────────────┬──────────────────────────────────┘   │   │
│  │                             │                                      │   │
│  │  ┌──────────────────────────┴──────────────────────────────────┐   │   │
│  │  │                    WEEX 交易页面 DOM                         │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  └────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 功能模块

| 模块 | 功能描述 |
|------|----------|
| 网格交易 | 在价格区间内自动挂买卖单，赚取网格利润 |
| 刷量交易 | 快速双向交易，增加交易量 |
| 套利监控 | 监控多交易所价差，发现套利机会 |
| 波动率扫描 | 扫描市场波动率，推荐适合网格的标的 |
| 价格提醒 | 监控价格变动，触发条件时发出提醒 |

---

## 快速开始

### 1. 安装油猴脚本

1. 安装 [Tampermonkey](https://www.tampermonkey.net/) 浏览器扩展
2. 点击 Tampermonkey 图标 → 添加新脚本
3. 将 `examples/weex_unified_bot.user.js` 的内容粘贴进去
4. 保存脚本 (Ctrl+S)

### 2. 安装 Python 依赖

```bash
cd crypto-trading-open
pip install websockets pyyaml
```

### 3. 启动交易服务器

```bash
# 使用默认配置
python examples/weex_trading_server.py

# 使用自定义配置
python examples/weex_trading_server.py config/weex/trading_config.yaml
```

### 4. 连接浏览器

1. 打开 WEEX 永续合约页面：https://www.weex.com/futures/BTC-USDT
2. 登录您的 WEEX 账户
3. 按 F12 打开开发者工具，在控制台执行：

```javascript
weexBot.connect('ws://localhost:8766')
```

### 5. 开始交易

连接成功后，Python 后端会根据配置自动启动相应的交易系统。

---

## 功能模块

### 1. 网格交易系统

网格交易通过在设定价格区间内布置买卖订单，在价格波动中赚取利润。

**工作原理**：
1. 在当前价格下方挂买单
2. 在当前价格上方挂卖单
3. 买单成交后，在上一格挂卖单
4. 卖单成交后，在下一格挂买单
5. 循环往复，赚取网格利润

**配置示例**：

```yaml
grid_trading:
  enabled: true
  symbol: "BTCUSDT"
  lower_price: 85000      # 价格下限
  upper_price: 95000      # 价格上限
  grid_count: 10          # 网格数量
  order_amount: 20        # 每格下单数量（张）
  leverage: 20            # 杠杆倍数
```

**手动控制**（在浏览器控制台）：

```javascript
// 获取网格状态
weexBot.getStats()

// 手动下限价买单
await weexBot.placeLimitBuy(87000, 20)

// 手动下限价卖单
await weexBot.placeLimitSell(89000, 20)
```

### 2. 刷量交易系统

刷量交易通过快速双向交易来增加交易量。

**配置示例**：

```yaml
volume_maker:
  enabled: true
  symbol: "BTCUSDT"
  order_size: 20          # 单笔订单大小（张）
  interval: 10            # 交易间隔（秒）
  spread_tolerance: 0.001 # 价差容忍度（0.1%）
  daily_target: 1000000   # 日目标交易量
```

### 3. 套利监控系统

监控 WEEX 与其他交易所的价差，发现套利机会。

**配置示例**：

```yaml
arbitrage:
  enabled: true
  symbol: "BTCUSDT"
  min_spread: 0.005       # 最小价差阈值（0.5%）
  order_size: 20          # 套利单大小
  auto_execute: false     # 是否自动执行
```

**注意**：套利系统需要外部数据源提供其他交易所的价格。可以通过以下方式设置参考价格：

```python
# 在 Python 后端设置参考价格
app.arbitrage.set_reference_price("binance", Decimal("88000"))
```

### 4. 波动率扫描器

扫描多个交易对的波动率，推荐适合网格交易的标的。

**配置示例**：

```yaml
volatility_scanner:
  enabled: true
  symbols:
    - "BTCUSDT"
    - "ETHUSDT"
    - "SOLUSDT"
  scan_interval: 300      # 扫描间隔（秒）
  min_volatility: 0.01    # 最小波动率（1%）
  max_volatility: 0.10    # 最大波动率（10%）
```

### 5. 价格提醒系统

监控价格变动，达到设定条件时发出提醒。

**配置示例**：

```yaml
price_alert:
  enabled: true
  symbol: "BTCUSDT"
  upper_limit: 100000     # 价格上限
  lower_limit: 80000      # 价格下限
  change_threshold: 0.02  # 变动阈值（2%）
  check_interval: 5       # 检查间隔（秒）
```

---

## 配置说明

### 配置文件位置

```
config/weex/trading_config.yaml
```

### 完整配置示例

```yaml
# 网格交易
grid_trading:
  enabled: true
  symbol: "BTCUSDT"
  grid_type: "normal"     # normal/follow_long/follow_short
  lower_price: 85000
  upper_price: 95000
  grid_count: 10
  order_amount: 20
  leverage: 20

# 刷量交易
volume_maker:
  enabled: false
  symbol: "BTCUSDT"
  order_size: 20
  interval: 10
  spread_tolerance: 0.001
  daily_target: 1000000

# 套利监控
arbitrage:
  enabled: false
  symbol: "BTCUSDT"
  min_spread: 0.005
  order_size: 20
  auto_execute: false

# 波动率扫描
volatility_scanner:
  enabled: false
  symbols: ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
  scan_interval: 300
  min_volatility: 0.01
  max_volatility: 0.10

# 价格提醒
price_alert:
  enabled: true
  symbol: "BTCUSDT"
  upper_limit: 100000
  lower_limit: 80000
  change_threshold: 0.02
  check_interval: 5

# WebSocket 服务器
websocket:
  host: "0.0.0.0"
  port: 8766
  timeout: 10
```

---

## API 参考

### 油猴脚本 API

在浏览器控制台中可以直接调用以下方法：

```javascript
// 连接 WebSocket 服务器
weexBot.connect('ws://localhost:8766')

// 获取当前价格
await weexBot.getCurrentPrice()

// 获取 K 线数据
await weexBot.getKlineData()

// 获取账户状态
await weexBot.getAccountStatus()

// 下限价买单
await weexBot.placeLimitBuy(price, quantity)

// 下限价卖单
await weexBot.placeLimitSell(price, quantity)

// 下市价买单
await weexBot.placeMarketBuy(quantity)

// 下市价卖单
await weexBot.placeMarketSell(quantity)

// 撤销所有订单
await weexBot.cancelAllOrders()

// 平仓
await weexBot.closePosition(symbol)

// 获取统计信息
weexBot.getStats()
```

### WebSocket 命令格式

**请求格式**：

```json
{
    "id": "unique-request-id",
    "action": "place_order",
    "params": {
        "type": "limit",
        "side": "buy",
        "price": 87000,
        "quantity": 20
    },
    "timestamp": "2026-01-26T12:00:00.000Z"
}
```

**响应格式**：

```json
{
    "type": "response",
    "id": "unique-request-id",
    "action": "place_order",
    "result": {
        "success": true,
        "type": "limit",
        "side": "buy",
        "price": 87000,
        "quantity": 20
    },
    "timestamp": "2026-01-26T12:00:00.100Z"
}
```

### 支持的命令

| 命令 | 描述 | 参数 |
|------|------|------|
| `get_price` | 获取当前价格 | - |
| `get_kline` | 获取K线数据 | - |
| `get_account` | 获取账户状态 | - |
| `get_orders` | 获取挂单信息 | - |
| `place_order` | 下单 | type, side, price, quantity |
| `cancel_order` | 撤单 | order_id |
| `cancel_all` | 撤销所有订单 | - |
| `close_position` | 平仓 | symbol, type |
| `get_stats` | 获取统计信息 | - |

---

## 常见问题

### Q: 为什么需要使用油猴脚本？

A: WEEX 交易所没有提供公开的 API 接口，因此需要通过浏览器端的油猴脚本来模拟用户操作，实现自动化交易。

### Q: 如何确保交易安全？

A: 
1. 油猴脚本只在浏览器本地运行，不会泄露您的账户信息
2. 所有交易操作都通过您已登录的浏览器会话执行
3. 建议先使用小额资金测试

### Q: WebSocket 连接失败怎么办？

A:
1. 确保 Python 后端已启动
2. 检查端口 8766 是否被占用
3. 确保浏览器允许连接本地 WebSocket

### Q: 如何查看交易日志？

A:
1. Python 后端日志会输出到控制台
2. 浏览器控制台 (F12) 可以查看油猴脚本日志
3. 日志文件保存在 `logs/weex_trading.log`

### Q: 如何停止交易？

A:
1. 在 Python 后端按 Ctrl+C 停止服务器
2. 或在浏览器控制台执行 `weexBot.disconnect()`

---

## 风险提示

**加密货币交易具有高风险，请注意以下事项**：

1. 本系统仅供学习和研究使用
2. 请勿使用超出您承受能力的资金进行交易
3. 网格交易在单边行情中可能产生亏损
4. 杠杆交易会放大盈亏，请谨慎使用
5. 请确保了解所有交易策略的风险后再使用

---

## 更新日志

### v1.0.0 (2026-01-26)

- 初始版本发布
- 支持网格交易、刷量交易、套利监控、波动率扫描、价格提醒
- 完整的 WebSocket 通信协议
- 详细的配置文件支持
