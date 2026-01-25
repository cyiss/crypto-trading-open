# WEEX 网格交易测试报告

## 测试概述

- **测试日期**: 2026-01-25 18:02 - 18:10 (UTC+8)
- **交易对**: BTC/USDT 永续合约
- **测试账户**: VIP 3
- **账户余额**: 1,862.4480 USDT
- **杠杆倍数**: 200x
- **当前价格**: ~87,868 USDT

## 网格配置

| 参数 | 值 |
|------|------|
| 网格数量 | 10 (5买 + 5卖) |
| 网格间距 | 500 USDT |
| 每单数量 | 20 张 |
| 数量单位 | 张 (contracts) |
| 价格范围 | 85,332 - 90,332 USDT |

## 订单详情

### 买入订单（开多）

| 序号 | 下单时间 | 价格 (USDT) | 数量 (张) | 状态 |
|------|----------|-------------|-----------|------|
| 1 | 18:02:31 | 87,332.0 | 20 | ✅ 已挂单 |
| 2 | 18:03:35 | 86,832.0 | 20 | ✅ 已挂单 |
| 3 | 18:05:08 | 86,332.0 | 20 | ✅ 已挂单 |
| 4 | 18:05:56 | 85,832.0 | 20 | ✅ 已挂单 |
| 5 | 18:06:49 | 85,332.0 | 20 | ✅ 已挂单 |

### 卖出订单（开空）

| 序号 | 下单时间 | 价格 (USDT) | 数量 (张) | 状态 |
|------|----------|-------------|-----------|------|
| 1 | 18:07:44 | 88,332.0 | 20 | ✅ 已挂单 |
| 2 | 18:08:35 | 88,832.0 | 20 | ✅ 已挂单 |
| 3 | 18:09:21 | 89,332.0 | 20 | ✅ 已挂单 |
| 4 | 18:09:23 | 90,332.0 | 20 | ✅ 已挂单 |
| 5 | 18:10:25 | 89,832.0 | 20 | ✅ 已挂单 |

## 保证金占用

- **单笔订单保证金**: ~1.0 USDT (200x杠杆)
- **总保证金占用**: ~10 USDT
- **可用余额**: 1,852.16 USDT

## 测试结论

### 成功项目

1. ✅ **订单下单功能正常** - 所有10个网格订单成功提交
2. ✅ **价格设置正确** - 买入订单低于当前价格，卖出订单高于当前价格
3. ✅ **数量单位正确** - 使用"张"作为数量单位
4. ✅ **杠杆设置正确** - 200x全仓杠杆
5. ✅ **GTC订单类型** - 订单持续有效直到成交或取消
6. ✅ **浏览器自动化** - Tampermonkey脚本和JavaScript注入均可正常工作

### 注意事项

1. **API限制**: WEEX私有API返回521错误，无法直接通过Python API下单
2. **解决方案**: 使用浏览器自动化（Selenium + JavaScript）进行交易操作
3. **"不再提示"选项**: 勾选后可加快下单速度，无需每次确认

## 技术实现

### 方案一：Tampermonkey脚本

```javascript
// 网格交易脚本已保存至 /home/ubuntu/weex_grid_bot.js
// 可通过Tampermonkey扩展加载使用
```

### 方案二：JavaScript控制台注入

```javascript
// 快速下单函数
async function placeOrder(price, quantity, isBuy) {
    const priceInput = document.getElementById('operation-input-price');
    const amountInput = document.getElementById('operation-input-amount');
    
    // 设置价格和数量
    priceInput.value = price;
    amountInput.value = quantity;
    
    // 触发input事件
    priceInput.dispatchEvent(new Event('input', { bubbles: true }));
    amountInput.dispatchEvent(new Event('input', { bubbles: true }));
    
    // 点击对应按钮
    const buttons = document.querySelectorAll('button');
    for (const btn of buttons) {
        if (isBuy && btn.textContent.includes('买入开多')) {
            btn.click();
            break;
        } else if (!isBuy && btn.textContent.includes('卖出开空')) {
            btn.click();
            break;
        }
    }
}
```

## 后续优化建议

1. **自动化监控**: 添加订单成交监控，自动补单
2. **止盈止损**: 为每个订单设置止盈止损价格
3. **动态调整**: 根据市场波动自动调整网格间距
4. **风险控制**: 添加最大持仓限制和亏损预警

## 相关文件

- `/home/ubuntu/crypto-trading-open/core/adapters/exchanges/adapters/weex.py` - WEEX适配器
- `/home/ubuntu/crypto-trading-open/docs/WEEX_ADAPTER.md` - WEEX适配器文档
- `/home/ubuntu/weex_grid_bot.js` - Tampermonkey网格交易脚本
- `/home/ubuntu/crypto-trading-open/examples/weex_btc_grid_example.py` - Python示例

---

*测试报告生成时间: 2026-01-25 18:10 UTC+8*
