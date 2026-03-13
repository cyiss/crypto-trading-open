"""
波动率计算器 - Volatility Calculator

计算ATR、收益率标准差、趋势强度等指标，为动态参数调整提供数据基础。
"""

import logging
from decimal import Decimal
from typing import List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class MarketIndicators:
    """市场指标快照"""
    symbol: str
    timestamp: datetime
    atr: Decimal                          # Average True Range (14周期)
    atr_percent: Decimal                  # ATR相对于当前价格的百分比
    volatility_daily: Decimal             # 日波动率（年化前）
    volatility_annualized: Decimal        # 年化波动率
    trend_strength: Decimal               # 趋势强度 (-1.0 ~ 1.0)
    trend_direction: str                  # "bullish" / "bearish" / "sideways"
    ema_fast: Decimal                     # EMA快线值
    ema_slow: Decimal                     # EMA慢线值
    current_price: Decimal                # 当前价格
    avg_volume: Decimal                   # 平均成交量


class VolatilityCalculator:
    """
    波动率计算器

    从K线数据中计算各类波动率和趋势指标。
    支持从交易所适配器获取历史K线数据。
    """

    def __init__(self, exchange_adapter=None):
        """
        Args:
            exchange_adapter: 交易所适配器，用于获取K线数据
        """
        self.adapter = exchange_adapter

    async def calculate_indicators(
        self,
        symbol: str,
        klines: Optional[List[dict]] = None,
        atr_period: int = 14,
        ema_fast_period: int = 20,
        ema_slow_period: int = 50,
        volatility_window: int = 20,
    ) -> Optional[MarketIndicators]:
        """
        计算市场指标

        Args:
            symbol: 交易对符号
            klines: K线数据列表，每项为 dict {time, open, high, low, close, volume}
                    如果为None，则尝试从adapter获取
            atr_period: ATR计算周期（默认14）
            ema_fast_period: EMA快线周期（默认20）
            ema_slow_period: EMA慢线周期（默认50）
            volatility_window: 波动率计算窗口（默认20）

        Returns:
            MarketIndicators 或 None（如果数据不足）
        """
        # 获取K线数据
        if klines is None and self.adapter:
            klines = await self._fetch_klines(symbol, max(500, ema_slow_period * 3))

        if not klines or len(klines) < ema_slow_period:
            logger.warning(f"[{symbol}] K线数据不足: {len(klines) if klines else 0} 根")
            return None

        # 转换为DataFrame
        df = pd.DataFrame(klines)
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)

        current_price = Decimal(str(df['close'].iloc[-1]))

        # 1. 计算 ATR
        atr = self._calculate_atr(df, atr_period)
        atr_percent = (Decimal(str(atr)) / current_price * Decimal('100'))

        # 2. 计算波动率（日收益率标准差）
        daily_vol = self._calculate_daily_volatility(df, volatility_window)
        annualized_vol = Decimal(str(float(daily_vol) * np.sqrt(365)))

        # 3. 计算趋势强度和方向
        ema_fast = df['close'].ewm(span=ema_fast_period, adjust=False).mean().iloc[-1]
        ema_slow = df['close'].ewm(span=ema_slow_period, adjust=False).mean().iloc[-1]
        trend_strength = self._calculate_trend_strength(df, ema_fast_period, ema_slow_period)
        trend_direction = self._determine_trend_direction(ema_fast, ema_slow, current_price)

        # 4. 平均成交量
        avg_volume = Decimal(str(df['volume'].tail(20).mean()))

        return MarketIndicators(
            symbol=symbol,
            timestamp=datetime.now(),
            atr=Decimal(str(round(atr, 8))),
            atr_percent=Decimal(str(round(float(atr_percent), 4))),
            volatility_daily=daily_vol,
            volatility_annualized=annualized_vol,
            trend_strength=Decimal(str(round(trend_strength, 4))),
            trend_direction=trend_direction,
            ema_fast=Decimal(str(round(ema_fast, 8))),
            ema_slow=Decimal(str(round(ema_slow, 8))),
            current_price=current_price,
            avg_volume=avg_volume,
        )

    def _calculate_atr(self, df: pd.DataFrame, period: int) -> float:
        """
        计算Average True Range

        ATR = MA(True Range, period)
        True Range = max(high-low, |high-prev_close|, |low-prev_close|)
        """
        high = df['high']
        low = df['low']
        close = df['close']
        prev_close = close.shift(1)

        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs()
        ], axis=1).max(axis=1)

        atr = tr.rolling(window=period).mean().iloc[-1]
        return atr if not np.isnan(atr) else 0.0

    def _calculate_daily_volatility(self, df: pd.DataFrame, window: int) -> Decimal:
        """
        计算日波动率

        日收益率 = ln(close / prev_close)
        日波动率 = std(日收益率, window)
        """
        close = df['close']
        returns = np.log(close / close.shift(1)).dropna()
        daily_vol = returns.rolling(window=window).std().iloc[-1]

        if np.isnan(daily_vol) or daily_vol <= 0:
            daily_vol = 0.01  # 默认1%

        return Decimal(str(round(daily_vol, 6)))

    def _calculate_trend_strength(
        self,
        df: pd.DataFrame,
        fast_period: int,
        slow_period: int
    ) -> float:
        """
        计算趋势强度 (-1.0 ~ 1.0)

        基于EMA差值的归一化：
        - 1.0 = 强烈上涨趋势
        - -1.0 = 强烈下跌趋势
        - 0 = 无趋势/震荡
        """
        ema_fast = df['close'].ewm(span=fast_period, adjust=False).mean()
        ema_slow = df['close'].ewm(span=slow_period, adjust=False).mean()

        # EMA差值百分比
        diff_pct = (ema_fast - ema_slow) / ema_slow

        # 使用最近20个值的平均
        recent_diff = diff_pct.tail(20).mean()

        # 归一化到 [-1, 1]（假设最大差距为10%）
        normalized = np.clip(float(recent_diff) * 10, -1.0, 1.0)

        return round(normalized, 4)

    def _determine_trend_direction(
        self,
        ema_fast: float,
        ema_slow: float,
        current_price: Decimal,
    ) -> str:
        """判断趋势方向"""
        price = float(current_price)

        if ema_fast > ema_slow * 1.005:  # EMA快线高于慢线0.5%
            if price > ema_fast:
                return "bullish"  # 强烈看涨
            return "bullish"
        elif ema_fast < ema_slow * 0.995:  # EMA快线低于慢线0.5%
            if price < ema_fast:
                return "bearish"  # 强烈看跌
            return "bearish"
        else:
            return "sideways"  # 震荡

    async def _fetch_klines(
        self,
        symbol: str,
        limit: int = 500,
        interval: str = "1h"
    ) -> Optional[List[dict]]:
        """
        从交易所适配器获取K线数据

        尝试多种方法获取K线：
        1. adapter.fetch_ohlcv()
        2. adapter.get_klines()
        3. 通过REST API
        """
        if not self.adapter:
            return None

        try:
            # 方法1: 直接调用fetch_ohlcv（ccxt兼容接口）
            if hasattr(self.adapter, 'fetch_ohlcv'):
                klines = await self.adapter.fetch_ohlcv(
                    symbol, timeframe=interval, limit=limit
                )
                return [
                    {"time": k[0], "open": k[1], "high": k[2],
                     "low": k[3], "close": k[4], "volume": k[5]}
                    for k in klines
                ]

            # 方法2: 通过REST客户端获取K线
            if hasattr(self.adapter, 'get_klines'):
                return await self.adapter.get_klines(symbol, interval=interval, limit=limit)

            logger.warning(f"[{symbol}] 交易所适配器不支持K线查询")
            return None

        except Exception as e:
            logger.error(f"[{symbol}] 获取K线数据失败: {e}")
            return None

    @staticmethod
    def calculate_grid_interval_from_atr(
        atr: Decimal,
        current_price: Decimal,
        min_ratio: float = 0.12,
        max_ratio: float = 0.22,
        price_decimals: int = 2,
    ) -> Decimal:
        """
        根据ATR计算推荐的网格间距

        Args:
            atr: ATR值
            current_price: 当前价格
            min_ratio: ATR最小比例（默认12%）
            max_ratio: ATR最大比例（默认22%）
            price_decimals: 价格精度

        Returns:
            推荐的网格间距（绝对价格）
        """
        import random
        ratio = random.uniform(min_ratio, max_ratio)
        raw_interval = atr * Decimal(str(ratio))

        # 约束范围
        min_interval = max(Decimal('0.5'), current_price * Decimal('0.001'))
        max_interval = min(Decimal('500'), current_price * Decimal('0.05'))

        interval = max(min_interval, min(raw_interval, max_interval))

        # 四舍五入到指定精度
        if price_decimals <= 0:
            return interval.quantize(Decimal('1'))
        quantizer = Decimal(10) ** (-price_decimals)
        return interval.quantize(quantizer)

    @staticmethod
    def calculate_order_amount_from_volatility(
        volatility_annualized: Decimal,
        base_amount: Decimal,
        min_multiplier: float = 0.5,
        max_multiplier: float = 2.0,
    ) -> Decimal:
        """
        根据波动率计算推荐的下单量

        波动率越高 → 单格仓位越小
        波动率越低 → 单格仓位可以稍大

        Args:
            volatility_annualized: 年化波动率
            base_amount: 基础下单量
            min_multiplier: 最小倍数
            max_multiplier: 最大倍数

        Returns:
            推荐的下单量
        """
        vol = float(volatility_annualized)
        risk_factor = 1.0 / (1.0 + vol * 5.0)  # 波动率越大，因子越小
        multiplier = max(min_multiplier, min(max_multiplier, risk_factor))
        return base_amount * Decimal(str(round(multiplier, 4)))
