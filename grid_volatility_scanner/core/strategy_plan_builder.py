from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict


def _to_decimal(value, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(default)


def _clamp(value: Decimal, lower: Decimal, upper: Decimal) -> Decimal:
    return max(lower, min(upper, value))


@dataclass
class StrategyPlan:
    grid_interval: Decimal
    grid_range_percent: Decimal
    follow_grid_count: int
    startup_active_grid_count: int
    order_amount: Decimal
    startup_batch_count: int
    leverage: int
    capital_mode: str
    recommended_action: str
    exit_policy: str
    startup_required_margin: Decimal


class StrategyPlanBuilder:
    def __init__(self, scanner_config: Dict):
        self.scanner_config = scanner_config or {}

    def build(self, result) -> StrategyPlan:
        current_price = _to_decimal(getattr(result, "current_price", 0), "1")
        if current_price <= 0:
            current_price = Decimal("1")

        grid_interval_percent = _to_decimal(getattr(result, "grid_interval_percent", 0), "0.1")
        price_change_percent = abs(_to_decimal(getattr(result, "price_change_24h_percent", 0)))
        spread_p95_bps = _to_decimal(getattr(result, "spread_bps_p95", 0))

        atr_bps_proxy = max(grid_interval_percent * Decimal("100"), price_change_percent * Decimal("25"), Decimal("8"))
        min_tick_bps = Decimal(str(self.scanner_config.get("min_tick_bps", 1)))
        interval_bps = _clamp(
            max(atr_bps_proxy * Decimal("0.15"), spread_p95_bps * Decimal("1.8"), min_tick_bps * Decimal("3")),
            Decimal(str(self.scanner_config.get("min_interval_bps", 8))),
            Decimal(str(self.scanner_config.get("max_interval_bps", 120))),
        )
        range_bps = _clamp(
            max(atr_bps_proxy * Decimal("2.2"), price_change_percent * Decimal("40"), interval_bps * Decimal("12")),
            Decimal(str(self.scanner_config.get("min_range_bps", 180))),
            Decimal(str(self.scanner_config.get("max_range_bps", 2400))),
        )

        raw_grid_count = int(range_bps / interval_bps) if interval_bps > 0 else 12
        follow_grid_count = max(12, min(60, raw_grid_count))

        base_order_notional = _to_decimal(self.scanner_config.get("order_value_usdc", 10), "10")
        liquidity_cap = _to_decimal(getattr(result, "depth_same_side_0_3pct_usdc", 0)) / Decimal("20")
        single_order_notional = min(base_order_notional, liquidity_cap) if liquidity_cap > 0 else base_order_notional
        single_order_notional = _clamp(single_order_notional, Decimal("5"), Decimal("50"))

        order_amount = (single_order_notional / current_price).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        if order_amount <= 0:
            order_amount = Decimal("0.000001")

        depth_1pct = _to_decimal(getattr(result, "depth_same_side_1_0pct_usdc", 0))
        startup_active_grid_count = min(follow_grid_count, 12)
        if depth_1pct > 0 and single_order_notional > 0:
            startup_active_grid_count = min(
                startup_active_grid_count,
                max(4, int(depth_1pct / (single_order_notional * Decimal("3"))))
            )
        startup_active_grid_count = max(4, min(startup_active_grid_count, follow_grid_count))

        leverage = max(1, min(10, int(self.scanner_config.get("recommended_leverage", 5))))
        startup_required_margin = (
            single_order_notional * Decimal(str(startup_active_grid_count)) / Decimal(str(leverage))
        ).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

        liquidity_pass = bool(getattr(result, "liquidity_pass", False))
        execution_pass = bool(getattr(result, "execution_pass", False))
        rating = getattr(result, "rating_letter", "D")
        recommended_action = "watch_only"
        capital_mode = "normal"
        exit_policy = "drain_if_degraded"

        if execution_pass and liquidity_pass and rating in {"S", "A"}:
            recommended_action = "auto_launch"
            capital_mode = "aggressive" if rating == "S" else "normal"
            if rating == "A":
                startup_active_grid_count = max(4, min(startup_active_grid_count, 8))
        elif not execution_pass:
            recommended_action = "drain_only"
            capital_mode = "drain-only"
            exit_policy = "reduce_only_exit"

        grid_interval = (current_price * interval_bps / Decimal("10000")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        grid_range_percent = (range_bps / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        return StrategyPlan(
            grid_interval=grid_interval,
            grid_range_percent=grid_range_percent,
            follow_grid_count=follow_grid_count,
            startup_active_grid_count=startup_active_grid_count,
            order_amount=order_amount,
            startup_batch_count=startup_active_grid_count,
            leverage=leverage,
            capital_mode=capital_mode,
            recommended_action=recommended_action,
            exit_policy=exit_policy,
            startup_required_margin=startup_required_margin,
        )