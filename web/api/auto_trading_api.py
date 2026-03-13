"""
自动交易状态API路由
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Request

from core.services.auto_trading import AutoGridLauncher, CapitalAllocator
from web.api.security import require_api_key


def _get_auto_components(request: Request) -> tuple[AutoGridLauncher | None, CapitalAllocator | None]:
    """从app.state获取自动交易组件。"""
    launcher = getattr(request.app.state, "auto_launcher", None)
    allocator = getattr(request.app.state, "capital_allocator", None)
    return launcher, allocator


def create_auto_trading_router() -> APIRouter:
    router = APIRouter()

    @router.get("/status")
    async def get_auto_trading_status(request: Request):
        """获取自动交易状态"""
        auto_launcher, capital_allocator = _get_auto_components(request)
        status = {
            "auto_launcher": auto_launcher.get_status() if auto_launcher else None,
            "capital_allocator": capital_allocator.get_status() if capital_allocator else None,
            "query_time": datetime.now().isoformat(),
        }
        return status

    @router.get("/active-grids")
    async def get_active_grids(request: Request):
        """获取自动启动的活跃网格列表"""
        auto_launcher, _ = _get_auto_components(request)
        if not auto_launcher:
            return {"grids": [], "message": "自动启动器未初始化"}

        status = auto_launcher.get_status()
        return {
            "grids": status.get('active_symbols', []),
            "paused": status.get('paused_symbols', []),
            "count": status.get('active_grids', 0),
        }

    @router.post("/resume/{symbol}")
    async def resume_grid(
        request: Request,
        symbol: str,
        _auth: None = Depends(require_api_key),
    ):
        """手动恢复暂停的网格"""
        auto_launcher, _ = _get_auto_components(request)
        if not auto_launcher:
            return {"status": "error", "message": "自动启动器未初始化"}

        was_paused = symbol in auto_launcher.get_status().get("paused_symbols", [])
        await auto_launcher.resume_grid(symbol)
        return {
            "status": "queued",
            "message": f"{symbol} 已从暂停列表移除，将在下次扫描时重新评估启动",
            "was_paused": was_paused,
        }

    @router.get("/capital")
    async def get_capital_status(request: Request):
        """获取资金分配状态"""
        _, capital_allocator = _get_auto_components(request)
        if not capital_allocator:
            return {"message": "资金分配器未初始化"}

        return capital_allocator.get_status()

    return router
