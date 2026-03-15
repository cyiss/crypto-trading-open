"""
双向网格控制器 - Bidirectional Grid Controller

同时运行做多和做空网格，根据市场趋势自动调整方向权重。

核心功能：
1. 同时管理做多和做空两个网格实例
2. 根据趋势方向调整资金分配权重
3. 震荡行情双向交易，趋势行情单向交易
4. 平滑切换，避免频繁开关
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any, List, TYPE_CHECKING

if TYPE_CHECKING:
    from core.services.grid.coordinator.grid_coordinator import GridCoordinator
    from core.services.grid.models.grid_config import GridConfig

logger = logging.getLogger(__name__)


@dataclass
class DirectionWeights:
    """方向权重"""
    long_weight: Decimal = Decimal("0.5")  # 做多权重
    short_weight: Decimal = Decimal("0.5")  # 做空权重
    reason: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


class BidirectionalGridController:
    """
    双向网格控制器

    管理 同时运行的做多和做空网格，根据市场趋势动态调整：

    1. **强看涨** (bullish, strength > 0.5):
       - 做多权重 100%，做空暂停

    2. **强看跌** (bearish, strength < -0.5):
       - 做空权重 100%，做多暂停

    3. **震荡** (sideways 或 strength 在 -0.5~0.5):
       - 双向交易，根据波动率分配权重

    使用方式：
        controller = BidirectionalGridController()
        controller.set_grids(long_coordinator, short_coordinator)

        # 根据趋势更新权重
        weights = await controller.update_weights(trend_direction, trend_strength)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化双向网格控制器

        Args:
            config: 配置参数
                - min_switch_interval: 最小切换间隔（秒，默认300）
                - strength_threshold: 趋势强度阈值（默认0.4）
                - sideways_weight_range: 震荡时权重范围（默认0.3~0.7）
        """
        self.config = config or {}
        self.logger = logging.getLogger(f"{__name__}.BidirectionalGridController")

        # 配置参数
        self.min_switch_interval = self.config.get("min_switch_interval", 300)
        self.strength_threshold = Decimal(str(self.config.get("strength_threshold", 0.4)))
        self.sideways_weight_range = (
            Decimal(str(self.config.get("sideways_min_weight", 0.3))),
            Decimal(str(self.config.get("sideways_max_weight", 0.7))),
        )

        # 网格实例
        self._long_coordinator: Optional['GridCoordinator'] = None
        self._short_coordinator: Optional['GridCoordinator'] = None

        # 状态
        self._current_weights = DirectionWeights()
        self._last_switch_time: Optional[datetime] = None
        self._switch_count = 0
        self._weight_history: List[DirectionWeights] = []

        self.logger.info(
            f"✅ 双向网格控制器初始化: "
            f"min_switch_interval={self.min_switch_interval}s, "
            f"strength_threshold={self.strength_threshold}"
        )

    def set_grids(
        self,
        long_coordinator: Optional['GridCoordinator'] = None,
        short_coordinator: Optional['GridCoordinator'] = None,
    ):
        """
        设置网格协调器实例

        Args:
            long_coordinator: 做多网格协调器
            short_coordinator: 做空网格协调器
        """
        self._long_coordinator = long_coordinator
        self._short_coordinator = short_coordinator

        if long_coordinator:
            self.logger.info("✅ 做多网格已绑定")
        if short_coordinator:
            self.logger.info("✅ 做空网格已绑定")

    async def update_weights(
        self,
        trend_direction: str,
        trend_strength: Decimal,
        volatility: Optional[Decimal] = None,
    ) -> DirectionWeights:
        """
        根据市场趋势更新方向权重

        Args:
            trend_direction: 趋势方向（bullish/bearish/sideways）
            trend_strength: 趋势强度（-1.0 ~ 1.0）
            volatility: 波动率（可选，用于震荡时调整权重）

        Returns:
            DirectionWeights: 新的方向权重
        """
        # 检查切换间隔
        if self._last_switch_time:
            elapsed = (datetime.now() - self._last_switch_time).total_seconds()
            if elapsed < self.min_switch_interval:
                self.logger.debug(f"切换间隔不足: {elapsed:.0f}s < {self.min_switch_interval}s")
                return self._current_weights

        # 计算新权重
        new_weights = self._calculate_weights(trend_direction, trend_strength, volatility)

        # 检查是否有实质性变化
        if self._has_significant_change(new_weights):
            await self._apply_weight_change(new_weights)
            self._last_switch_time = datetime.now()
            self._switch_count += 1

        return self._current_weights

    def _calculate_weights(
        self,
        trend_direction: str,
        trend_strength: Decimal,
        volatility: Optional[Decimal],
    ) -> DirectionWeights:
        """计算方向权重"""
        abs_strength = abs(trend_strength)

        # 强趋势 → 单向交易
        if trend_direction == "bullish" and abs_strength > self.strength_threshold:
            return DirectionWeights(
                long_weight=Decimal("1.0"),
                short_weight=Decimal("0.0"),
                reason=f"强看涨趋势(strength={trend_strength:.2f})",
            )

        if trend_direction == "bearish" and abs_strength > self.strength_threshold:
            return DirectionWeights(
                long_weight=Decimal("0.0"),
                short_weight=Decimal("1.0"),
                reason=f"强看跌趋势(strength={trend_strength:.2f})",
            )

        # 震荡或弱趋势 → 双向交易
        min_weight, max_weight = self.sideways_weight_range

        # 根据趋势强度调整权重
        # strength > 0: 略偏多
        # strength < 0: 略偏空
        base_weight = Decimal("0.5")
        adjustment = trend_strength * (max_weight - min_weight) / 2
        long_weight = base_weight + adjustment

        # 限制在范围内
        long_weight = max(min_weight, min(max_weight, long_weight))
        short_weight = Decimal("1.0") - long_weight

        return DirectionWeights(
            long_weight=long_weight,
            short_weight=short_weight,
            reason=f"震荡行情(strength={trend_strength:.2f}, volatility={volatility:.2%})" if volatility else f"弱趋势(strength={trend_strength:.2f})",
        )

    def _has_significant_change(self, new_weights: DirectionWeights) -> bool:
        """检查权重是否有显著变化"""
        threshold = Decimal("0.1")  # 10%变化才触发

        long_diff = abs(new_weights.long_weight - self._current_weights.long_weight)
        short_diff = abs(new_weights.short_weight - self._current_weights.short_weight)

        return long_diff > threshold or short_diff > threshold

    async def _apply_weight_change(self, new_weights: DirectionWeights):
        """应用权重变化"""
        old_weights = self._current_weights
        self._current_weights = new_weights

        # 记录历史
        self._weight_history.append(new_weights)
        if len(self._weight_history) > 100:
            self._weight_history = self._weight_history[-100:]

        self.logger.info(
            f"⚖️ 方向权重更新: "
            f"做多 {old_weights.long_weight:.0%}→{new_weights.long_weight:.0%}, "
            f"做空 {old_weights.short_weight:.0%}→{new_weights.short_weight:.0%} "
            f"| 原因: {new_weights.reason}"
        )

        # 暂停/恢复网格
        await self._adjust_grid_states(new_weights)

    async def _adjust_grid_states(self, weights: DirectionWeights):
        """根据权重调整网格状态"""
        # 做多网格
        if self._long_coordinator:
            if weights.long_weight == Decimal("0.0"):
                await self._pause_grid(self._long_coordinator, "切换到做空方向")
            elif weights.long_weight > Decimal("0.0") and not self._is_grid_running(self._long_coordinator):
                await self._resume_grid(self._long_coordinator, "恢复做多网格")

        # 做空网格
        if self._short_coordinator:
            if weights.short_weight == Decimal("0.0"):
                await self._pause_grid(self._short_coordinator, "切换到做多方向")
            elif weights.short_weight > Decimal("0.0") and not self._is_grid_running(self._short_coordinator):
                await self._resume_grid(self._short_coordinator, "恢复做空网格")

    async def _pause_grid(self, coordinator: 'GridCoordinator', reason: str):
        """暂停网格"""
        try:
            if hasattr(coordinator, 'pause'):
                await coordinator.pause(reason)
                self.logger.info(f"⏸️ 网格已暂停: {reason}")
        except Exception as e:
            self.logger.error(f"暂停网格失败: {e}")

    async def _resume_grid(self, coordinator: 'GridCoordinator', reason: str):
        """恢复网格"""
        try:
            if hasattr(coordinator, 'resume'):
                await coordinator.resume(reason)
                self.logger.info(f"▶️ 网格已恢复: {reason}")
        except Exception as e:
            self.logger.error(f"恢复网格失败: {e}")

    def _is_grid_running(self, coordinator: 'GridCoordinator') -> bool:
        """检查网格是否在运行"""
        if hasattr(coordinator, 'is_running'):
            return coordinator.is_running()
        if hasattr(coordinator, '_running'):
            return coordinator._running
        return True  # 默认假设运行中

    def get_current_weights(self) -> DirectionWeights:
        """获取当前权重"""
        return self._current_weights

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "current_weights": {
                "long": float(self._current_weights.long_weight),
                "short": float(self._current_weights.short_weight),
                "reason": self._current_weights.reason,
            },
            "switch_count": self._switch_count,
            "last_switch": self._last_switch_time.isoformat() if self._last_switch_time else None,
            "long_grid_running": self._is_grid_running(self._long_coordinator) if self._long_coordinator else False,
            "short_grid_running": self._is_grid_running(self._short_coordinator) if self._short_coordinator else False,
        }


async def create_bidirectional_grids(
    symbol: str,
    exchange_adapter,
    base_config: Dict[str, Any],
    trend_direction: str = "sideways",
) -> BidirectionalGridController:
    """
    创建双向网格（便捷工厂函数）

    Args:
        symbol: 交易对符号
        exchange_adapter: 交易所适配器
        base_config: 基础配置（从YAML加载）
        trend_direction: 初始趋势方向

    Returns:
        BidirectionalGridController: 配置好的双向网格控制器
    """
    from core.services.grid.models.grid_config import GridConfig, GridType

    controller = BidirectionalGridController()

    # 创建做多配置
    long_config = GridConfig(
        exchange=base_config.get("exchange", "lighter"),
        symbol=symbol,
        grid_type=GridType.FOLLOW_LONG,
        grid_interval=Decimal(str(base_config.get("grid_interval", 0.01))),
        order_amount=Decimal(str(base_config.get("order_amount", 0.001))),
        **base_config
    )

    # 创建做空配置
    short_config = GridConfig(
        exchange=base_config.get("exchange", "lighter"),
        symbol=symbol,
        grid_type=GridType.FOLLOW_SHORT,
        grid_interval=Decimal(str(base_config.get("grid_interval", 0.01))),
        order_amount=Decimal(str(base_config.get("order_amount", 0.001))),
        **base_config
    )

    # TODO: 创建网格协调器实例
    # 这需要完整的依赖注入，在实际使用时由调用者完成

    return controller
