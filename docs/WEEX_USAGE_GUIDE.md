# WEEX 交易机器人使用指南

本指南将帮助您快速上手使用本项目在WEEX交易所进行自动化交易。

## 系统架构

```
┌─────────────────┐     WebSocket      ┌─────────────────┐
│  Python 后端    │◄──────────────────►│  浏览器油猴脚本  │
│  (策略逻辑)     │                    │  (交易执行)      │
└─────────────────┘                    └─────────────────┘
                                              │
                                              ▼
                                       ┌─────────────────┐
                                       │   WEEX 网页     │
                                       │   (交易界面)    │
                                       └─────────────────┘
```

## 前置准备

### 1. 安装浏览器扩展

在Chrome或Edge浏览器中安装 [Tampermonkey](https://www.tampermonkey.net/) 扩展。

### 2. 安装Python依赖

```bash
pip install websockets
```

### 3. 克隆项目

```bash
git clone -b dev_weex git@github.com:cyiss/crypto-trading-open.git
cd crypto-trading-open
```

## 快速开始

### 步骤1：安装油猴脚本

1. 打开Tampermonkey扩展，点击"添加新脚本"
2. 删除默认内容，将 `examples/weex_unified_bot.user.js` 的全部内容粘贴进去
3. 按 `Ctrl+S` 保存脚本
4. 确保脚本已启用

### 步骤2：启动Python后端服务器

```bash
cd examples
python weex_ws_server.py
```

服务器将在 `ws://localhost:8766` 启动并等待浏览器连接。

### 步骤3：打开WEEX交易页面

1. 在浏览器中访问 https://www.weex.com/futures/BTC-USDT
2. 登录您的WEEX账户
3. 打开浏览器开发者工具（F12），切换到Console标签页
4. 执行以下命令连接后端：

```javascript
weexBot.connect('ws://localhost:8766')
```

### 步骤4：开始交易

连接成功后，Python后端可以向浏览器发送交易命令。

## API 使用说明

### 浏览器端 API（在Console中使用）

```javascript
// 获取当前价格
await weexBot.getCurrentPrice()
// 返回: { success: true, price: 87800.5 }

// 获取K线数据
await weexBot.getKlineData()
// 返回: { success: true, data: { currentPrice, high24h, low24h, volume24h, fundingRate } }

// 获取账户状态
await weexBot.getAccountStatus()
// 返回: { success: true, data: { available, positions, openOrders } }

// 下限价买单（价格, 数量-张）
await weexBot.placeLimitBuy(87000, 20)

// 下限价卖单
await weexBot.placeLimitSell(88000, 20)

// 下市价买单（数量-张）
await weexBot.placeMarketBuy(20)

// 下市价卖单
await weexBot.placeMarketSell(20)

// 获取统计信息
weexBot.getStats()

// 重置状态
weexBot.reset()
```

### Python后端 API

```python
import asyncio
from weex_ws_server import WeexWebSocketServer, WeexTradingController

async def main():
    server = WeexWebSocketServer()
    controller = WeexTradingController(server)
    
    # 启动服务器（在后台运行）
    asyncio.create_task(server.start())
    
    # 等待浏览器连接
    while not server.clients:
        await asyncio.sleep(1)
    
    # 获取当前价格
    result = await controller.get_current_price()
    print(f"当前价格: {result}")
    
    # 获取K线数据
    result = await controller.get_kline_data()
    print(f"K线数据: {result}")
    
    # 下限价买单
    result = await controller.place_limit_order("buy", 87000, 20)
    print(f"下单结果: {result}")
    
    # 下市价卖单
    result = await controller.place_market_order("sell", 20)
    print(f"下单结果: {result}")

asyncio.run(main())
```

## 配置说明

### 油猴脚本配置

在 `weex_unified_bot.user.js` 文件开头修改配置：

```javascript
const CONFIG = {
    orderQuantity: 20,           // 默认下单数量（张）
    orderDelay: 800,             // 下单延迟（毫秒）
    debug: true,                 // 调试模式
    wsServerUrl: 'ws://localhost:8766'  // WebSocket服务器地址
};
```

### Python后端配置

在 `weex_ws_server.py` 中修改服务器配置：

```python
server = WeexWebSocketServer(host="0.0.0.0", port=8766)
```

## 集成到现有策略

如果您想将WEEX交易集成到现有的交易策略中，可以参考以下示例：

```python
import asyncio
from weex_ws_server import WeexWebSocketServer, WeexTradingController

class MyTradingStrategy:
    def __init__(self):
        self.server = WeexWebSocketServer()
        self.controller = WeexTradingController(self.server)
    
    async def start(self):
        # 启动WebSocket服务器
        asyncio.create_task(self.server.start())
        
        # 等待浏览器连接
        print("等待浏览器连接...")
        while not self.server.clients:
            await asyncio.sleep(1)
        print("浏览器已连接！")
        
        # 运行策略
        await self.run_strategy()
    
    async def run_strategy(self):
        while True:
            # 获取市场数据
            kline = await self.controller.get_kline_data()
            if kline and kline.get('result', {}).get('success'):
                price = kline['result']['data']['currentPrice']
                print(f"当前价格: {price}")
                
                # 在这里实现您的交易逻辑
                # 例如：网格交易、趋势跟踪等
                
            await asyncio.sleep(5)  # 每5秒检查一次

# 运行策略
strategy = MyTradingStrategy()
asyncio.run(strategy.start())
```

## 注意事项

1. **登录状态**：确保在WEEX网页上已登录账户，否则无法执行实际交易。

2. **网络要求**：WEEX可能对某些地区的IP有限制，请确保您的网络可以正常访问WEEX。

3. **风险提示**：自动化交易存在风险，请先使用小额资金测试，确认功能正常后再进行实际交易。

4. **浏览器保持打开**：交易执行依赖浏览器页面，请确保浏览器和WEEX页面保持打开状态。

5. **单位说明**：下单数量单位为"张"，每张代表一定价值的合约。

## 常见问题

### Q: 连接失败怎么办？

A: 请检查：
- Python后端服务器是否已启动
- 端口号是否一致（默认8766）
- 浏览器控制台是否有错误信息

### Q: 下单没有执行？

A: 请确认：
- 已登录WEEX账户
- 账户有足够的可用余额
- 页面上的下单按钮可以正常点击

### Q: 如何修改默认下单数量？

A: 在油猴脚本的CONFIG中修改 `orderQuantity` 值，或在调用下单函数时指定数量参数。

## 技术支持

如有问题，请在GitHub仓库提交Issue：
https://github.com/cyiss/crypto-trading-open/issues
