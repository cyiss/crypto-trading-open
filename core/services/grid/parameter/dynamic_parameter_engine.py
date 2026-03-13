"""
动态参数引擎 - Dynamic Parameter Engine

整合波动率计算和参数调整，作为网格交易系统运行时的参数自动调整组件。
"""

import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any, TYPE_CHECKING

from .volatility_calculator import VolatilityCalculator, MarketIndicators
from .parameter_adjuster import ParameterAdjuster, AdjustedParameters, DynamicFallbackLimits

if TYPE_CHECKING:
    from core.services.grid.models.grid_config import GridConfig

logger = logging.getLogger(__name__)


class DynamicParameterEngine:
    """
    动态参数引擎

    核心功能：
    1. 定期获取市场指标（ATR、波动率、趋势）
    2. 根据指标自动调整网格参数
    3. 在安全边界内运行，防止过度调整
    4. 记录调整历史，便于分析

    使用方式：
        engine = DynamicParameterEngine(
            exchange_adapter=adapter,
            update_interval=600,  # 每10分钟更新一次
        )

        # 在主循环中
        new_config = await engine.update_grid_params(current_config)
    """

    def __init__(
        self,
        exchange_adapter=None,
        update_interval: int = 600,  # 默认10分钟
        atr_period: int = 14,
        volatility_window: int = 20,
        limits_config: Optional[dict] = None,
        klines_cache_ttl: int = 300,  # K线缓存5分钟
    ):
        """
        Args:
            exchange_adapter: 交易所适配器（用于获取K线）
            update_interval: 参数更新间隔（秒）
            atr_period: ATR计算周期
            volatility_window: 波动率计算窗口
            limits_config: 安全边界配置（来自YAML的dynamic_fallback段）
            klines_cache_ttl: K线数据缓存时间（秒）
        """
        self.adapter = exchange_adapter
        self.update_interval = update_interval
        self.klines_cache_ttl = klines_cache_ttl

        # 计算器和调整器
        self.calculator = VolatilityCalculator(exchange_adapter)

        limits = None
        if limits_config:
            limits = DynamicFallbackLimits.from_config(limits_config)
        self.adjuster = ParameterAdjuster(limits=limits)

        # 状态追踪
        self._last_update_time: Optional[datetime] = None
        self._last_indicators: Dict[str, MarketIndicators] = {}
        self._last_adjustments: Dict[str, AdjustedParameters] = {}
        self._adjustment_history: list = []  # 最近100次调整记录
        self._base_params: Dict[str, dict] = {}  # 原始参数（不调整的基准）

        # K线缓存
        self._klines_cache: Dict[str, tuple] = {}  # {symbol: (timestamp, klines)}

        logger.info(
            f"✅ 动态参数引擎初始化: 更新间隔={update_interval}s, "
            f"ATR周期={atr_period}, 波动率窗口={volatility_window}"
        )

    def set_base_params(self, symbol: str, params: dict):
        """
        设置基准参数（YAML中的原始配置值）

        Args:
            symbol: 交易对符号
            params: 原始参数字典，包含:
                grid_interval, order_amount, follow_grid_count,
                scalping_trigger_percent, leverage, price_decimals
        """
        self._base_params[symbol] = params

    async def update_grid_params(self, config: 'GridConfig') -> 'GridConfig':
        """
        更新网格配置参数

        这是核心方法，在网格交易主循环中定期调用。

        Args:
            config: 当前的GridConfig对象

        Returns:
            更新后的GridConfig对象（如果未到更新时间，返回原config）
        """
        now = datetime.now()
        symbol = config.symbol

        # 1. 检查是否到更新时间
        if self._last_update_time:
            elapsed = (now - self._last_update_time).total_seconds()
            if elapsed < self.update_interval:
                return config  # 还没到更新时间

        # 2. 检查是否有基准参数
        if symbol not in self._base_params:
            self._base_params[symbol] = {
                'grid_interval': config.grid_interval,
                'order_amount': config.order_amount,
                'follow_grid_count': config.follow_grid_count or 100,
                'scalping_trigger_percent': config.scalping_trigger_percent,
                'leverage': config.leverage,
                'price_decimals': config.price_decimals,
            }

        base = self._base_params[symbol]

        # 3. 获取K线数据（带缓存）
        klines = await self._get_cached_klines(symbol)

        # 4. 计算市场指标
        indicators = await self.calculator.calculate_indicators(
            symbol=symbol,
            klines=klines,
        )

        if indicators is None:
            logger.warning(f"[{symbol}] 无法计算市场指标，跳过参数调整")
            self._last_update_time = now
            return config

        self._last_indicators[symbol] = indicators

        # 5. 计算调整后的参数
        adjusted = self.adjuster.adjust_parameters(
            indicators=indicators,
            base_grid_interval=base['grid_interval'],
            base_order_amount=base['order_amount'],
            base_follow_grid_count=base['follow_grid_count'],
            base_scalping_trigger=base['scalping_trigger_percent'],
            base_leverage=base['leverage'],
        )

        self._last_adjustments[symbol] = adjusted

        # 6. 记录调整历史
        self._record_adjustment(symbol, indicators, adjusted)

        # 7. 应用调整后的参数到config
        config.grid_interval = adjusted.grid_interval
        config.order_amount = adjusted.order_amount
        config.follow_grid_count = adjusted.follow_grid_count
        config.scalping_trigger_percent = adjusted.scalping_trigger_percent
        if adjusted.leverage is not None:
            config.leverage = adjusted.leverage

        self._last_update_time = now

        # 8. 日志
        if adjusted.adjustments:
            logger.info(
                f"🔧 [{symbol}] 动态参数调整:\n"
                f"   原因: {adjusted.reason}\n"
                f"   调整项: {adjusted.adjustments}"
            )
        else:
            logger.debug(f"[{symbol}] 参数无需调整 (在正常范围内)")

        return config

    async def _get_cached_klines(self, symbol: str) -> Optional[list]:
        """获取K线数据（带缓存）"""
        now = datetime.now()

        # 检查缓存
        if symbol in self._klines_cache:
            cached_time, cached_data = self._klines_cache[symbol]
            elapsed = (now - cached_time).total_seconds()
            if elapsed < self.klines_cache_ttl:
                return cached_data

        # 缓存过期或不存在，重新获取
        try:
            klines = await self.calculator._fetch_klines(symbol, limit=500)
            if klines:
                self._klines_cache[symbol] = (now, klines)
            return klines
        except Exception as e:
            logger.error(f"[{symbol}] 获取K线缓存失败: {e}")
            return None

    def _record_adjustment(
        self,
        symbol: str,
        indicators: MarketIndicators,
        adjusted: AdjustedParameters,
    ):
        """记录调整历史"""
        record = {
            'timestamp': datetime.now().isoformat(),
            'symbol': symbol,
            'atr': float(indicators.atr),
            'atr_percent': float(indicators.atr_percent),
            'volatility': float(indicators.volatility_annualized),
            'trend_direction': indicators.trend_direction,
            'trend_strength': float(indicators.trend_strength),
            'grid_interval': float(adjusted.grid_interval),
            'order_amount': float(adjusted.order_amount),
            'follow_grid_count': adjusted.follow_grid_count,
            'scalping_trigger': adjusted.scalping_trigger_percent,
            'adjustments': adjusted.adjustments,
        }

        self._adjustment_history.append(record)

        # 限制历史长度
        if len(self._adjustment_history) > 1000:
            self._adjustment_history = self._adjustment_history[-500:]

    def get_last_adjustment(self, symbol: str) -> Optional[dict]:
        """获取某代币最近一次调整记录"""
        if symbol in self._last_adjustments:
            adj = self._last_adjustments[symbol]
            ind = self._last_indicators.get(symbol)
            return {
                'symbol': symbol,
                'adjusted': {
                    'grid_interval': float(adj.grid_interval),
                    'order_amount': float(adj.order_amount),
                    'follow_grid_count': adj.follow_grid_count,
                    'scalping_trigger': adj.scalping_trigger_percent,
                },
                'indicators': {
                    'atr': float(ind.atr) if ind else 0,
                    'atr_percent': float(ind.atr_percent) if ind else 0,
                    'volatility': float(ind.volatility_annualized) if ind else 0,
                    'trend': ind.trend_direction if ind else 'unknown',
                } if ind else None,
                'reason': adj.reason,
                'adjustments': adj.adjustments,
            }
        return None

    def get_adjustment_history(
        self,
        symbol: Optional[str] = None,
        limit: int = 50,
    ) -> list:
        """获取调整历史"""
        history = self._adjustment_history
        if symbol:
            history = [h for h in history if h['symbol'] == symbol]
        return history[-limit:]

    def get_engine_status(self) -> dict:
        """获取引擎状态"""
        return {
            'last_update': self._last_update_time.isoformat() if self._last_update_time else None,
            'update_interval': self.update_interval,
            'tracked_symbols': list(self._base_params.keys()),
            'adjustment_count': len(self._adjustment_history),
            'cache_size': len(self._klines_cache),
        }
