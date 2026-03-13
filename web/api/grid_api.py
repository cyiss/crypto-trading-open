"""
网格交易API路由
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from grid_volatility_scanner.storage import ScannerHistoryStorage
from web.api.security import require_api_key


class GridPerformancePayload(BaseModel):
    instance_id: str = Field(min_length=1, max_length=128)
    symbol: str = Field(min_length=1, max_length=64)
    exchange: str = Field(min_length=1, max_length=64)
    grid_type: str = Field(default="follow_long", max_length=64)
    grid_interval: float = 0
    order_amount: float = 0
    follow_distance: int = 1
    scalping_trigger_percent: int = 80
    leverage: int = 10
    volatility: float = 0
    trend_strength: float = 0
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    annualized_return: float = 0
    max_drawdown: float = 0
    trade_count: int = 0
    total_pnl: float = 0
    sharpe_ratio: float = 0
    is_ai_recommended: bool = False


def _get_storage(request: Request) -> ScannerHistoryStorage:
    return request.app.state.storage


def create_grid_router() -> APIRouter:
    router = APIRouter()

    @router.get("/instances")
    async def get_grid_instances(request: Request):
        """获取当前运行的网格实例状态

        注意：这是一个占位实现，实际的网格实例管理
        需要与 run_grid_trading.py 的进程通信。
        """
        # 暂时返回空列表，后续phase接入真实网格管理
        return {
            "instances": [],
            "total": 0,
            "query_time": datetime.now().isoformat(),
        }

    @router.get("/performance")
    async def get_grid_performance(
        request: Request,
        symbol: Optional[str] = None,
        instance_id: Optional[str] = None,
        days: int = Query(30, ge=1, le=365),
        page: int = Query(1, ge=1),
        page_size: int = Query(100, ge=1, le=1000),
    ):
        """获取网格交易绩效数据"""
        storage = _get_storage(request)
        query_result = await storage.get_grid_performance(
            symbol=symbol,
            instance_id=instance_id,
            days=days,
            page=page,
            page_size=page_size,
        )
        return query_result

    @router.post("/performance")
    async def save_grid_performance(
        request: Request,
        payload: GridPerformancePayload,
        _auth: None = Depends(require_api_key),
    ):
        """保存网格绩效数据（由网格引擎调用）"""
        storage = _get_storage(request)
        await storage.save_grid_performance(payload.model_dump())
        return {"status": "ok"}

    @router.get("/config/defaults")
    async def get_default_config():
        """获取网格交易默认配置模板"""
        return {
            "grid_types": [
                {"value": "long", "label": "普通做多"},
                {"value": "short", "label": "普通做空"},
                {"value": "follow_long", "label": "跟随做多（推荐）"},
                {"value": "follow_short", "label": "跟随做空"},
                {"value": "martingale_long", "label": "马丁做多"},
                {"value": "martingale_short", "label": "马丁做空"},
            ],
            "default_params": {
                "grid_interval": 15,
                "order_amount": 0.0002,
                "follow_grid_count": 100,
                "follow_distance": 2,
                "leverage": 20,
                "scalping_enabled": True,
                "smart_scalping_enabled": True,
                "capital_protection_enabled": True,
                "capital_protection_trigger_percent": 25,
                "exit_cleanup_enabled": True,
            },
        }

    return router
