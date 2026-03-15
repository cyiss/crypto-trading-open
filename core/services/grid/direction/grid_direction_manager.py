"""
网格方向管理器 - Grid Direction Manager

根据市场趋势自动切换多空方向，实现智能双向交易。

核心功能：
1. 监控市场趋势（bullish/bearish/sideways）
2. 决定最佳交易方向（long/short/neutral）
3. 触发方向切换时平滑过渡
4. 支持双向网格同时运行

设计理念：
- 趋势明确时：单方向交易（做多或做空）
- 震荡行情时：双向交易（同时做多和做空）
- 避免频繁切换，使用确认机制
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Optional, List, Dict, Any, Callable

logger = logging.getLogger(__name__)


class TradeDirection(Enum):
    """交易方向"""
    LONG = "long"       # 做多
    SHORT = "short"     # 做空
    NEUTRAL = "neutral" # 中性（震荡）
    BOTH = "both"       # 双向（同时做多做空）


class TrendType(Enum):
    """趋势类型"""
    BULLISH = "bullish"     # 看涨
    BEARISH = "bearish"     # 看跌
    SIDEWAYS = "sideways"   # 震荡


@dataclass
class DirectionDecision:
    """方向决策结果"""
    direction: TradeDirection
    trend: TrendType
    confidence: Decimal  # 0.0 ~ 1.0
    reason: str
    should_switch: bool  # 是否需要切换
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class DirectionState:
    """方向状态"""
    current_direction: TradeDirection = TradeDirection.NEUTRAL
    last_switch_time: Optional[datetime] = None
    switch_count: int = 0
    confirmed_trend: Optional[TrendType] = None
    trend_confirmation_count: int = 0


class GridDirectionManager:
    """
    网格方向管理器

    根据市场趋势自动决定交易方向，支持：
    - 单向交易：明确趋势时只做多或只做空
    - 双向交易：震荡行情时同时做多做空
    - 平滑切换：避免频繁切换造成损失
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        初始化方向管理器

        Args:
            config: 配置参数
                - min_confidence: 最低置信度阈值（默认0.6）
                - confirmation_periods: 趋势确认周期数（默认3）
                - min_switch_interval: 最小切换间隔秒数（默认300）
                - trend_strength_threshold: 趋势强度阈值（默认0.3）
                - enable_bidirectional: 是否启用双向交易（默认True）
        """
        self.config = config or {}
        self.logger = logging.getLogger(f"{__name__}.GridDirectionManager")

        # 配置参数
        self.min_confidence = Decimal(str(self.config.get("min_confidence", 0.6)))
        self.confirmation_periods = self.config.get("confirmation_periods", 3)
        self.min_switch_interval = self.config.get("min_switch_interval", 300)  # 5分钟
        self.trend_strength_threshold = Decimal(str(self.config.get("trend_strength_threshold", 0.3)))
        self.enable_bidirectional = self.config.get("enable_bidirectional", True)

        # 状态
        self.state = DirectionState()
        self._decision_history: List[DirectionDecision] = []
        self._callbacks: List[Callable] = []

        # 趋势历史（用于确认）
        self._trend_history: List[TrendType] = []

        self.logger.info(
            f"🧭 方向管理器初始化: "
            f"min_confidence={self.min_confidence}, "
            f"confirmation_periods={self.confirmation_periods}, "
            f"enable_bidirectional={self.enable_bidirectional}"
        )

    def register_callback(self, callback: Callable):
        """注册方向切换回调函数"""
        self._callbacks.append(callback)

    async def _notify_callbacks(self, decision: DirectionDecision):
        """通知所有回调函数"""
        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(decision)
                else:
                    callback(decision)
            except Exception as e:
                self.logger.error(f"方向切换回调执行失败: {e}")

    def analyze_trend(
        self,
        trend_direction: str,
        trend_strength: Decimal,
        atr_percent: Decimal,
    ) -> DirectionDecision:
        """
        分析市场趋势，决定交易方向

        Args:
            trend_direction: 趋势方向（bullish/bearish/sideways）
            trend_strength: 趋势强度（-1.0 ~ 1.0）
            atr_percent: ATR百分比（波动率指标）

        Returns:
            DirectionDecision: 方向决策结果
        """
        # 解析趋势类型
        try:
            trend = TrendType(trend_direction.lower())
        except ValueError:
            trend = TrendType.SIDEWAYS

        # 记录趋势历史
        self._trend_history.append(trend)
        if len(self._trend_history) > self.confirmation_periods * 2:
            self._trend_history = self._trend_history[-self.confirmation_periods * 2:]

        # 计算置信度
        confidence = self._calculate_confidence(trend_strength, atr_percent)

        # 确定目标方向
        target_direction = self._determine_target_direction(
            trend, trend_strength, confidence
        )

        # 判断是否需要切换
        should_switch = self._should_switch_direction(target_direction)

        # 构建决策结果
        decision = DirectionDecision(
            direction=target_direction,
            trend=trend,
            confidence=confidence,
            reason=self._build_reason(trend, trend_strength, confidence),
            should_switch=should_switch,
        )

        # 记录历史
        self._decision_history.append(decision)
        if len(self._decision_history) > 100:
            self._decision_history = self._decision_history[-100:]

        return decision

    def _calculate_confidence(
        self,
        trend_strength: Decimal,
        atr_percent: Decimal,
    ) -> Decimal:
        """
        计算方向置信度

        置信度基于：
        1. 趋势强度（越强越可靠）
        2. 波动率（适中波动率更好）
        """
        # 趋势强度贡献（0.0 ~ 0.6）
        strength_score = abs(trend_strength) * Decimal("0.6")

        # 波动率贡献（0.0 ~ 0.4）
        # 适中波动率（1%~5%）得分最高
        if atr_percent < Decimal("0.5"):
            vol_score = atr_percent / Decimal("0.5") * Decimal("0.2")
        elif atr_percent > Decimal("5"):
            vol_score = max(Decimal("0"), Decimal("0.4") - (atr_percent - Decimal("5")) * Decimal("0.05"))
        else:
            vol_score = Decimal("0.4")

        confidence = min(Decimal("1.0"), strength_score + vol_score)
        return confidence.quantize(Decimal("0.01"))

    def _determine_target_direction(
        self,
        trend: TrendType,
        trend_strength: Decimal,
        confidence: Decimal,
    ) -> TradeDirection:
        """
        确定目标交易方向

        规则：
        1. 趋势强度 > 阈值 且 置信度 > 最低值 → 单向交易
        2. 趋势强度 < 阈值 或 置信度 < 最低值 → 双向/中性
        """
        abs_strength = abs(trend_strength)

        # 置信度不足或趋势不明显 → 震荡行情
        if confidence < self.min_confidence or abs_strength < self.trend_strength_threshold:
            if self.enable_bidirectional:
                return TradeDirection.BOTH
            return TradeDirection.NEUTRAL

        # 明确趋势
        if trend == TrendType.BULLISH:
            return TradeDirection.LONG
        elif trend == TrendType.BEARISH:
            return TradeDirection.SHORT
        else:
            # 震荡但有一定强度 → 双向交易
            if self.enable_bidirectional and abs_strength > self.trend_strength_threshold * Decimal("0.5"):
                return TradeDirection.BOTH
            return TradeDirection.NEUTRAL

    def _should_switch_direction(self, target_direction: TradeDirection) -> bool:
        """
        判断是否应该切换方向

        考虑因素：
        1. 当前方向与目标方向不同
        2. 趋势确认（连续N次同方向）
        3. 切换间隔限制
        """
        current = self.state.current_direction

        # 方向相同，无需切换
        if current == target_direction:
            return False

        # 检查切换间隔
        if self.state.last_switch_time:
            elapsed = (datetime.now() - self.state.last_switch_time).total_seconds()
            if elapsed < self.min_switch_interval:
                self.logger.debug(
                    f"切换间隔不足: {elapsed:.0f}s < {self.min_switch_interval}s"
                )
                return False

        # 检查趋势确认
        if len(self._trend_history) >= self.confirmation_periods:
            recent_trends = self._trend_history[-self.confirmation_periods:]
            if len(set(recent_trends)) == 1:  # 连续N次相同趋势
                self.logger.info(f"✅ 趋势确认: 连续{self.confirmation_periods}次 {recent_trends[0].value}")
                return True
            else:
                self.logger.debug(f"趋势未确认: {recent_trends}")
                return False

        return True

    def _build_reason(
        self,
        trend: TrendType,
        trend_strength: Decimal,
        confidence: Decimal,
    ) -> str:
        """构建决策原因说明"""
        reasons = []

        if trend == TrendType.BULLISH:
            reasons.append(f"看涨趋势(strength={trend_strength:.2f})")
        elif trend == TrendType.BEARISH:
            reasons.append(f"看跌趋势(strength={trend_strength:.2f})")
        else:
            reasons.append(f"震荡行情(strength={trend_strength:.2f})")

        reasons.append(f"置信度={confidence:.0%}")

        return " | ".join(reasons)

    async def update_and_decide(
        self,
        trend_direction: str,
        trend_strength: Decimal,
        atr_percent: Decimal,
    ) -> DirectionDecision:
        """
        更新状态并做出方向决策

        如果决定切换方向，会触发回调通知。

        Args:
            trend_direction: 趋势方向
            trend_strength: 趋势强度
            atr_percent: ATR百分比

        Returns:
            DirectionDecision: 方向决策结果
        """
        decision = self.analyze_trend(trend_direction, trend_strength, atr_percent)

        if decision.should_switch:
            self.logger.info(
                f"🔄 方向切换: {self.state.current_direction.value} → {decision.direction.value} "
                f"| 原因: {decision.reason}"
            )

            # 更新状态
            self.state.current_direction = decision.direction
            self.state.last_switch_time = datetime.now()
            self.state.switch_count += 1
            self.state.confirmed_trend = decision.trend

            # 通知回调
            await self._notify_callbacks(decision)

        return decision

    def get_current_direction(self) -> TradeDirection:
        """获取当前交易方向"""
        return self.state.current_direction

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "current_direction": self.state.current_direction.value,
            "last_switch_time": self.state.last_switch_time.isoformat() if self.state.last_switch_time else None,
            "total_switches": self.state.switch_count,
            "trend_history": [t.value for t in self._trend_history[-10:]],
            "recent_decisions": [
                {
                    "direction": d.direction.value,
                    "trend": d.trend.value,
                    "confidence": float(d.confidence),
                    "should_switch": d.should_switch,
                }
                for d in self._decision_history[-5:]
            ],
        }


class BidirectionalGridController:
    """
    双向网格控制器

    管理同时运行的做多和做空网格，根据方向决策器调整权重。
    """

    def __init__(
        self,
        direction_manager: GridDirectionManager,
    ):
        self.direction_manager = direction_manager
        self.logger = logging.getLogger(f"{__name__}.BidirectionalGridController")

        # 网格实例
        self._long_grid = None
        self._short_grid = None

        # 权重（用于分配资金和订单）
        self._long_weight = Decimal("0.5")
        self._short_weight = Decimal("0.5")

    def set_grids(self, long_grid=None, short_grid=None):
        """设置网格实例"""
        self._long_grid = long_grid
        self._short_grid = short_grid

    async def on_direction_change(self, decision: DirectionDecision):
        """
        处理方向变化

        根据新的方向决策调整网格权重和状态。
        """
        self.logger.info(f"📊 方向变化: {decision.direction.value}")

        if decision.direction == TradeDirection.LONG:
            # 纯做多
            self._long_weight = Decimal("1.0")
            self._short_weight = Decimal("0.0")
            await self._pause_grid(self._short_grid, "切换到纯做多模式")

        elif decision.direction == TradeDirection.SHORT:
            # 纯做空
            self._long_weight = Decimal("0.0")
            self._short_weight = Decimal("1.0")
            await self._pause_grid(self._long_grid, "切换到纯做空模式")

        elif decision.direction == TradeDirection.BOTH:
            # 双向
            self._long_weight = Decimal("0.5")
            self._short_weight = Decimal("0.5")

        elif decision.direction == TradeDirection.NEUTRAL:
            # 中性 - 减少仓位
            self._long_weight = Decimal("0.3")
            self._short_weight = Decimal("0.3")

        self.logger.info(
            f"⚖️ 网格权重更新: 做多={self._long_weight:.0%}, 做空={self._short_weight:.0%}"
        )

    async def _pause_grid(self, grid, reason: str):
        """暂停网格"""
        if grid and hasattr(grid, 'pause'):
            try:
                await grid.pause(reason)
                self.logger.info(f"⏸️ 网格已暂停: {reason}")
            except Exception as e:
                self.logger.error(f"暂停网格失败: {e}")

    def get_weights(self) -> tuple:
        """获取当前权重"""
        return self._long_weight, self._short_weight
