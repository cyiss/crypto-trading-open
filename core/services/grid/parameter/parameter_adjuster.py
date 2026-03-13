"""
参数调整器 - Parameter Adjuster

基于波动率和市场指标，根据规则自动调整网格参数。
"""

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional, Dict, Any

from .volatility_calculator import MarketIndicators

logger = logging.getLogger(__name__)


@dataclass
class DynamicFallbackLimits:
    """动态参数的安全边界"""
    grid_interval_min: Decimal = Decimal('5')
    grid_interval_max: Decimal = Decimal('100')
    order_amount_min: Decimal = Decimal('0.00005')
    order_amount_max: Decimal = Decimal('0.0005')
    follow_grid_count_min: int = 30
    follow_grid_count_max: int = 200
    scalping_trigger_min: int = 40
    scalping_trigger_max: int = 90

    @classmethod
    def from_config(cls, config: dict) -> 'DynamicFallbackLimits':
        """从配置字典创建"""
        return cls(
            grid_interval_min=Decimal(str(config.get('grid_interval_min', 5))),
            grid_interval_max=Decimal(str(config.get('grid_interval_max', 100))),
            order_amount_min=Decimal(str(config.get('order_amount_min', 0.00005))),
            order_amount_max=Decimal(str(config.get('order_amount_max', 0.0005))),
            follow_grid_count_min=config.get('follow_grid_count_min', 30),
            follow_grid_count_max=config.get('follow_grid_count_max', 200),
            scalping_trigger_min=config.get('scalping_trigger_min', 40),
            scalping_trigger_max=config.get('scalping_trigger_max', 90),
        )


@dataclass
class AdjustedParameters:
    """调整后的参数"""
    grid_interval: Decimal
    order_amount: Decimal
    follow_grid_count: int
    scalping_trigger_percent: int
    leverage: Optional[int] = None  # 可选调整
    reason: str = ""  # 调整原因
    adjustments: Dict[str, str] = field(default_factory=dict)  # 具体调整项


class ParameterAdjuster:
    """
    参数调整器

    基于市场指标（ATR、波动率、趋势强度）自动调整网格参数。
    调整逻辑遵循安全边界，避免过度调整。
    """

    def __init__(
        self,
        limits: Optional[DynamicFallbackLimits] = None,
    ):
        self.limits = limits or DynamicFallbackLimits()

    def adjust_parameters(
        self,
        indicators: MarketIndicators,
        base_grid_interval: Decimal,
        base_order_amount: Decimal,
        base_follow_grid_count: int,
        base_scalping_trigger: int = 80,
        base_leverage: int = 20,
        base_volatility: Optional[float] = None,  # 基准波动率，用于计算偏离
    ) -> AdjustedParameters:
        """
        根据市场指标调整网格参数

        Args:
            indicators: 市场指标
            base_grid_interval: 原始网格间距
            base_order_amount: 原始下单量
            base_follow_grid_count: 原始网格层数
            base_scalping_trigger: 原始剥头皮触发点
            base_leverage: 原始杠杆倍数
            base_volatility: 基准波动率（用于相对调整）

        Returns:
            AdjustedParameters: 调整后的参数
        """
        adjustments = {}

        # 1. 调整网格间距 (基于ATR)
        grid_interval = self._adjust_grid_interval(
            indicators, base_grid_interval, adjustments
        )

        # 2. 调整网格层数 (基于波动率)
        follow_grid_count = self._adjust_grid_count(
            indicators, base_follow_grid_count, base_volatility, adjustments
        )

        # 3. 调整下单量 (基于波动率)
        order_amount = self._adjust_order_amount(
            indicators, base_order_amount, base_volatility, adjustments
        )

        # 4. 调整剥头皮触发点 (基于波动率)
        scalping_trigger = self._adjust_scalping_trigger(
            indicators, base_scalping_trigger, adjustments
        )

        # 5. 可选：调整杠杆 (基于趋势强度和波动率)
        leverage = self._adjust_leverage(
            indicators, base_leverage, adjustments
        )

        # 构建调整原因
        reason = self._build_reason(indicators, adjustments)

        return AdjustedParameters(
            grid_interval=grid_interval,
            order_amount=order_amount,
            follow_grid_count=follow_grid_count,
            scalping_trigger_percent=scalping_trigger,
            leverage=leverage,
            reason=reason,
            adjustments=adjustments,
        )

    def _adjust_grid_interval(
        self,
        indicators: MarketIndicators,
        base: Decimal,
        adjustments: dict,
    ) -> Decimal:
        """
        调整网格间距

        规则：
        - ATR百分比 > 3%: 大幅增加间距 (1.5x)
        - ATR百分比 > 1.5%: 增加间距 (1.2x)
        - ATR百分比 < 0.5%: 减少间距 (0.8x)
        - 否则：使用ATR直接计算
        """
        atr_pct = float(indicators.atr_percent)

        if atr_pct > 3.0:
            # 大波动：使用ATR计算，但偏向上限
            calculated = indicators.atr * Decimal('0.22')
            multiplier = "22% of ATR (high vol)"
        elif atr_pct > 1.5:
            # 中等波动
            calculated = indicators.atr * Decimal('0.17')
            multiplier = "17% of ATR (medium vol)"
        elif atr_pct < 0.5:
            # 低波动：缩小间距
            calculated = indicators.atr * Decimal('0.12')
            multiplier = "12% of ATR (low vol)"
        else:
            # 正常范围
            calculated = indicators.atr * Decimal('0.15')
            multiplier = "15% of ATR (normal)"

        # 应用安全边界
        result = max(
            self.limits.grid_interval_min,
            min(self.limits.grid_interval_max, calculated)
        )

        if abs(float(result - base)) / float(base) > 0.05:  # 变化超过5%
            adjustments['grid_interval'] = (
                f"{float(base):.4f} → {float(result):.4f} ({multiplier})"
            )

        return result

    def _adjust_grid_count(
        self,
        indicators: MarketIndicators,
        base: int,
        base_volatility: Optional[float],
        adjustments: dict,
    ) -> int:
        """
        调整网格层数

        规则：
        - 年化波动率 > 100%: 减少50%层数
        - 年化波动率 > 60%: 减少30%层数
        - 年化波动率 < 20%: 增加20%层数
        - 否则：保持不变
        """
        vol = float(indicators.volatility_annualized)

        if vol > 1.0:  # > 100%年化波动率
            factor = 0.5
            reason = "extreme volatility, -50%"
        elif vol > 0.6:  # > 60%
            factor = 0.7
            reason = "high volatility, -30%"
        elif vol < 0.2:  # < 20%
            factor = 1.2
            reason = "low volatility, +20%"
        elif vol < 0.35:  # < 35%
            factor = 1.1
            reason = "moderate-low volatility, +10%"
        else:
            factor = 1.0
            reason = "normal volatility, unchanged"

        result = int(base * factor)

        # 应用安全边界
        result = max(self.limits.follow_grid_count_min,
                     min(self.limits.follow_grid_count_max, result))

        if result != base:
            adjustments['follow_grid_count'] = f"{base} → {result} ({reason})"

        return result

    def _adjust_order_amount(
        self,
        indicators: MarketIndicators,
        base: Decimal,
        base_volatility: Optional[float],
        adjustments: dict,
    ) -> Decimal:
        """
        调整下单量

        规则：
        - 波动率越高 → 下单量越小
        - 波动率越低 → 下单量可以稍大
        """
        vol = float(indicators.volatility_annualized)
        risk_factor = 1.0 / (1.0 + vol * 5.0)
        multiplier = max(0.5, min(2.0, risk_factor))

        result = base * Decimal(str(round(multiplier, 4)))

        # 应用安全边界
        result = max(self.limits.order_amount_min,
                     min(self.limits.order_amount_max, result))

        if abs(float(result - base)) / float(base) > 0.05:
            adjustments['order_amount'] = (
                f"{float(base):.6f} → {float(result):.6f} "
                f"(vol={vol:.1%}, risk_factor={multiplier:.2f})"
            )

        return result

    def _adjust_scalping_trigger(
        self,
        indicators: MarketIndicators,
        base: int,
        adjustments: dict,
    ) -> int:
        """
        调整剥头皮触发点

        规则：
        - 高波动率: 降低触发点（更早锁利润）
        - 低波动率: 提高触发点（允许更多利润累积）
        """
        vol = float(indicators.volatility_annualized)

        if vol > 0.8:
            result = max(self.limits.scalping_trigger_min, int(base * 0.8))
            reason = "high vol, trigger earlier (80%)"
        elif vol > 0.5:
            result = int(base * 0.9)
            reason = "medium-high vol, trigger earlier (90%)"
        elif vol < 0.2:
            result = min(self.limits.scalping_trigger_max, int(base * 1.3))
            reason = "low vol, trigger later (130%)"
        else:
            result = base
            reason = "normal vol, unchanged"

        if result != base:
            adjustments['scalping_trigger'] = f"{base}% → {result}% ({reason})"

        return result

    def _adjust_leverage(
        self,
        indicators: MarketIndicators,
        base: int,
        adjustments: dict,
    ) -> Optional[int]:
        """
        可选：调整杠杆

        规则：
        - 强趋势 + 低波动率: 可以保持或略增杠杆
        - 高波动率 + 弱趋势: 降低杠杆
        - 否则：不调整（返回None表示不改变）
        """
        vol = float(indicators.volatility_annualized)
        trend = float(indicators.trend_strength)

        if vol > 0.8 and abs(trend) < 0.3:
            # 高波动率 + 无明显趋势 → 降杠杆
            result = max(5, base - 5)
            if result != base:
                adjustments['leverage'] = f"{base}x → {result}x (high vol + weak trend)"
                return result

        # 其他情况不调整杠杆
        return None

    def _build_reason(
        self,
        indicators: MarketIndicators,
        adjustments: dict,
    ) -> str:
        """构建调整原因摘要"""
        if not adjustments:
            return "No adjustment needed (within normal range)"

        parts = [
            f"ATR={float(indicators.atr_percent):.2f}%",
            f"Vol={float(indicators.volatility_annualized):.1%}",
            f"Trend={indicators.trend_direction}({float(indicators.trend_strength):.2f})",
        ]
        changed = ", ".join(adjustments.keys())
        return f"Adjusted {changed} | Market: {', '.join(parts)}"
