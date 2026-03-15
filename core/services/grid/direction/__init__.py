"""
网格方向管理模块

提供根据市场趋势自动切换多空方向的功能。
"""

from .grid_direction_manager import (
    GridDirectionManager,
    TradeDirection,
    TrendType,
    DirectionDecision,
    DirectionState,
)

from .bidirectional_controller import (
    BidirectionalGridController,
    DirectionWeights,
    create_bidirectional_grids,
)

__all__ = [
    # 方向管理器
    "GridDirectionManager",
    "TradeDirection",
    "TrendType",
    "DirectionDecision",
    "DirectionState",
    # 双向控制器
    "BidirectionalGridController",
    "DirectionWeights",
    "create_bidirectional_grids",
]
