# S级网格选币、参数生成与退出机制设计

## 1. 现状审计

### 1.1 扫描器当前如何给出 S 级

当前 S 级主要由 APR 阈值驱动，不是由完整的波动率加流动性联合决策驱动。

- `SimulationResult.calculate_rating()` 目前以 APR 为主：`APR >= 500% => S`，`>= 300% => A`。
- 成交量只做轻量加减分：`>= 10M USDC +5 分`，`< 0.5M USDC -10 分`，不是硬门槛。
- `scanner_config.min_24h_volume_usdc` 已经配置，但当前扫描结果排序/筛选链路没有真正执行该硬过滤。

结论：

1. 当前的“S级”本质上是“高 APR 标的”，不是“高 APR 且可实盘承载”的标的。
2. 流动性现在只是展示信息和弱修正，不足以支撑自动开单。

### 1.2 当前开单参数是否基于波动率

答案是：部分链路是，部分链路不是，而且启动时并不统一。

当前分成三条链路：

1. 扫描器虚拟网格链路
   - 使用 `grid_volatility_scanner/config/market_config.yaml` 里的 `grid_width_percent` 和 `grid_interval_percent`。
   - 这条链路主要用于虚拟 APR 计算，不直接等价于实盘启动参数。

2. 配置生成链路
   - `tools/grid_config_generator.py` 里，`follow_grid_count` 直接读取配置项；
   - `grid_interval = price_range / grid_count`；
   - 也就是说，层数是先给定，步长是由总宽度除以层数得到。

3. 运行期动态参数链路
   - `core/services/grid/parameter/parameter_adjuster.py` 支持基于 ATR 和年化波动率动态调整：
   - `grid_interval` 基于 ATR 调整；
   - `follow_grid_count` 基于波动率调整；
   - `order_amount` 基于波动率调整。
   - 但这是“启动后调整能力”，不是当前 S 级选币到实盘启动的一体化入口。

结论：

1. 当前并不是“扫描结果直接精准生成实盘参数”。
2. 当前更接近“扫描器负责找高 APR，配置生成器负责按模板产出参数，运行期再尝试动态修正”。

### 1.3 为什么会一次性开 100 格

根因是当前多处默认值都把 `follow_grid_count` 设成了 `100`，它不是扫描器实时算出来的。

- `run_grid_trading.py` 在 follow 模式读取的是配置里的 `follow_grid_count`。
- `tools/grid_config_generator.py` 的 `grid_count = int(self.config['follow_grid_count'])`。
- `AutoGridLauncher` 的基础模板也是 `follow_grid_count: 100`。

所以当前行为是：

1. 先决定“我要 100 格”；
2. 再根据价格区间反推出 `grid_interval`；
3. 启动时尝试把这 100 格挂出来。

这就是为什么你会看到一次性开 100 格。它是模板驱动，不是波动率驱动，也不是流动性驱动。

## 2. 当前问题总结

### 2.1 选币问题

- S 级过度依赖 APR，没有把流动性设为准入门槛。
- 没有把盘口深度、点差、滑点、订单簿刷新稳定性纳入评分闭环。
- 没有区分“适合模拟”和“适合真实开仓”。

### 2.2 参数问题

- `follow_grid_count` 是静态模板，不是基于波动率和流动性联合推导。
- 启动时默认尝试挂满所有层级，不考虑保证金容量、盘口容量、交易所价格距离限制。
- 动态参数引擎存在，但位置偏后，更像补救，不是启动前的主决策器。

### 2.3 生命周期问题

- “进入 S 级”有追踪，但“离开 S 级”没有完整的实盘状态机。
- 自动启动器当前只有“暂停网格”，没有“有持仓时如何分阶段退出”的策略。
- 缺少观察期、降级滞后、冷却期、退出模式和再入场规则。

## 3. 目标设计

新系统要把“S级”从单一 APR 排名改造成“可交易资格”。

### 3.1 核心目标

1. S 级 = 波动率足够 + 流动性足够 + 预期收益足够 + 可承载真实启动。
2. 实盘参数由扫描结果直接生成，而不是固定 100 格模板。
3. 启动时只挂“当前账户和盘口真正能承受的那部分网格”。
4. 币种离开 S 级时，系统知道该继续持有、冻结扩张、排空库存还是强制退出。

### 3.2 新的链路定义

改成单一决策链：

1. 市场扫描
2. 波动率与流动性联合评分
3. 生成实盘参数方案
4. 启动前容量校验
5. 进入运行状态
6. 持续评级监控
7. 降级后进入冻结/排空/退出状态

## 4. 新的 S 级量化标准

S 级不能只看 APR，必须同时通过四类门槛。

### 4.1 收益门槛

- `estimated_apr >= 500%`
- `recent_5min_cycles >= min_cycles_for_s`
- `S` 连续保持至少 `stable_scan_count` 次，或 `stable_duration_minutes` 分钟

建议默认：

- `min_cycles_for_s = 3`
- `stable_scan_count = 3`
- `stable_duration_minutes = 10`

### 4.2 流动性硬门槛

必须新增以下实时指标：

1. `volume_24h_usdc`
2. `spread_bps_p50` 和 `spread_bps_p95`
3. `depth_bid_0_3pct_usdc` / `depth_ask_0_3pct_usdc`
4. `depth_bid_1_0pct_usdc` / `depth_ask_1_0pct_usdc`
5. `estimated_slippage_10usd_bps`
6. `estimated_slippage_startup_batch_bps`
7. `orderbook_freshness_ratio`

建议的 S 级硬门槛：

- `volume_24h_usdc >= 10,000,000`
- `spread_bps_p95 <= min(8, grid_interval_bps * 0.25)`
- `depth_same_side_0_3pct_usdc >= 20 * single_order_notional`
- `depth_same_side_1_0pct_usdc >= 3 * startup_batch_notional`
- `estimated_slippage_10usd_bps <= 5`
- `estimated_slippage_startup_batch_bps <= 12`
- `orderbook_freshness_ratio >= 0.95`

说明：

1. 这些是准入门槛，不是加减分项。
2. 任一硬门槛不满足，最高只能评为 `B`，不能进 `S/A` 自动开单池。

### 4.3 交易所约束门槛

启动前必须检查：

- `buying_power > 0`
- `available_balance >= startup_required_margin`
- `symbol` 的最小下单单位满足
- 限价单距离 mark price 不触发交易所距离限制

### 4.4 评分结构

建议把评分拆成四段，总分 100：

- `yield_score` 35 分：APR、cycle、稳定性
- `volatility_score` 20 分：ATR%、年化波动率、趋势稳定性
- `liquidity_score` 30 分：量、深度、点差、滑点
- `execution_score` 15 分：保证金、交易所约束、近期下单成功率

评级建议：

- `S >= 85`
- `A >= 75`
- `B >= 60`
- `C >= 45`
- `D < 45`

并增加额外约束：

- 若 `liquidity_score < 20`，评级上限为 `B`
- 若 `execution_score < 10`，评级上限为 `C`

## 5. 参数生成方案

### 5.1 设计原则

参数不再由固定模板决定，而是由以下四个输入联合决定：

1. 波动率
2. 流动性
3. 账户容量
4. 交易所限制

### 5.2 关键参数

每个候选币都要产出以下参数：

- `grid_interval`
- `grid_range_percent`
- `follow_grid_count`
- `startup_active_grid_count`
- `order_amount`
- `startup_batch_count`
- `leverage`
- `capital_mode`：`aggressive / normal / drain-only`

### 5.3 步长计算

建议公式：

`interval_bps = clamp(max(0.15 * atr_bps, 1.8 * spread_p95_bps, min_tick_bps * 3), min_interval_bps, max_interval_bps)`

解释：

1. 太小会被点差吃掉。
2. 太大会损失循环频率。
3. 步长必须同时大于交易成本和盘口噪声。

### 5.4 网格总宽度计算

建议公式：

`range_bps = clamp(max(2.2 * atr_15m_bps, 0.9 * expected_move_1h_bps), min_range_bps, max_range_bps)`

做多 follow grid：

- 下沿 = `current_price - range`
- 上沿 = `current_price + entry_buffer`

做空 follow grid：

- 下沿 = `current_price - entry_buffer`
- 上沿 = `current_price + range`

### 5.5 层数计算

不再固定 100。

建议公式：

`raw_grid_count = floor(range_bps / interval_bps)`

然后再做三层裁剪：

1. 波动率裁剪：`12 <= grid_count <= 60`
2. 流动性裁剪：`grid_count <= liquidity_limited_count`
3. 保证金裁剪：`grid_count <= margin_limited_count`

推荐默认范围：

- 主流高流动性：`24 ~ 48`
- 中流动性 S 级：`16 ~ 32`
- 边缘 A/B：`12 ~ 24`

### 5.6 启动时为什么不能挂满所有层

对于 follow grid，`follow_grid_count` 表示“理论完整网格层数”，不应等于“启动时立刻提交的订单数”。

要拆成两个概念：

1. `follow_grid_count`
   - 理论网格结构
   - 用于后续跟随和反手

2. `startup_active_grid_count`
   - 启动时真实挂出的订单数
   - 必须由流动性、保证金和交易所限制共同决定

建议：

- `startup_active_grid_count = min(near_price_count, margin_limited_count, liquidity_limited_count, exchange_distance_limited_count)`

默认不应超过：

- `8 ~ 20` 格

### 5.7 单格下单量

建议先算每个币的风险预算：

- `symbol_capital_budget_usdc`
- `symbol_startup_budget_usdc`

然后：

`order_notional = min(symbol_startup_budget / startup_active_grid_count, depth_same_side_0_3pct_usdc / 20, max_single_order_notional)`

再换算为数量：

`order_amount = order_notional / reference_price`

### 5.8 最终输出示例

每个扫描结果最终不是只给“评级”，而是给一份可执行方案：

- `symbol: DASH`
- `rating: A`
- `score: 78`
- `liquidity_pass: false`
- `recommended_action: watch_only`
- `grid_interval: 0.42`
- `grid_range_percent: 12.5`
- `follow_grid_count: 24`
- `startup_active_grid_count: 8`
- `order_amount: 0.22`
- `startup_required_margin: 8.6 USDC`
- `exit_policy: drain_if_degraded`

## 6. 持仓生命周期与退出机制

### 6.1 状态机

新增统一状态机：

- `CANDIDATE`：候选，尚未满足 S/A 启动条件
- `READY`：满足启动条件，等待资金调度
- `ACTIVE`：实盘运行中
- `FROZEN`：不再加仓，只保留必要订单
- `DRAINING`：逐步退出持仓
- `EXIT_PENDING`：准备强制退出
- `CLOSED`：已退出完成
- `COOLDOWN`：退出后冷却期，禁止立即重启

### 6.2 进入规则

建议：

- 新标的只有当 `S` 连续 `3` 次扫描且流动性门槛全部通过，才可自动启动
- 若只是一次瞬时 S，状态只进 `READY`，不能直接 `ACTIVE`

### 6.3 保持规则

运行中标的分三档处理：

1. 仍为 `S/A` 且流动性通过
   - 保持 `ACTIVE`
   - 可按动态参数微调

2. 降为 `B` 或 S/A 但流动性不再通过
   - 进入 `FROZEN`
   - 停止新开远端挂单
   - 取消最外层扩张挂单
   - 只保留近端订单和 reduce-only 收敛逻辑

3. 降为 `C/D` 或执行风险触发
   - 进入 `DRAINING` 或 `EXIT_PENDING`

### 6.4 “已有持仓，但不再是 S 级”如何退出

这部分要分情况，不能一刀切。

#### 情况 A：从 S 降到 A，但流动性仍健康

动作：

- 不新增理论层数
- 停止外层扩张
- 保留近端网格和止盈
- 观察 `N=3` 个扫描周期

目标：

- 避免因为短时噪声把仍可赚钱的仓位过早砍掉

#### 情况 B：从 S/A 降到 B，或者流动性跌破硬门槛

动作：

- 立即取消所有“增加库存”的挂单
- 保留 reduce-only / take-profit / close ladder
- 将策略切换为 `drain-only`
- 启动排空计时器，例如 `30-120 分钟`

目标：

- 不再继续积累风险，只让仓位自然减小或分批退出

#### 情况 C：降到 C/D，或出现执行风险

执行风险包括：

- `buying_power <= 0`
- `startup_batch_slippage_bps` 超阈值
- 下单成功率显著恶化
- 盘口深度大幅下降

动作：

1. 取消所有非 reduce-only 订单
2. 将持仓切为退出模式
3. 采用分批 reduce-only 限价退出
4. 若 `timeout` 超过阈值，则升级为更激进的 reduce-only IOC/TWAP

建议退出切片：

- 单次退出 notional 不超过 `min(position_notional * 15%, depth_opposite_0_3pct_usdc * 20%)`
- 每 `20-60` 秒重挂一次
- 最大退出时长 `15-30` 分钟

### 6.5 再入场规则

退出后的币种不能立刻重开。

建议：

- 进入 `COOLDOWN` 至少 `60 分钟`
- 只有满足以下条件才允许重新进入 `READY`
  - 连续 `3` 次回到 `S`
  - 流动性重新通过全部门槛
  - 执行成功率恢复

## 7. 需要新增的数据字段

### 7.1 扫描结果字段

扫描结果需要扩展以下字段：

- `atr_percent`
- `volatility_annualized`
- `spread_bps_p50`
- `spread_bps_p95`
- `depth_bid_0_3pct_usdc`
- `depth_ask_0_3pct_usdc`
- `depth_bid_1_0pct_usdc`
- `depth_ask_1_0pct_usdc`
- `slippage_10usd_bps`
- `slippage_startup_batch_bps`
- `execution_success_rate`
- `liquidity_pass`
- `execution_pass`
- `recommended_action`

### 7.2 运行态字段

每个实盘网格还要记录：

- `entry_rating`
- `entry_score`
- `entry_liquidity_score`
- `current_rating`
- `current_score`
- `strategy_state`
- `degrade_since`
- `drain_mode_enabled`
- `planned_exit_deadline`

## 8. 系统模块改造建议

### 8.1 Scanner 层

新增模块：

- `liquidity_analyzer.py`
  - 统计点差、盘口深度、滑点

- `eligibility_engine.py`
  - 汇总 APR、波动率、流动性、执行约束
  - 输出 `rating + score + action`

- `strategy_plan_builder.py`
  - 把扫描结果转成实盘参数方案

### 8.2 Auto Launcher 层

当前 `AutoGridLauncher` 只做简单筛选和暂停，需要升级为：

- `admission controller`
  - 决定是否允许进入 ACTIVE

- `position lifecycle manager`
  - 管理 `ACTIVE/FROZEN/DRAINING/EXIT_PENDING`

- `exit executor`
  - 负责 reduce-only 退出切片执行

### 8.3 Grid 运行层

运行层增加两类能力：

1. 启动只挂 `startup_active_grid_count`，不挂满理论层
2. 支持运行中切换到 `drain-only` 模式

## 9. 推荐实施顺序

### Phase 1: 修正决策口径

目标：先让扫描结果变得可信。

1. 把流动性门槛纳入硬过滤
2. 扩展扫描结果数据结构
3. 增加 `liquidity_pass` 和 `recommended_action`

### Phase 2: 修正参数生成

目标：去掉固定 100 格。

1. 把 `follow_grid_count` 改为由 `range / interval` 计算
2. 增加 `startup_active_grid_count`
3. 启动时只挂近端有限层数

### Phase 3: 修正生命周期

目标：解决“不是 S 级了怎么办”。

1. 引入状态机
2. 实现 `FROZEN` 与 `DRAINING`
3. 增加 reduce-only 退出执行器

### Phase 4: 修正控制面

目标：让运营视角可解释。

控制面板应展示：

- 为什么是 S/A/B
- 哪个流动性门槛没过
- 为什么只挂了 8 格而不是 24 格
- 当前处于 `ACTIVE/FROZEN/DRAINING` 的哪一种
- 如果退出，预计多久退出完

## 10. 最终结论

### 10.1 对你问题的直接回答

1. 当前 S 级参数不是完整地根据波动率算出来的。
2. 当前会一次性开 100 格，是因为 `follow_grid_count=100` 在多个链路里都是固定模板值。
3. 当前流动性没有被作为自动开单的硬门槛，只是弱评分修正，这是不够的。
4. 当前“已有持仓但不再是 S 级”的处理不完整，只有暂停思路，没有完整退出状态机。

### 10.2 必须落地的原则

后续实盘要改成：

- `S级 != 高APR`
- `S级 = 高APR + 足够流动性 + 可执行 + 可退出`

并且：

- `理论网格层数 != 启动挂单层数`
- `进入S级 != 立即满仓开单`
- `离开S级 != 立即粗暴平仓`

而是要用统一的量化准入、参数生成、状态机和退出执行来闭环。