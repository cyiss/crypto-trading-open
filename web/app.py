"""
Web Dashboard - FastAPI 主应用 (完整版)

启动方式:
    python web/app.py --port 8000
    python web/app.py --host 127.0.0.1 --port 8000 --scanner-db data/grid_scanner.db
"""

import argparse
import logging
import sys
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from grid_volatility_scanner.storage import ScannerHistoryStorage
from web.api.scanner_api import create_scanner_router
from web.api.grid_api import create_grid_router
from web.api.ml_api import create_ml_router
from web.api.auto_trading_api import create_auto_trading_router
from web.api.control_api import create_control_router

logger = logging.getLogger(__name__)

# 全局实例
storage: ScannerHistoryStorage = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global storage
    db_path = app.state.scanner_db_path
    storage = ScannerHistoryStorage(db_path)
    await storage.initialize()
    app.state.storage = storage

    # 初始化ML组件
    from core.services.ml.performance_tracker import PerformanceTracker
    from core.services.ml.parameter_recommender import AIParameterRecommender

    tracker = PerformanceTracker(db_path)
    await tracker.initialize()
    recommender = AIParameterRecommender()

    app.state.ml_tracker = tracker
    app.state.ml_recommender = recommender

    # 初始化自动交易组件（占位，实际使用时由外部注入）
    from core.services.auto_trading import AutoGridLauncher, CapitalAllocator
    launcher = AutoGridLauncher(auto_launch=False)
    allocator = CapitalAllocator(total_capital=50000)
    app.state.auto_launcher = launcher
    app.state.capital_allocator = allocator

    logger.info(f"✅ Web Dashboard已启动，数据库: {db_path}")
    yield

    await storage.close()
    await tracker.close()
    logger.info("👋 Web Dashboard已关闭")


def create_app(db_path: str = "data/grid_scanner.db") -> FastAPI:
    """创建FastAPI应用"""
    app = FastAPI(
        title="Grid Trading Dashboard",
        description="网格交易系统监控面板 - 扫描器历史、网格状态、ML推荐、自动交易",
        version="2.0.0",
        lifespan=lifespan,
    )
    app.state.scanner_db_path = db_path

    # 注册API路由
    app.include_router(create_scanner_router(), prefix="/api/scanner", tags=["Scanner"])
    app.include_router(create_grid_router(), prefix="/api/grid", tags=["Grid"])
    app.include_router(create_ml_router(), prefix="/api/ml", tags=["ML"])
    app.include_router(create_auto_trading_router(), prefix="/api/auto", tags=["Auto Trading"])
    app.include_router(create_control_router(), prefix="/api/control", tags=["Control"])

    # 静态文件和模板
    web_dir = Path(__file__).parent
    static_dir = web_dir / "static"
    template_dir = web_dir / "templates"

    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    templates = Jinja2Templates(directory=str(template_dir))

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return templates.TemplateResponse("index.html", {"request": request})

    @app.get("/scanner", response_class=HTMLResponse)
    async def scanner_page(request: Request):
        return templates.TemplateResponse("scanner.html", {"request": request})

    @app.get("/performance", response_class=HTMLResponse)
    async def performance_page(request: Request):
        return templates.TemplateResponse("performance.html", {"request": request})

    @app.get("/auto-trading", response_class=HTMLResponse)
    async def auto_trading_page(request: Request):
        return templates.TemplateResponse("auto_trading.html", {"request": request})

    @app.get("/control", response_class=HTMLResponse)
    async def control_page(request: Request):
        return templates.TemplateResponse("control.html", {"request": request})

    return app


def main():
    parser = argparse.ArgumentParser(description="Grid Trading Web Dashboard")
    parser.add_argument("--host", default="127.0.0.1", help="Host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")
    parser.add_argument("--scanner-db", default="data/grid_scanner.db", help="Scanner DB path")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    app = create_app(args.scanner_db)

    import uvicorn
    print(f"🌐 Web Dashboard: http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
