# WEEX 网格交易使用指南

## 概述

由于 WEEX 的私有 API 存在限制（返回 521 错误），本项目采用 **油猴脚本 + Python 后端** 的混合方案来实现网格交易：

- **Python 后端**: 计算网格价格、生成交易命令
- **油猴脚本**: 在浏览器中执行实际的下单、撤单操作
- **WebSocket 通信**: 后端和浏览器通过 WebSocket 进行实时通信

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                   Python 后端 (run_grid_trading.py)          │
│              计算网格价格、生成交易命令                       │
└──────────────────────────┬──────────────────────────────────┘
                           │
                    WebSocket 通信
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                   浏览器 (Tampermonkey 脚本)                  │
│              执行下单、撤单、查询订单等操作                    │
└─────────────────────────────────────────────────────────────┘
```

## 安装步骤

### 1. 安装 Tampermonkey 扩展

**Chrome/Edge:**
- 访问 https://chrome.google.com/webstore/detail/tampermonkey/dhdgffkkebhmkfjojejmpbldmpobp55f
- 点击"添加至 Chrome"

**Firefox:**
- 访问 https://addons.mozilla.org/firefox/addon/tampermonkey/
- 点击"添加到 Firefox"

### 2. 创建油猴脚本

1. 打开 Tampermonkey 面板（浏览器右上角）
2. 点击"创建新脚本"
3. 删除默认内容，复制以下脚本：

```javascript
// 从 examples/weex_trading_controlled_tampermonkey.js 复制完整脚本
```

4. 保存脚本（Ctrl+S）

### 3. 配置 Python 环境变量

创建 `.env` 文件或设置环境变量：

```bash
export WEEX_API_KEY="weex_d0649c112185fb5a0aeb13846fe915ac"
export WEEX_API_SECRET="a041e89a40dba5c2a8ae80ec12d2a51ece7026ab378f21bad74fcb1e984f3a61"
export WEEX_API_PASSPHRASE="manus20260125"
```

### 4. 启动网格交易

```bash
# 使用默认配置
python run_grid_trading.py -c config/grid/weex_grid_example.yaml

# 或使用自定义配置
python run_grid_trading.py -c config/grid/your_custom_config.yaml
```

## 使用流程

### 第一步：启动 Python 后端

```bash
python run_grid_trading.py -c config/grid/weex_grid_example.yaml
```

输出示例：
```
[INFO] 正在初始化网格交易系统...
[INFO] 交易所: WEEX
[INFO] 交易对: BTC/USDT
[INFO] 网格类型: 普通网格（做多）
[INFO] 网格数量: 20
[INFO] 网格间隔: 500 USDT
[INFO] 
[INFO] ⏳ 等待浏览器连接...
[INFO] WebSocket 服务器已启动，监听 ws://localhost:8765
```

### 第二步：打开浏览器并访问 WEEX

1. 打开浏览器，访问 https://www.weex.com
2. 登录您的 WEEX 账户
3. 进入交易页面

### 第三步：启动油猴脚本

1. 打开浏览器控制台（F12）
2. 在控制台中执行：

```javascript
// 连接到 Python 后端
await window.WEEXBot.connect('ws://localhost:8765')

// 启动网格交易
await window.WEEXBot.startGridTrading()
```

### 第四步：监控交易

- **Python 后端**: 显示网格计算、订单统计、收益情况
- **浏览器控制台**: 显示实际的下单、撤单、成交情况
- **WEEX 网站**: 实时查看订单和持仓

## 配置文件说明

### 网格类型

#### 1. 普通网格（LONG/SHORT）

```yaml
grid_type: long                 # 做多网格
price_range:
  lower_price: 85000           # 价格下限
  upper_price: 95000           # 价格上限
grid_interval: 500             # 网格间隔
```

**特点**: 固定价格区间，等差网格

#### 2. 马丁网格（MARTINGALE_LONG/MARTINGALE_SHORT）

```yaml
grid_type: martingale_long
martingale_increment: 100      # 递增金额
price_range:
  lower_price: 85000
  upper_price: 95000
grid_interval: 500
```

**特点**: 每次下单金额递增，适合看好趋势的情况

#### 3. 价格移动网格（FOLLOW_LONG/FOLLOW_SHORT）

```yaml
grid_type: follow_long
follow_grid_count: 10          # 网格数量
follow_timeout: 300            # 脱离超时（秒）
follow_distance: 1             # 脱离距离（网格数）
grid_interval: 500
```

**特点**: 动态跟踪价格，自动调整网格范围

### 高级功能

#### 剥头皮模式

```yaml
scalping_enabled: true
scalping_trigger_percent: 80   # 网格进度 80% 时触发
scalping_take_profit_grids: 2  # 使用 2 格作为止盈
```

**特点**: 快速止盈，锁定利润

#### 智能剥头皮

```yaml
smart_scalping_enabled: true
allowed_deep_drops: 1          # 允许 1 次深度下跌
min_drop_threshold_percent: 10 # 最小下跌 10%
```

**特点**: 等待深度下跌后再激活剥头皮

#### 本金保护模式

```yaml
capital_protection_enabled: true
capital_protection_trigger_percent: 50  # 网格进度 50% 时触发
```

**特点**: 保护本金，及时止损

#### 止盈模式

```yaml
take_profit_enabled: true
take_profit_percentage: 0.01   # 1% 止盈
```

**特点**: 达到目标收益后自动平仓

#### 止损保护

```yaml
stop_loss_protection_enabled: true
stop_loss_trigger_percent: 100.0      # 完全脱离网格时触发
stop_loss_escape_timeout: 300         # 持续 5 分钟脱离
stop_loss_apr_threshold: 50.0         # APR 低于 50% 时停止
```

**特点**: 极端行情保护，自动止损

## 常见问题

### Q1: 油猴脚本无法连接到 Python 后端？

**解决方案**:
1. 确保 Python 后端正在运行
2. 检查 WebSocket 服务器地址是否正确
3. 检查防火墙是否阻止了 8765 端口
4. 在浏览器控制台查看错误信息

### Q2: 下单失败，显示 521 错误？

**原因**: WEEX 私有 API 限制

**解决方案**:
1. 确保已登录 WEEX 账户
2. 检查账户余额是否充足
3. 检查杠杆和保证金模式设置
4. 查看浏览器控制台的详细错误信息

### Q3: 网格交易停止了，怎么办？

**排查步骤**:
1. 检查 Python 后端是否仍在运行
2. 检查浏览器是否关闭或刷新了页面
3. 检查网络连接是否正常
4. 查看日志文件获取详细信息

### Q4: 如何修改网格参数？

**方法**:
1. 编辑配置文件（YAML）
2. 重启 Python 后端
3. 重新启动油猴脚本中的网格交易

### Q5: 如何停止网格交易？

**方法**:
1. **Python 后端**: 按 Ctrl+C
2. **油猴脚本**: 在浏览器控制台执行 `await window.WEEXBot.stopGridTrading()`
3. **完全停止**: 同时停止两者

## 交易精度参数

不同的交易对有不同的精度要求，需要在配置文件中正确设置：

### BTC/USDT

```yaml
quantity_precision: 8           # BTC 最小单位：0.00000001
price_decimals: 2               # USDT 最小单位：0.01
```

### ETH/USDT

```yaml
quantity_precision: 6           # ETH 最小单位：0.000001
price_decimals: 2
```

### SOL/USDT

```yaml
quantity_precision: 4           # SOL 最小单位：0.0001
price_decimals: 2
```

> **提示**: 可以在 WEEX 交易页面查看最小下单单位来确定精度参数

## 风险提示

⚠️ **重要警告**:

1. **测试账户**: 建议先在测试账户上测试
2. **小额测试**: 先用小额进行测试，确认无误后再增加金额
3. **监控交易**: 定期检查交易执行情况
4. **及时止损**: 设置合理的止损参数
5. **备份密钥**: 妥善保管 API 密钥和密码短语
6. **网络安全**: 不要在公共网络上运行交易脚本

## 支持的交易对

WEEX 支持的主要交易对（更新至 2026-01-25）：

- **主流币**: BTC/USDT, ETH/USDT, SOL/USDT, XRP/USDT
- **Layer 2**: ARB/USDT, OP/USDT, STARKNET/USDT
- **DeFi**: AAVE/USDT, UNI/USDT, DYDX/USDT
- **其他**: 711+ 个交易对

> 完整列表可通过 Python 后端查询：`await adapter.get_supported_symbols()`

## 技术细节

### WebSocket 通信协议

**客户端 → 服务器**:
```json
{
  "action": "place_order",
  "symbol": "cmt_btcusdt",
  "side": "buy",
  "type": "limit",
  "price": "50000",
  "quantity": "0.01"
}
```

**服务器 → 客户端**:
```json
{
  "type": "order_placed",
  "order_id": "12345",
  "status": "success",
  "data": {...}
}
```

### 签名算法

WEEX 使用 HMAC-SHA256 签名：

```python
timestamp = str(int(time.time() * 1000))
message = f"GET/capi/v2/account/getAccounts{timestamp}"
signature = base64.b64encode(
    hmac.new(
        api_secret.encode(),
        message.encode(),
        hashlib.sha256
    ).digest()
).decode()
```

## 更多帮助

- **WEEX API 文档**: https://www.weex.com/api-doc/zh-CN/contract/
- **项目 GitHub**: https://github.com/cyiss/crypto-trading-open
- **问题反馈**: 提交 Issue 或 PR

## 更新日志

### v2.0.0 (2026-01-25)

- ✅ 添加 WEEX 网格交易支持
- ✅ 实现油猴脚本 + Python 后端混合方案
- ✅ 支持所有网格交易模式
- ✅ 完整的 WebSocket 通信协议

### v1.0.0 (2026-01-20)

- ✅ WEEX 适配器基础实现
- ✅ 公开 API 支持（行情、合约信息）
- ✅ 油猴脚本基础框架
