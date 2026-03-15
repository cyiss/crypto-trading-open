from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Deque, Optional

from core.adapters.exchanges.models import OrderBookData


def _to_decimal(value, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(default)


def _bps(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator <= 0:
        return Decimal("0")
    return (numerator / denominator) * Decimal("10000")


@dataclass
class LiquiditySnapshot:
    spread_bps_p50: Decimal = Decimal("0")
    spread_bps_p95: Decimal = Decimal("0")
    depth_bid_0_3pct_usdc: Decimal = Decimal("0")
    depth_ask_0_3pct_usdc: Decimal = Decimal("0")
    depth_bid_1_0pct_usdc: Decimal = Decimal("0")
    depth_ask_1_0pct_usdc: Decimal = Decimal("0")
    estimated_slippage_10usd_bps: Decimal = Decimal("999")
    estimated_slippage_startup_batch_bps: Decimal = Decimal("999")
    orderbook_freshness_ratio: Decimal = Decimal("0")
    best_bid: Decimal = Decimal("0")
    best_ask: Decimal = Decimal("0")
    mid_price: Decimal = Decimal("0")


@dataclass
class LiquidityTracker:
    spread_samples: Deque[Decimal] = field(default_factory=lambda: deque(maxlen=60))
    refresh_attempts: int = 0
    refresh_successes: int = 0
    latest_snapshot: LiquiditySnapshot = field(default_factory=LiquiditySnapshot)

    def record_orderbook(
        self,
        orderbook: Optional[OrderBookData],
        single_order_notional: Decimal,
        startup_batch_notional: Decimal,
    ) -> LiquiditySnapshot:
        self.refresh_attempts += 1
        if not orderbook or not orderbook.best_bid or not orderbook.best_ask:
            self.latest_snapshot.orderbook_freshness_ratio = self._freshness_ratio()
            return self.latest_snapshot

        self.refresh_successes += 1
        best_bid = _to_decimal(orderbook.best_bid.price)
        best_ask = _to_decimal(orderbook.best_ask.price)
        mid_price = (best_bid + best_ask) / Decimal("2") if best_bid > 0 and best_ask > 0 else Decimal("0")
        spread_bps = _bps(best_ask - best_bid, mid_price)
        self.spread_samples.append(spread_bps)

        snapshot = LiquiditySnapshot(
            spread_bps_p50=self._quantile(Decimal("0.50")),
            spread_bps_p95=self._quantile(Decimal("0.95")),
            depth_bid_0_3pct_usdc=self._depth_notional(orderbook, "bid", Decimal("0.003"), mid_price),
            depth_ask_0_3pct_usdc=self._depth_notional(orderbook, "ask", Decimal("0.003"), mid_price),
            depth_bid_1_0pct_usdc=self._depth_notional(orderbook, "bid", Decimal("0.01"), mid_price),
            depth_ask_1_0pct_usdc=self._depth_notional(orderbook, "ask", Decimal("0.01"), mid_price),
            estimated_slippage_10usd_bps=self._estimate_slippage_bps(orderbook, single_order_notional, mid_price),
            estimated_slippage_startup_batch_bps=self._estimate_slippage_bps(orderbook, startup_batch_notional, mid_price),
            orderbook_freshness_ratio=self._freshness_ratio(),
            best_bid=best_bid,
            best_ask=best_ask,
            mid_price=mid_price,
        )
        self.latest_snapshot = snapshot
        return snapshot

    def mark_failure(self) -> LiquiditySnapshot:
        self.refresh_attempts += 1
        self.latest_snapshot.orderbook_freshness_ratio = self._freshness_ratio()
        return self.latest_snapshot

    def _freshness_ratio(self) -> Decimal:
        if self.refresh_attempts <= 0:
            return Decimal("0")
        return Decimal(str(self.refresh_successes)) / Decimal(str(self.refresh_attempts))

    def _quantile(self, ratio: Decimal) -> Decimal:
        if not self.spread_samples:
            return Decimal("0")
        samples = sorted(self.spread_samples)
        index = int((len(samples) - 1) * float(ratio))
        return samples[max(0, min(index, len(samples) - 1))]

    def _depth_notional(
        self,
        orderbook: OrderBookData,
        side: str,
        width_ratio: Decimal,
        mid_price: Decimal,
    ) -> Decimal:
        if mid_price <= 0:
            return Decimal("0")

        levels = orderbook.bids if side == "bid" else orderbook.asks
        if side == "bid":
            threshold = mid_price * (Decimal("1") - width_ratio)
            return sum(
                _to_decimal(level.price) * _to_decimal(level.size)
                for level in levels
                if _to_decimal(level.price) >= threshold
            )

        threshold = mid_price * (Decimal("1") + width_ratio)
        return sum(
            _to_decimal(level.price) * _to_decimal(level.size)
            for level in levels
            if _to_decimal(level.price) <= threshold
        )

    def _estimate_slippage_bps(
        self,
        orderbook: OrderBookData,
        target_notional: Decimal,
        mid_price: Decimal,
    ) -> Decimal:
        if target_notional <= 0 or mid_price <= 0:
            return Decimal("0")

        remaining = target_notional
        filled_notional = Decimal("0")
        filled_quantity = Decimal("0")
        for level in orderbook.asks:
            price = _to_decimal(level.price)
            size = _to_decimal(level.size)
            if price <= 0 or size <= 0:
                continue

            level_notional = price * size
            take_notional = min(remaining, level_notional)
            take_size = take_notional / price
            filled_notional += take_notional
            filled_quantity += take_size
            remaining -= take_notional
            if remaining <= 0:
                break

        if filled_notional <= 0 or filled_quantity <= 0:
            return Decimal("999")

        avg_fill_price = filled_notional / filled_quantity
        slippage = _bps(avg_fill_price - mid_price, mid_price)
        if remaining > 0:
            slippage += Decimal("100")
        return slippage