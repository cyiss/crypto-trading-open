"""
ML参数推荐API路由 - 完整实现

集成PerformanceTracker和AIParameterRecommender。
"""

import asyncio
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, HTTPException

from core.services.ml.performance_tracker import PerformanceTracker
from core.services.ml.parameter_recommender import AIParameterRecommender
from web.api.security import require_api_key


def _get_ml_components(request: Request) -> tuple[Optional[AIParameterRecommender], Optional[PerformanceTracker]]:
    """从app.state获取ML组件。"""
    recommender = getattr(request.app.state, "ml_recommender", None)
    tracker = getattr(request.app.state, "ml_tracker", None)
    return recommender, tracker


def create_ml_router() -> APIRouter:
    router = APIRouter()

    @router.get("/recommendations")
    async def get_recommendations(
        request: Request,
        symbol: Optional[str] = None,
        volatility: float = Query(0.5),
        trend: float = Query(0.0),
        current_apr: float = Query(0.0),
    ):
        """获取ML参数推荐"""
        ml_recommender, _ = _get_ml_components(request)
        if not ml_recommender or not ml_recommender.is_available:
            return {
                "recommendations": [],
                "model_available": False,
                "message": "ML模型未训练或scikit-learn未安装",
                "query_time": datetime.now().isoformat(),
            }

        # 默认参数
        default_params = {
            'grid_interval': 15,
            'order_amount': 0.0002,
            'follow_distance': 2,
            'scalping_trigger_percent': 80,
            'leverage': 20,
        }

        result = ml_recommender.recommend(
            current_volatility=volatility,
            current_trend=trend,
            current_params=default_params,
            current_apr=current_apr,
        )

        return {
            "recommendations": [result] if result.get('recommended') else [],
            "model_available": True,
            "query_time": datetime.now().isoformat(),
            "model_status": ml_recommender.get_status(),
        }

    @router.get("/model_status")
    async def get_model_status(request: Request):
        """获取ML模型状态"""
        ml_recommender, _ = _get_ml_components(request)
        if not ml_recommender:
            return {
                "model_available": False,
                "message": "ML推荐器未初始化",
            }
        return ml_recommender.get_status()

    @router.post("/train")
    async def trigger_training(
        request: Request,
        symbol: Optional[str] = None,
        days: int = Query(90, ge=1, le=365),
        _auth: None = Depends(require_api_key),
    ):
        """触发模型训练"""
        ml_recommender, ml_tracker = _get_ml_components(request)

        if not ml_tracker:
            raise HTTPException(status_code=503, detail="绩效记录器未初始化")
        if not ml_recommender:
            raise HTTPException(status_code=503, detail="ML推荐器未初始化")

        # 获取训练数据
        data = await ml_tracker.get_training_data(
            symbol=symbol,
            min_samples=10,
            days=days,
        )

        if not data:
            return {
                "status": "insufficient_data",
                "message": f"训练数据不足 (需要至少10条记录，当前{len(data) if data else 0}条)",
            }

        # 训练模型
        # 训练是CPU密集任务，放到线程池避免阻塞事件循环
        result = await asyncio.to_thread(ml_recommender.train, data)
        return result

    @router.get("/performance/summary")
    async def get_performance_summary(
        request: Request,
        symbol: Optional[str] = None,
        days: int = Query(30, ge=1, le=365),
    ):
        """获取绩效汇总"""
        _, ml_tracker = _get_ml_components(request)
        if not ml_tracker:
            return {"total_records": 0, "message": "绩效记录器未初始化"}

        summary = await ml_tracker.get_performance_summary(
            symbol=symbol,
            days=days,
        )
        return summary

    return router
