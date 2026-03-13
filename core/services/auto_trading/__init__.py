"""
全自动交易模块 - Auto Trading

扫描器→选币→启动网格 全自动联动。
"""

from .auto_grid_launcher import AutoGridLauncher
from .capital_allocator import CapitalAllocator

__all__ = [
    "AutoGridLauncher",
    "CapitalAllocator",
]
