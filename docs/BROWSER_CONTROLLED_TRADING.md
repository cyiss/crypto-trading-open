# 浏览器控制的网格交易 - 完整指南

## 概述

这个系统允许您通过 Python 后端代码远程控制浏览器中的油猴脚本，实现自动化的网格交易。

### 架构

```
Python 后端 (dev_weex)
    ↓
WebSocket 服务器
    ↓
浏览器中的油猴脚本
    ↓
WEEX API
```

## 系统组件

### 1. 油猴脚本 (Tampermonkey Script)
- **文件**: `weex_trading_controlled_tampermonkey.js`
- **功能**: 在浏览器中运行，执行交易操作
- **特点**: 
  - 使用浏览器真实会话
  - 自动生成 HMAC-SHA256 签名
  - 接收 WebSocket 命令

### 2. WebSocket 服务器
- **文件**: `weex_websocket_server.py`
- **功能**: 充当 Python 和浏览器之间的通信桥梁
- **特点**:
  - 支持多个浏览器客户端
  - 消息转发和路由
  - 响应存储

### 3. Bot 控制器
- **文件**: `weex_bot_controller.py`
- **功能**: Python 后端用来控制油猴脚本
- **特点**:
  - 简单易用的 API
  - 支持异步操作
  - 自动重连

## 安装和配置

### 步骤 1: 安装 Tampermonkey

**Chrome/Edge**:
1. 访问 [Chrome Web Store](https://chrome.google.com/webstore/detail/tampermonkey/dhdgffkkebhmkfjojejmpbldmpobp55f)
2. 点击"添加至 Chrome"

**Firefox**:
1. 访问 [Firefox Add-ons](https://addons.mozilla.org/firefox/addon/tampermonkey/)
2. 点击"添加到 Firefox"

### 步骤 2: 安装油猴脚本

1. 点击 Tampermonkey 图标
2. 选择"创建新脚本"
3. 删除默认内容
4. 复制 `weex_trading_controlled_tampermonkey.js` 的全部内容
5. 粘贴到编辑器
6. 按 `Ctrl+S` 保存

### 步骤 3: 启动 WebSocket 服务器

```bash
# 在项目目录中运行
python3 examples/weex_websocket_server.py
```

输出应该显示：
```
2026-01-25 17:00:00 - __main__ - INFO - 启动 WebSocket 服务器: ws://0.0.0.0:8765
2026-01-25 17:00:00 - __main__ - INFO - WebSocket 服务器已启动
```

### 步骤 4: 运行 Python 控制器

```bash
# 在项目目录中运行
python3 examples/weex_bot_controller.py
```

## 使用方法

### 方法 1: 直接在浏览器中使用

在浏览器控制台（F12）中：

```javascript
// 连接到 WebSocket 服务器
window.WEEXBot.connectWebSocket()

// 启动网格交易
await window.WEEXBot.executeGridTrading('cmt_btcusdt', 5, 1000)

// 停止网格交易
await window.WEEXBot.stopGridTrading()

// 获取状态
window.WEEXBot.getState()
```

### 方法 2: 通过 Python 后端控制

```python
import asyncio
from examples.weex_bot_controller import WEEXBotController

async def main():
    # 创建控制器
    controller = WEEXBotController(
        ws_url="ws://localhost:8765",
        use_websocket=True,
    )
    
    # 连接到油猴脚本
    if await controller.connect():
        # 启动网格交易
        result = await controller.start_grid_trading(
            symbol="cmt_btcusdt",
            grid_levels=5,
            grid_spacing=1000,
        )
        print(f"结果: {result}")
        
        # 运行 30 秒
        await asyncio.sleep(30)
        
        # 停止网格交易
        result = await controller.stop_grid_trading()
        print(f"停止结果: {result}")
        
        # 断开连接
        await controller.disconnect()

asyncio.run(main())
```

## API 参考

### 油猴脚本 API

#### 交易操作

```javascript
// 获取账户信息
await window.WEEXBot.getAccountInfo()

// 获取行情
await window.WEEXBot.getTicker('cmt_btcusdt')

// 下单
await window.WEEXBot.placeOrder(
    'cmt_btcusdt',  // 交易对
    '0.01',         // 数量
    '1',            // 类型: 1=开多, 2=开空, 3=平多, 4=平空
    '50000',        // 价格
    '0',            // 订单类型: 0=普通, 1=只做maker, 2=全部成交或立即取消, 3=立即成交并取消剩余
    '0'             // 匹配价格: 0=限价, 1=市价
)

// 撤单
await window.WEEXBot.cancelOrder('cmt_btcusdt', 'order_id')

// 执行网格交易
await window.WEEXBot.executeGridTrading('cmt_btcusdt', 5, 1000)

// 停止网格交易
await window.WEEXBot.stopGridTrading()
```

#### 控制操作

```javascript
// 连接到 WebSocket 服务器
window.WEEXBot.connectWebSocket()

// 发送 WebSocket 消息
window.WEEXBot.sendWebSocketMessage({
    type: 'command',
    command: 'start_grid_trading',
    symbol: 'cmt_btcusdt',
    gridLevels: 5,
    gridSpacing: 1000,
})

// 通过 HTTP 处理命令
await window.WEEXBot.handleHttpCommand('start_grid_trading', {
    symbol: 'cmt_btcusdt',
    gridLevels: 5,
    gridSpacing: 1000,
})
```

#### 状态查询

```javascript
// 获取完整状态
window.WEEXBot.getState()

// 获取统计信息
window.WEEXBot.getStats()

// 获取网格交易状态
window.WEEXBot.getGridStatus()

// 获取配置
window.WEEXBot.getConfig()

// 修改配置
window.WEEXBot.setConfig({
    defaultSymbol: 'cmt_ethusdt',
    defaultGridLevels: 10,
})
```

### Python 控制器 API

```python
controller = WEEXBotController(ws_url="ws://localhost:8765")

# 连接
await controller.connect()

# 启动网格交易
await controller.start_grid_trading(
    symbol="cmt_btcusdt",
    grid_levels=5,
    grid_spacing=1000,
)

# 停止网格交易
await controller.stop_grid_trading()

# 获取账户信息
await controller.get_account_info()

# 获取行情
await controller.get_ticker("cmt_btcusdt")

# 下单
await controller.place_order(
    symbol="cmt_btcusdt",
    size="0.01",
    order_type="1",
    price="50000",
)

# 撤单
await controller.cancel_order("cmt_btcusdt", "order_id")

# 获取状态
await controller.get_status()

# 断开连接
await controller.disconnect()
```

## 完整示例

### 示例 1: 简单的网格交易

```python
import asyncio
from examples.weex_bot_controller import WEEXBotController

async def simple_grid_trading():
    controller = WEEXBotController()
    
    try:
        # 连接
        await controller.connect()
        
        # 启动网格交易
        result = await controller.start_grid_trading(
            symbol="cmt_btcusdt",
            grid_levels=5,
            grid_spacing=1000,
        )
        print(f"网格交易已启动: {result}")
        
        # 运行 1 小时
        await asyncio.sleep(3600)
        
        # 停止
        result = await controller.stop_grid_trading()
        print(f"网格交易已停止: {result}")
        
    finally:
        await controller.disconnect()

asyncio.run(simple_grid_trading())
```

### 示例 2: 监控和自动调整

```python
import asyncio
from examples.weex_bot_controller import WEEXBotController

async def monitored_grid_trading():
    controller = WEEXBotController()
    
    try:
        await controller.connect()
        
        # 启动网格交易
        await controller.start_grid_trading(
            symbol="cmt_btcusdt",
            grid_levels=5,
            grid_spacing=1000,
        )
        
        # 每 5 分钟检查一次状态
        for i in range(12):  # 运行 1 小时
            await asyncio.sleep(300)
            
            status = await controller.get_status()
            print(f"[{i+1}/12] 状态: {status['result']['stats']}")
            
            # 如果失败订单过多，停止交易
            if status['result']['stats']['failedOrders'] > 10:
                print("失败订单过多，停止交易")
                await controller.stop_grid_trading()
                break
        
        # 最后停止
        await controller.stop_grid_trading()
        
    finally:
        await controller.disconnect()

asyncio.run(monitored_grid_trading())
```

### 示例 3: 多交易对网格交易

```python
import asyncio
from examples.weex_bot_controller import WEEXBotController

async def multi_symbol_trading():
    controller = WEEXBotController()
    
    try:
        await controller.connect()
        
        symbols = ['cmt_btcusdt', 'cmt_ethusdt', 'cmt_bnbusdt']
        
        for symbol in symbols:
            print(f"启动 {symbol} 网格交易")
            
            await controller.start_grid_trading(
                symbol=symbol,
                grid_levels=3,
                grid_spacing=500,
            )
            
            # 每个交易对运行 30 分钟
            await asyncio.sleep(1800)
            
            await controller.stop_grid_trading()
            print(f"停止 {symbol} 网格交易")
            
            # 等待 5 分钟再开始下一个
            await asyncio.sleep(300)
        
    finally:
        await controller.disconnect()

asyncio.run(multi_symbol_trading())
```

## 故障排除

### 问题 1: 无法连接到 WebSocket

**症状**: `连接失败` 或 `连接超时`

**解决方案**:
1. 确认 WebSocket 服务器已启动
2. 确认端口 8765 未被占用
3. 检查防火墙设置
4. 确认油猴脚本已安装并启用

### 问题 2: 油猴脚本不工作

**症状**: 浏览器控制台无法访问 `window.WEEXBot`

**解决方案**:
1. 刷新页面（Ctrl+R）
2. 检查 Tampermonkey 是否已启用
3. 检查脚本是否已保存
4. 查看浏览器控制台错误信息

### 问题 3: 命令无响应

**症状**: 发送命令后没有收到响应

**解决方案**:
1. 检查浏览器是否在线
2. 检查 WebSocket 连接状态
3. 查看浏览器控制台日志
4. 尝试重新连接

### 问题 4: 订单失败

**症状**: 下单返回 521 错误

**解决方案**:
1. 检查 WEEX 服务状态
2. 确认 API 密钥正确
3. 检查账户余额
4. 查看浏览器网络日志

## 安全建议

1. **不要分享脚本** - 包含 API 密钥
2. **使用 HTTPS** - 生产环境使用 HTTPS
3. **限制访问** - 只允许受信任的 IP 访问
4. **定期更新** - 定期更新 API 密钥
5. **监控活动** - 定期检查账户活动

## 性能优化

1. **减少请求频率** - 避免频繁调用 API
2. **使用缓存** - 缓存行情数据
3. **异步操作** - 使用 async/await 处理并发
4. **错误处理** - 添加重试机制
5. **日志记录** - 记录所有操作

## 常见问题

### Q: 可以同时运行多个网格交易吗？
A: 可以，只需在不同的浏览器标签页中运行不同的脚本，或修改脚本支持多个交易对。

### Q: 如何监控交易进度？
A: 使用 `get_status()` 获取实时状态，包括订单数量、成功率等。

### Q: 如何自动止损？
A: 在 Python 控制器中添加监控逻辑，当价格下跌超过阈值时自动停止交易。

### Q: 脚本支持哪些交易对？
A: 支持所有 WEEX 支持的交易对，只需修改 `symbol` 参数。

## 更新日志

### v2.0.0 (2026-01-25)
- 添加 WebSocket 控制功能
- 添加 Python 控制器
- 添加 WebSocket 服务器
- 支持远程控制网格交易
- 添加状态监控
- 添加统计信息

### v1.0.0 (2026-01-25)
- 初始版本
- 基础网格交易功能
- 可视化控制面板

## 许可证

MIT License

---

**最后更新**: 2026-01-25  
**版本**: 2.0.0  
**作者**: Manus Trading Bot
