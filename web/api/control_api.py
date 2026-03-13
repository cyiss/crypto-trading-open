"""
系统控制API - System Control API

提供Web界面控制系统启动/停止/重启等操作。
"""

import asyncio
import logging
import os
import signal
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Request, HTTPException
from pydantic import BaseModel

from web.api.security import require_api_key

logger = logging.getLogger(__name__)


class ServiceStatus(BaseModel):
    """服务状态"""
    name: str
    running: bool
    pid: Optional[int] = None
    uptime_seconds: Optional[int] = None
    last_log_lines: list[str] = []


def create_control_router() -> APIRouter:
    router = APIRouter()

    @router.get("/scanner/status")
    async def get_scanner_status(request: Request):
        """获取扫描器状态"""
        try:
            # 检查扫描器进程
            import subprocess
            result = subprocess.run(
                ["pgrep", "-f", "run_scanner.py"],
                capture_output=True,
                text=True
            )

            pids = result.stdout.strip().split('\n') if result.stdout.strip() else []
            running = len(pids) > 0 and pids[0] != ''

            # 获取PID
            pid = int(pids[0]) if running else None

            # 获取运行时间
            uptime = None
            if pid:
                try:
                    uptime_result = subprocess.run(
                        ["ps", "-p", str(pid), "-o", "etimes="],
                        capture_output=True,
                        text=True
                    )
                    if uptime_result.returncode == 0:
                        uptime = int(uptime_result.stdout.strip())
                except:
                    pass

            # 读取最后几行日志
            log_lines = []
            log_file = Path("logs/scanner.log")
            if log_file.exists():
                try:
                    with open(log_file, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        log_lines = [line.strip() for line in lines[-10:] if line.strip()]
                except:
                    pass

            return {
                "running": running,
                "pid": pid,
                "uptime_seconds": uptime,
                "log_lines": log_lines,
                "status": "running" if running else "stopped"
            }

        except Exception as e:
            logger.error(f"获取扫描器状态失败: {e}")
            return {
                "running": False,
                "pid": None,
                "uptime_seconds": None,
                "log_lines": [],
                "status": "error",
                "error": str(e)
            }

    @router.post("/scanner/start")
    async def start_scanner(
        request: Request,
        _auth: None = Depends(require_api_key)
    ):
        """启动扫描器"""
        try:
            # 检查是否已运行
            import subprocess
            result = subprocess.run(
                ["pgrep", "-f", "run_scanner.py"],
                capture_output=True,
                text=True
            )

            if result.stdout.strip():
                return {
                    "status": "already_running",
                    "message": "扫描器已在运行中",
                    "pid": int(result.stdout.strip().split('\n')[0])
                }

            # 启动扫描器
            log_file = Path("logs/scanner.log")
            log_file.parent.mkdir(parents=True, exist_ok=True)

            subprocess.Popen(
                ["python", "grid_volatility_scanner/run_scanner.py", "--web", "--exchange", "lighter"],
                stdout=open(log_file, 'a'),
                stderr=subprocess.STDOUT,
                start_new_session=True,
                cwd=Path.cwd()
            )

            # 等待启动
            await asyncio.sleep(3)

            # 检查是否启动成功
            result = subprocess.run(
                ["pgrep", "-f", "run_scanner.py"],
                capture_output=True,
                text=True
            )

            if result.stdout.strip():
                return {
                    "status": "started",
                    "message": "扫描器启动成功",
                    "pid": int(result.stdout.strip().split('\n')[0])
                }
            else:
                return {
                    "status": "error",
                    "message": "扫描器启动失败，请检查日志"
                }

        except Exception as e:
            logger.error(f"启动扫描器失败: {e}")
            raise HTTPException(status_code=500, detail=f"启动失败: {str(e)}")

    @router.post("/scanner/stop")
    async def stop_scanner(
        request: Request,
        _auth: None = Depends(require_api_key)
    ):
        """停止扫描器"""
        try:
            import subprocess

            # 查找进程
            result = subprocess.run(
                ["pgrep", "-f", "run_scanner.py"],
                capture_output=True,
                text=True
            )

            if not result.stdout.strip():
                return {
                    "status": "not_running",
                    "message": "扫描器未运行"
                }

            # 停止所有相关进程
            pids = result.stdout.strip().split('\n')
            stopped_pids = []

            for pid in pids:
                try:
                    os.kill(int(pid), signal.SIGTERM)
                    stopped_pids.append(int(pid))
                except ProcessLookupError:
                    pass

            # 等待进程结束
            await asyncio.sleep(2)

            # 强制杀死未结束的进程
            result = subprocess.run(
                ["pgrep", "-f", "run_scanner.py"],
                capture_output=True,
                text=True
            )

            if result.stdout.strip():
                subprocess.run(["pkill", "-9", "-f", "run_scanner.py"])

            return {
                "status": "stopped",
                "message": f"扫描器已停止",
                "stopped_pids": stopped_pids
            }

        except Exception as e:
            logger.error(f"停止扫描器失败: {e}")
            raise HTTPException(status_code=500, detail=f"停止失败: {str(e)}")

    @router.post("/scanner/restart")
    async def restart_scanner(
        request: Request,
        _auth: None = Depends(require_api_key)
    ):
        """重启扫描器"""
        try:
            # 停止
            await stop_scanner(request, _auth)
            await asyncio.sleep(2)

            # 启动
            result = await start_scanner(request, _auth)
            return {
                "status": "restarted",
                "message": "扫描器已重启",
                **result
            }
        except Exception as e:
            logger.error(f"重启扫描器失败: {e}")
            raise HTTPException(status_code=500, detail=f"重启失败: {str(e)}")

    @router.get("/dashboard/status")
    async def get_dashboard_status(request: Request):
        """获取Dashboard状态"""
        try:
            import subprocess
            result = subprocess.run(
                ["pm2", "jlist"],
                capture_output=True,
                text=True
            )

            import json
            processes = json.loads(result.stdout) if result.stdout else []

            crypto_grid = next(
                (p for p in processes if p.get('name') == 'crypto_grid'),
                None
            )

            if crypto_grid:
                return {
                    "running": crypto_grid.get('pm2_env', {}).get('status') == 'online',
                    "pid": crypto_grid.get('pid'),
                    "uptime_seconds": crypto_grid.get('pm2_env', {}).get('pm_uptime'),
                    "memory": crypto_grid.get('monit', {}).get('memory'),
                    "cpu": crypto_grid.get('monit', {}).get('cpu'),
                    "restarts": crypto_grid.get('pm2_env', {}).get('restart_time', 0),
                    "status": crypto_grid.get('pm2_env', {}).get('status')
                }
            else:
                return {
                    "running": False,
                    "status": "not_found"
                }

        except Exception as e:
            logger.error(f"获取Dashboard状态失败: {e}")
            return {
                "running": False,
                "status": "error",
                "error": str(e)
            }

    @router.post("/dashboard/restart")
    async def restart_dashboard(
        request: Request,
        _auth: None = Depends(require_api_key)
    ):
        """重启Dashboard"""
        try:
            import subprocess
            result = subprocess.run(
                ["pm2", "restart", "crypto_grid"],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                return {
                    "status": "restarted",
                    "message": "Dashboard已重启"
                }
            else:
                return {
                    "status": "error",
                    "message": result.stderr
                }
        except Exception as e:
            logger.error(f"重启Dashboard失败: {e}")
            raise HTTPException(status_code=500, detail=f"重启失败: {str(e)}")

    @router.get("/logs/{service}")
    async def get_logs(
        request: Request,
        service: str,
        lines: int = 50
    ):
        """获取服务日志"""
        try:
            log_file = None

            if service == "scanner":
                log_file = Path("logs/scanner.log")
            elif service == "dashboard":
                log_file = Path("/root/.pm2/logs/crypto_grid-out.log")
            elif service == "dashboard_error":
                log_file = Path("/root/.pm2/logs/crypto_grid-error.log")
            else:
                raise HTTPException(status_code=404, detail="未知服务")

            if not log_file.exists():
                return {
                    "service": service,
                    "lines": [],
                    "message": "日志文件不存在"
                }

            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                all_lines = f.readlines()
                log_lines = [line.strip() for line in all_lines[-lines:] if line.strip()]

            return {
                "service": service,
                "lines": log_lines,
                "total_lines": len(all_lines)
            }

        except Exception as e:
            logger.error(f"获取日志失败: {e}")
            raise HTTPException(status_code=500, detail=f"获取日志失败: {str(e)}")

    return router
