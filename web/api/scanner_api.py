"""
扫描器API路由
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Query, Request

from grid_volatility_scanner.storage import ScannerHistoryStorage


def _get_storage(request: Request) -> ScannerHistoryStorage:
    return request.app.state.storage


def create_scanner_router() -> APIRouter:
    router = APIRouter()

    @router.get("/current")
    async def get_current_status(request: Request):
        """获取当前扫描器实时状态"""
        storage = _get_storage(request)
        exchange = request.query_params.get("exchange")
        results = await storage.get_latest_snapshots(exchange=exchange, limit=50)

        # 统计评级
        rating_counts = {}
        for r in results:
            rating = r.get("rating", "")
            rating_counts[rating] = rating_counts.get(rating, 0) + 1

        return {
            "status": "available",
            "exchange": exchange,
            "results": results,
            "rating_counts": rating_counts,
            "total_symbols": len(results),
            "query_time": datetime.now().isoformat(),
        }

    @router.get("/history")
    async def get_history(
        request: Request,
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        exchange: Optional[str] = None,
        rating: Optional[str] = None,
        symbol: Optional[str] = None,
        hours: int = Query(24, ge=1, le=720),
    ):
        """获取扫描器历史记录"""
        storage = _get_storage(request)
        data = await storage.get_snapshots_by_time(
            hours=hours,
            exchange=exchange,
            symbol=symbol,
            rating=rating if rating and rating != "all" else None,
            page=page,
            page_size=page_size,
        )

        return data

    @router.get("/snapshots/{symbol}")
    async def get_symbol_trend(
        request: Request,
        symbol: str,
        hours: int = Query(24, ge=1),
        exchange: Optional[str] = None,
    ):
        """获取某代币的APR历史趋势"""
        storage = _get_storage(request)
        return await storage.get_apr_trend(symbol=symbol, hours=hours, exchange=exchange)

    @router.get("/summaries")
    async def get_summaries(
        request: Request,
        limit: int = Query(20, ge=1, le=100),
        exchange: Optional[str] = None,
    ):
        """获取扫描汇总列表"""
        storage = _get_storage(request)
        return await storage.get_summaries(limit=limit, exchange=exchange)

    @router.get("/statistics")
    async def get_statistics(
        request: Request,
        exchange: Optional[str] = None,
    ):
        """获取扫描器统计概览"""
        storage = _get_storage(request)
        return await storage.get_statistics(exchange=exchange)

    @router.get("/symbols")
    async def get_symbols_list(
        request: Request,
        exchange: Optional[str] = None,
        hours: int = Query(24, ge=1),
    ):
        """获取所有扫描过的代币列表"""
        storage = _get_storage(request)
        data = await storage.get_snapshots_by_time(hours=hours, exchange=exchange, page=1, page_size=10000)
        symbols = list(set(r["symbol"] for r in data.get("data", [])))
        symbols.sort()
        return {"symbols": symbols, "count": len(symbols)}

    return router
