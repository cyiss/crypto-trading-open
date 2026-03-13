"""
资金分配器 - Capital Allocator

跨策略资金管理：网格交易、套利等策略间的动态资金分配。
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Optional
from decimal import Decimal

logger = logging.getLogger(__name__)


@dataclass
class StrategyBucket:
    """策略资金桶"""
    name: str
    base_ratio: float       # 基础分配比例
    min_ratio: float        # 最小比例
    max_ratio: float        # 最大比例
    current_ratio: float    # 当前比例
    allocated: float = 0.0  # 已分配金额


class CapitalAllocator:
    """
    资金分配器

    管理总资金在不同策略间的分配。

    功能：
    1. 按比例分配资金给各策略
    2. 当某策略需要更多资金时，从其他策略调拨
    3. 有最大/最小比例限制，防止单一策略占用过多资金

    使用方式：
        allocator = CapitalAllocator(
            total_capital=50000,
            strategy_buckets={
                'grid': StrategyBucket('grid', 0.6, 0.3, 0.8, 0.6),
                'arbitrage': StrategyBucket('arbitrage', 0.4, 0.2, 0.7, 0.4),
            }
        )

        # 请求资金
        granted = allocator.request('grid', 10000)
        # 释放资金
        allocator.release('grid', 5000)
    """

    def __init__(
        self,
        total_capital: float,
        strategy_buckets: Optional[Dict[str, StrategyBucket]] = None,
    ):
        self.total_capital = total_capital

        # 默认网格和套利两个策略桶
        if strategy_buckets is None:
            self.buckets = {
                'grid': StrategyBucket('grid', 0.6, 0.3, 0.8, 0.6),
                'arbitrage': StrategyBucket('arbitrage', 0.4, 0.2, 0.7, 0.4),
            }
        else:
            self.buckets = strategy_buckets

        # 计算初始分配
        self._rebalance_all()

    def _rebalance_all(self):
        """重新分配所有策略的资金"""
        total_ratio = sum(b.base_ratio for b in self.buckets.values())
        if total_ratio == 0:
            total_ratio = 1.0

        for bucket in self.buckets.values():
            normalized_ratio = bucket.base_ratio / total_ratio
            bucket.current_ratio = normalized_ratio
            bucket.allocated = self.total_capital * normalized_ratio

    def request(self, strategy: str, amount: float) -> float:
        """
        请求资金

        Args:
            strategy: 策略名称
            amount: 请求金额

        Returns:
            实际授予的金额（可能小于请求数）
        """
        if strategy not in self.buckets:
            logger.warning(f"未知策略: {strategy}")
            return 0.0

        bucket = self.buckets[strategy]
        max_allowed = self.total_capital * bucket.max_ratio
        can_grant = min(amount, max_allowed - bucket.allocated)

        if can_grant > 0:
            bucket.allocated += can_grant
            # 从其他策略按比例收回
            self._redistribute(-can_grant, exclude=strategy)
            logger.debug(f"资金分配: {strategy} +${can_grant:.2f}")

        return max(0.0, can_grant)

    def release(self, strategy: str, amount: float):
        """
        释放资金

        Args:
            strategy: 策略名称
            释放金额
        """
        if strategy not in self.buckets:
            return

        bucket = self.buckets[strategy]
        released = min(amount, bucket.allocated)
        bucket.allocated -= released

        # 将释放的资金按比例分配给其他策略
        self._redistribute(released, exclude=strategy)

    def _redistribute(self, amount: float, exclude: str = None):
        """将资金在其他策略间按比例重新分配"""
        # 计算可用的策略
        others = [
            (name, b) for name, b in self.buckets.items()
            if name != exclude
        ]

        if not others:
            return

        total_ratio = sum(b.current_ratio for name, b in others)
        if total_ratio == 0:
            return

        for name, bucket in others:
            share = (bucket.current_ratio / total_ratio) * amount
            bucket.allocated += share
            # 约束在范围内
            bucket.allocated = max(
                self.total_capital * bucket.min_ratio,
                min(self.total_capital * bucket.max_ratio, bucket.allocated)
            )

    def get_available(self, strategy: str) -> float:
        """获取策略的可用资金"""
        if strategy not in self.buckets:
            return 0.0

        bucket = self.buckets[strategy]
        max_allowed = self.total_capital * bucket.max_ratio
        return max(0.0, max_allowed - bucket.allocated)

    def get_allocated(self, strategy: str) -> float:
        """获取策略已分配的资金"""
        if strategy not in self.buckets:
            return 0.0
        return self.buckets[strategy].allocated

    def get_status(self) -> Dict:
        """获取资金分配状态"""
        return {
            'total_capital': self.total_capital,
            'strategies': {
                name: {
                    'allocated': bucket.allocated,
                    'ratio': bucket.current_ratio,
                    'available': self.get_available(name),
                }
                for name, bucket in self.buckets.items()
            },
        }
