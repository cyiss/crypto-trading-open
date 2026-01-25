# WEEX Tampermonkey 交易脚本使用指南

## 概述

这是一个完整的 Tampermonkey（油猴）脚本，可以在浏览器中直接执行 WEEX 的交易操作。通过利用浏览器的真实会话和 Cookie，可以绕过某些 API 限制。

## 为什么使用 Tampermonkey？

### 优势

1. **使用浏览器真实会话** - 浏览器已经登录，有真实的会话信息
2. **绕过 API 限制** - 如果 REST API 有限制，可以通过浏览器访问
3. **自动签名** - 脚本自动生成 HMAC-SHA256 签名
4. **可视化界面** - 右下角控制面板，无需编码
5. **易于测试** - 快速测试交易策略

### 适用场景

- 测试网格交易策略
- 手动下单和撤单
- 获取账户信息
- 监控行情数据
- 自动化交易操作

## 安装步骤

### 1. 安装 Tampermonkey 浏览器扩展

**Chrome/Edge**:
1. 访问 [Chrome Web Store](https://chrome.google.com/webstore/detail/tampermonkey/dhdgffkkebhmkfjojejmpbldmpobp55f)
2. 点击"添加至 Chrome"
3. 确认安装

**Firefox**:
1. 访问 [Firefox Add-ons](https://addons.mozilla.org/firefox/addon/tampermonkey/)
2. 点击"添加到 Firefox"
3. 确认安装

**Safari**:
1. 访问 [Safari App Store](https://apps.apple.com/app/tampermonkey/id1482490089)
2. 点击"获取"
3. 确认安装

### 2. 创建新脚本

1. 点击浏览器工具栏中的 Tampermonkey 图标
2. 选择"创建新脚本"
3. 删除默认内容
4. 复制 `weex_trading_tampermonkey.js` 的全部内容
5. 粘贴到编辑器
6. 按 `Ctrl+S` 保存

### 3. 验证脚本

1. 访问 https://www.weex.com
2. 打开浏览器开发者工具（F12）
3. 在控制台中应该看到：
   ```
   [WEEX Bot] 脚本已加载
   [WEEX Bot] 使用方法: window.WEEXBot.getAccountInfo()
   ```

## 使用方法

### 方法 1：使用可视化控制面板

脚本会在页面右下角创建一个控制面板，包含以下按钮：

- **获取账户** - 获取账户信息
- **获取行情** - 获取 BTC 行情
- **网格交易** - 执行网格交易

直接点击按钮即可执行相应操作。

### 方法 2：在浏览器控制台中使用

打开浏览器开发者工具（F12），在控制台中执行以下命令：

#### 获取账户信息

```javascript
await window.WEEXBot.getAccountInfo()
```

**返回示例**：
```json
{
  "status": 200,
  "data": {
    "account_id": "123456",
    "currency": "USDT",
    "balance": "10000.00"
  }
}
```

#### 获取行情数据

```javascript
// 获取 BTC/USDT 行情
await window.WEEXBot.getTicker('cmt_btcusdt')

// 获取 ETH/USDT 行情
await window.WEEXBot.getTicker('cmt_ethusdt')
```

**返回示例**：
```json
{
  "status": 200,
  "data": {
    "symbol": "cmt_btcusdt",
    "last": "87882.7",
    "best_bid": "87882.6",
    "best_ask": "87882.8"
  }
}
```

#### 手动下单

```javascript
// 下买单
// 参数: symbol, size, type, price, orderType, matchPrice
// type: 1=开多, 2=开空, 3=平多, 4=平空
// orderType: 0=普通, 1=只做maker, 2=全部成交或立即取消, 3=立即成交并取消剩余
// matchPrice: 0=限价, 1=市价

await window.WEEXBot.placeOrder(
    'cmt_btcusdt',  // 交易对
    '0.01',         // 数量
    '1',            // 1=开多
    '50000',        // 价格
    '0',            // 普通订单
    '0'             // 限价
)
```

**返回示例**：
```json
{
  "status": 200,
  "data": {
    "order_id": "596471064624628269",
    "client_oid": "weex_1234567890_abc123"
  }
}
```

#### 撤单

```javascript
await window.WEEXBot.cancelOrder(
    'cmt_btcusdt',           // 交易对
    '596471064624628269'     // 订单 ID
)
```

#### 执行网格交易

```javascript
// 参数: symbol, gridLevels, gridSpacing
// gridLevels: 网格档数（默认 5）
// gridSpacing: 网格间距（USDT，默认 1000）

await window.WEEXBot.executeGridTrading(
    'cmt_btcusdt',  // 交易对
    5,              // 5 档网格
    1000            // 每档间距 1000 USDT
)
```

这将：
1. 获取当前 BTC 价格
2. 计算网格价格
3. 下 5 个买单和 5 个卖单

**示例**：
- 当前价格：87,882.7 USDT
- 买单：86,882.7、85,882.7、84,882.7、83,882.7、82,882.7
- 卖单：88,882.7、89,882.7、90,882.7、91,882.7、92,882.7

## 高级用法

### 自定义网格参数

```javascript
// 10 档网格，间距 500 USDT
await window.WEEXBot.executeGridTrading('cmt_btcusdt', 10, 500)

// 3 档网格，间距 2000 USDT
await window.WEEXBot.executeGridTrading('cmt_btcusdt', 3, 2000)
```

### 批量下单

```javascript
// 下 10 个买单
const buyPrices = [50000, 49000, 48000, 47000, 46000, 45000, 44000, 43000, 42000, 41000];

for (const price of buyPrices) {
    await window.WEEXBot.placeOrder('cmt_btcusdt', '0.01', '1', price.toString());
    console.log(`下单成功: ${price}`);
    await new Promise(resolve => setTimeout(resolve, 1000)); // 延迟 1 秒
}
```

### 监控行情

```javascript
// 每 5 秒获取一次行情
setInterval(async () => {
    const ticker = await window.WEEXBot.getTicker('cmt_btcusdt');
    console.log(`BTC 价格: ${ticker.data.last}`);
}, 5000);
```

### 自动追踪止损

```javascript
// 当价格下跌 2% 时自动平仓
const initialPrice = 87882.7;
const stopLossPrice = initialPrice * 0.98;

setInterval(async () => {
    const ticker = await window.WEEXBot.getTicker('cmt_btcusdt');
    const currentPrice = parseFloat(ticker.data.last);
    
    if (currentPrice <= stopLossPrice) {
        console.log('触发止损，平仓');
        // 执行平仓操作
        await window.WEEXBot.placeOrder('cmt_btcusdt', '0.01', '3', currentPrice.toString(), '0', '1');
    }
}, 5000);
```

## 常见问题

### Q: 脚本无法执行？
A: 检查以下几点：
1. 确认 Tampermonkey 已安装并启用
2. 确认脚本已保存
3. 刷新页面（F5）
4. 检查浏览器控制台是否有错误信息

### Q: 显示 521 错误？
A: 这是 WEEX 服务端的问题，不是脚本问题。可以尝试：
1. 等待 WEEX 服务恢复
2. 在浏览器中手动访问 WEEX 网站，确认服务是否正常
3. 检查网络连接

### Q: 如何修改 API 密钥？
A: 在脚本顶部的 `CONFIG` 部分修改：
```javascript
const CONFIG = {
    apiKey: 'your_api_key_here',
    apiSecret: 'your_api_secret_here',
    apiPassphrase: 'your_passphrase_here',
    baseUrl: 'https://api-contract.weex.com',
};
```

### Q: 脚本是否安全？
A: 脚本仅在本地浏览器中运行，不会上传任何数据。但请注意：
- 不要在公共计算机上使用
- 不要分享脚本给他人（包含 API 密钥）
- 定期更改 API 密钥

### Q: 如何调试脚本？
A: 在浏览器控制台中查看日志：
```javascript
// 所有操作都会输出日志
// 例如: [WEEX Bot] 获取账户信息...
// 在控制台中可以看到完整的请求和响应
```

## 脚本结构

```
weex_trading_tampermonkey.js
├── 配置部分
│   └── API 密钥、基础 URL 等
├── 工具函数
│   ├── generateSignature() - 生成 HMAC-SHA256 签名
│   ├── apiRequest() - 发送 API 请求
│   ├── getAccountInfo() - 获取账户信息
│   ├── getTicker() - 获取行情
│   ├── placeOrder() - 下单
│   ├── cancelOrder() - 撤单
│   └── executeGridTrading() - 网格交易
├── 控制面板
│   └── 可视化界面和按钮
└── 初始化
    └── 脚本启动和日志
```

## 性能优化建议

1. **减少请求频率** - 避免频繁调用 API
2. **使用缓存** - 缓存行情数据，减少请求
3. **异步操作** - 使用 `async/await` 处理并发请求
4. **错误处理** - 添加 try-catch 处理异常

## 安全建议

1. **不要分享脚本** - 脚本包含 API 密钥
2. **定期更改密钥** - 每月更改一次 API 密钥
3. **使用 IP 白名单** - 在 WEEX 中配置 IP 白名单
4. **监控账户** - 定期检查账户活动
5. **备份密钥** - 安全保存 API 密钥备份

## 故障排除

### 脚本不工作

1. **检查浏览器控制台**（F12）：
   ```
   [WEEX Bot] 脚本已加载
   ```

2. **检查 Tampermonkey 状态**：
   - 确认扩展已启用
   - 确认脚本已启用

3. **刷新页面**：
   - 按 `Ctrl+Shift+R`（硬刷新）

4. **检查 API 密钥**：
   - 确认密钥正确
   - 确认密钥未过期

### 请求失败

1. **检查网络连接**
2. **检查 WEEX 服务状态**
3. **查看浏览器控制台错误信息**
4. **尝试在浏览器中手动访问 API**

## 更新日志

### v1.0.0 (2026-01-25)
- 初始版本
- 支持获取账户信息
- 支持获取行情数据
- 支持下单和撤单
- 支持网格交易
- 包含可视化控制面板

## 许可证

MIT License

## 支持

如有问题，请查看浏览器控制台的日志信息，或在 GitHub 上提交 Issue。

---

**最后更新**: 2026-01-25  
**版本**: 1.0.0  
**作者**: Manus Trading Bot
