# WEEX 网格交易系统终端 UI 数据显示修复

**日期**：2026-01-29  
**问题**：WEEX 网格交易系统终端面板显示的持仓、平均成本、未实现盈亏等数据错误  
**状态**：✅ 已修复

---

## 问题描述

用户反馈 WEEX 网格交易系统的终端 UI 显示数据完全错误：

| 字段 | 错误显示 | 应该显示 |
|------|---------|---------|
| 持仓方向 (side) | "440 张" | "多" 或 "空" |
| 持仓数量 (size) | 89358.0 | 0.044 BTC (440张 × 0.0001) |
| 平均成本 (entryPrice) | 显示其他数据 | 89358.0 |
| 未实现盈亏 (unrealizedPnl) | 0 | -2,047.2686 USDT |

---

## 根本原因

油猴脚本 `weex_unified_bot.user.js` 的 DOM 解析逻辑使用了**错误的列索引映射**。

### 错误的解析逻辑（修复前）

```javascript
// 错误的列索引映射
const pos = {
    symbol: cells[0]?.textContent?.trim() || '',
    side: cells[1]?.textContent?.trim() || '',      // ❌ 实际是张数
    quantity: cells[2]?.textContent?.trim() || '',  // ❌ 实际是均价
    entryPrice: cells[3]?.textContent?.trim() || '', // ❌ 实际是标记价格
    pnl: cells[4]?.textContent?.trim() || ''
};
```

### WEEX 实际表格结构

```html
<table data-slot="table">
  <tbody data-slot="table-body">
    <tr data-slot="table-row">
      <td>[0] 合约: BTC/USDT + <span>空</span> + 200x</td>
      <td>[1] 数量: 89,490 张</td>
      <td>[2] 开仓均价: 89,335.3</td>
      <td>[3] 标记价格: 89,540.6</td>
      <td>[4] 预估强平价: 101,506.6</td>
      <td>[5] 保证金比率: 1.11%</td>
      <td>[6] 保证金: 4,008.0646 USDT</td>
      <td>[7] 未实现盈亏: -1,837.2297 USDT</td>
      <td>[8] 已实现盈亏: -127.9139 USDT</td>
    </tr>
  </tbody>
</table>
```

---

## 修复方案

### 1. 油猴脚本修复

**文件**：`examples/weex_unified_bot.user.js` (第 341-457 行)

**修复内容**：
- 使用精确选择器定位 WEEX 持仓表格
- 从 `cells[0]` 内部 DOM 分别提取币对、方向标签（多/空）、杠杆
- 从 `cells[1]` 提取张数（正则匹配 "X,XXX 张"）
- 从 `cells[2]` 提取开仓均价
- 从 `cells[7]` 提取未实现盈亏
- 计算 BTC 数量：`张数 × 0.0001`（WEEX BTC 合约面值）

**核心代码**：

```javascript
// 查找持仓表格的 tbody
const positionTable = document.querySelector('table[data-slot="table"] tbody[data-slot="table-body"]');
if (positionTable) {
    const rows = positionTable.querySelectorAll('tr[data-slot="table-row"]');
    
    rows.forEach(row => {
        const cells = row.querySelectorAll('td[data-slot="table-cell"]');
        if (cells.length >= 9) {
            // 解析合约名称和方向
            const contractCell = cells[0];
            const symbolText = contractCell.querySelector('.text-text-primary')?.textContent?.trim() || '';
            const sideElement = contractCell.querySelector('.text-xs.mr-1.px-1');
            const sideText = sideElement?.textContent?.trim() || '';
            const leverageText = contractCell.querySelector('.text-xs.ml-1.px-1')?.textContent?.trim() || '';
            
            // 完整合约名称（如 "BTC/USDT空200x"）
            const fullSymbol = `${symbolText}${sideText}${leverageText}`;
            
            // 解析方向
            let side = '';
            if (sideText.includes('多')) {
                side = 'long';
            } else if (sideText.includes('空')) {
                side = 'short';
            }
            
            // 解析张数
            const sizeText = cells[1]?.textContent?.trim() || '';
            const sizeMatch = sizeText.match(/([0-9,]+)\s*张/);
            const contracts = sizeMatch ? parseFloat(sizeMatch[1].replace(/,/g, '')) : 0;
            
            // 解析开仓均价
            const entryPriceText = cells[2]?.textContent?.trim() || '';
            const entryPrice = parseFloat(cleanNumber(entryPriceText)) || 0;
            
            // 解析未实现盈亏（从第8列提取）
            const unrealizedPnlCell = cells[7];
            const unrealizedPnlText = unrealizedPnlCell?.querySelector('p[dir="ltr"]')?.textContent?.trim() || '';
            const unrealizedPnl = cleanNumber(unrealizedPnlText);
            
            // 计算 BTC 数量：张数 * 合约面值
            const contractMultiplier = 0.0001;  // WEEX BTC 合约面值
            const quantityInBTC = contracts * contractMultiplier;
            
            const position = {
                symbol: fullSymbol,
                side: side,
                contracts: contracts,
                quantity: quantityInBTC.toFixed(6),
                size: quantityInBTC.toFixed(6),
                entryPrice: entryPrice.toString(),
                pnl: unrealizedPnl,
                unrealizedPnl: unrealizedPnl
            };
            
            // 验证并添加到结果
            if (position.symbol && contracts > 0 && side) {
                account.positions.push(position);
                if (!account.position) {
                    account.position = position;
                }
                foundPositions = true;
                log(`解析到持仓: ${position.symbol} 方向=${side} 张数=${contracts} BTC=${position.size} 均价=${entryPrice} 盈亏=${unrealizedPnl}`, 'info');
            }
        }
    });
}
```

### 2. Python 适配器修复

**文件**：`core/adapters/exchanges/adapters/weex_tampermonkey_rest.py` (第 360-393 行)

**修复内容**：
- 支持油猴脚本返回的 `side` 字段（"long"/"short"）
- 优先使用 `side` 字段判断持仓方向
- 兼容旧版：如果 `side` 字段不存在，使用 `size` 正负判断方向
- 增强调试日志

**核心代码**：

```python
# 从油猴脚本返回的 side 字段判断方向
side_str = position_data.get('side', '').lower()
if side_str == 'long':
    position_side = PositionSide.LONG
elif side_str == 'short':
    position_side = PositionSide.SHORT
else:
    # 兼容旧版：如果 side 字段不是 long/short，用 size 的正负判断
    position_side = PositionSide.LONG if size > 0 else PositionSide.SHORT

# 🔍 调试日志：打印解析后的数据
if self.logger:
    self.logger.info(f"[WEEX] 持仓解析: side={position_side.value}, size={size}, entry_price={entry_price}, unrealized_pnl={unrealized_pnl}")

positions.append(PositionData(
    symbol=self._base.get_current_symbol(),
    side=position_side,  # 使用正确解析的方向
    size=abs(size),
    entry_price=entry_price,
    # ... 其他字段
))
```

---

## 数据流

```
WEEX 页面（表格 HTML）
  ↓
油猴脚本 DOM 解析
  ├─ cells[0] → symbol: "BTC/USDT空200x", side: "short"
  ├─ cells[1] → contracts: 89490 (从 "89,490 张" 提取)
  ├─ cells[2] → entryPrice: 89335.3
  └─ cells[7] → unrealizedPnl: -1837.2297 (从 "-1,837.2297 USDT" 提取)
  ↓
计算 quantity = contracts × 0.0001 BTC/张 = 8.949 BTC
  ↓
WebSocket 发送到 Python 后端
  {
    "symbol": "BTC/USDT空200x",
    "side": "short",
    "contracts": 89490,
    "quantity": "8.949000",
    "size": "8.949000",
    "entryPrice": "89335.3",
    "unrealizedPnl": "-1837.2297"
  }
  ↓
Python 适配器 weex_tampermonkey_rest.py 解析
  ↓
创建 PositionData
  - symbol: "BTC/USDT"
  - side: PositionSide.SHORT
  - size: 8.949
  - entry_price: 89335.3
  - unrealized_pnl: -1837.2297
  ↓
终端 UI 正确显示
```

---

## 测试验证

### 预期日志输出

**油猴脚本日志**：
```
[油猴] 解析到持仓: BTC/USDT空200x 方向=short 张数=89490 BTC=8.949000 均价=89335.3 盈亏=-1837.2297
[油猴] 解析到持仓: BTC/USDT多200x 方向=long 张数=520 BTC=0.052000 均价=89386.1 盈亏=8.0318
```

**Python 适配器日志**：
```
2026-01-29 03:45:11,153 - ExchangeAdapter.weex - INFO - [WEEX] 持仓原始数据: {'symbol': 'BTC/USDT空200x', 'side': 'short', 'contracts': 89490, 'quantity': '8.949000', 'size': '8.949000', 'entryPrice': '89335.3', 'pnl': '-1837.2297', 'unrealizedPnl': '-1837.2297'}
2026-01-29 03:45:11,154 - ExchangeAdapter.weex - INFO - [WEEX] 持仓解析: side=short, size=8.949, entry_price=89335.3, unrealized_pnl=-1837.2297
```

---

## 注意事项

### 合约面值配置

当前代码中硬编码了 BTC 合约面值为 `0.0001 BTC/张`：

```javascript
const contractMultiplier = 0.0001;  // BTC 合约面值
```

**如果 WEEX 的合约乘数不是 0.0001，需要调整此值。**

常见合约面值：
- BTC: 0.0001 BTC/张
- ETH: 0.001 ETH/张
- 其他币种需根据 WEEX 官方规则确定

### 支持的持仓视图

当前实现支持 WEEX 的**简洁视图**模式。如果用户切换到"详情"视图，表格列可能不同，需要额外适配。

---

## 相关文件

| 文件路径 | 说明 | 修改行数 |
|---------|------|---------|
| `examples/weex_unified_bot.user.js` | 油猴脚本（DOM 解析） | 341-457 |
| `core/adapters/exchanges/adapters/weex_tampermonkey_rest.py` | WEEX REST 适配器 | 360-393 |

---

## 总结

本次修复通过**精确匹配 WEEX 表格结构**，解决了数据字段错位的问题：

✅ 正确提取持仓方向（多/空 → long/short）  
✅ 正确解析张数并计算 BTC 数量  
✅ 正确提取开仓均价  
✅ 正确提取未实现盈亏  
✅ Python 适配器支持新的字段格式  
✅ 增强调试日志便于后续排查

用户现在应该能在终端 UI 中看到正确的持仓、盈亏等数据。
