"""
系统控制API - System Control API

提供Web界面控制系统启动/停止/重启等操作。
"""

import asyncio
import copy
import json
import logging
import os
import re
import shlex
import signal
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from typing import Optional, Any

import yaml

from fastapi import APIRouter, Depends, Request, HTTPException
from pydantic import BaseModel, Field

from grid_volatility_scanner.storage import ScannerHistoryStorage
from run_grid_trading import load_config as load_grid_runtime_config, create_grid_config

from web.api.security import require_api_key

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path.cwd()
GRID_CONFIG_DIR = PROJECT_ROOT / "config" / "grid"
GRID_RUNTIME_CONFIG_DIR = GRID_CONFIG_DIR / "_runtime"
GRID_LOG_DIR = PROJECT_ROOT / "logs"


class ServiceStatus(BaseModel):
    """服务状态"""
    name: str
    running: bool
    pid: Optional[int] = None
    uptime_seconds: Optional[int] = None
    last_log_lines: list[str] = []


class GridActionPayload(BaseModel):
    symbol: Optional[str] = Field(default=None, min_length=1, max_length=64)
    config_path: Optional[str] = Field(default=None, min_length=1, max_length=256)
    dynamic: bool = True
    debug: bool = False


class GridPreflightResponse(BaseModel):
    symbol: str
    config_path: str
    checks: dict[str, Any]
    order_preview: dict[str, Any]
    effective_plan: dict[str, Any] = {}
    warnings: list[str] = []


def _build_preflight_startup_margin_check(
    grid_config,
    preview_price: Optional[Decimal],
    available_usdc: Decimal,
) -> dict[str, Any]:
    startup_count = min(grid_config.startup_active_grid_count or grid_config.grid_count, grid_config.grid_count)
    leverage = Decimal(str(max(grid_config.leverage, 1)))
    result: dict[str, Any] = {
        "status": "unknown",
        "source": "rest_available_balance",
        "summary": "预检未能估算启动保证金",
        "startup_order_count": startup_count,
        "available_balance_usdc": str(available_usdc.quantize(Decimal("0.0001"))),
    }

    if not preview_price or preview_price <= 0:
        result["summary"] = "缺少有效最新价，无法估算本次启动是否能下出首单"
        return result

    orders: list[dict[str, Any]] = []
    is_long = grid_config.grid_type.value in {"long", "martingale_long", "follow_long"}
    for grid_id in range(1, grid_config.grid_count + 1):
        price = grid_config.get_grid_price(grid_id)
        amount = grid_config.get_formatted_grid_order_amount(grid_id)
        orders.append({
            "grid_id": grid_id,
            "price": price,
            "amount": amount,
            "side": "buy" if is_long else "sell",
        })

    prioritized_orders = sorted(
        orders,
        key=lambda order: (
            abs(order["price"] - preview_price),
            0 if order["side"] == "buy" else 1,
            -order["price"] if order["side"] == "buy" else order["price"],
        ),
    )
    startup_orders = prioritized_orders[:startup_count]
    if not startup_orders:
        result["summary"] = "预检未生成可启动的网格订单"
        return result

    usable_margin = available_usdc * Decimal("0.95") if available_usdc > 0 else Decimal("0")
    first_order = startup_orders[0]
    first_order_margin = (max(preview_price, first_order["price"]) * first_order["amount"]) / leverage
    startup_margin = sum(
        (max(preview_price, order["price"]) * order["amount"]) / leverage
        for order in startup_orders
    )
    startup_margin_1x = sum(
        max(preview_price, order["price"]) * order["amount"]
        for order in startup_orders
    )

    result.update({
        "first_order_margin_usdc": str(first_order_margin.quantize(Decimal("0.0001"))),
        "startup_margin_usdc": str(startup_margin.quantize(Decimal("0.0001"))),
        "startup_margin_1x_usdc": str(startup_margin_1x.quantize(Decimal("0.0001"))),
        "usable_margin_usdc": str(usable_margin.quantize(Decimal("0.0001"))),
        "first_order": {
            "grid_id": first_order["grid_id"],
            "side": first_order["side"],
            "price": str(first_order["price"]),
            "amount": str(first_order["amount"]),
        },
    })

    if usable_margin <= 0:
        result["status"] = "blocked"
        result["summary"] = "REST 可用余额为 0 或未返回；本次启动大概率连首单都不会提交"
        return result

    if first_order_margin > usable_margin:
        result["status"] = "blocked"
        result["summary"] = (
            f"按 REST 可用余额估算，本次启动连首单都不够，required={first_order_margin:.4f} USDC, usable={usable_margin:.4f} USDC"
        )
        return result

    if startup_margin > usable_margin:
        result["status"] = "partial"
        result["summary"] = (
            f"首单可下，但不足以覆盖 {startup_count} 个启动单；引擎会裁剪启动挂单，required={startup_margin:.4f} USDC, usable={usable_margin:.4f} USDC"
        )
        return result

    if usable_margin < startup_margin_1x:
        result["status"] = "leverage_dependent"
        result["summary"] = (
            f"按配置杠杆可覆盖启动单，但若交易所端实际仍接近 1x，可能继续报 not enough margin，required_1x={startup_margin_1x:.4f} USDC"
        )
        return result

    result["status"] = "ready"
    result["summary"] = f"按 REST 可用余额估算，本次启动的 {startup_count} 个启动单可覆盖"
    return result


def _get_storage(request: Request) -> ScannerHistoryStorage:
    return request.app.state.storage


def _run_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, cwd=PROJECT_ROOT)


def _read_last_lines(log_file: Path, line_count: int = 10) -> list[str]:
    if not log_file.exists():
        return []
    try:
        with open(log_file, "r", encoding="utf-8", errors="ignore") as file_obj:
            lines = file_obj.readlines()
        return [line.strip() for line in lines[-line_count:] if line.strip()]
    except OSError:
        return []


def _get_pid_uptime(pid: int) -> Optional[int]:
    try:
        uptime_result = _run_command(["ps", "-p", str(pid), "-o", "etimes="])
        if uptime_result.returncode == 0 and uptime_result.stdout.strip():
            return int(uptime_result.stdout.strip())
    except Exception:
        return None
    return None


def _resolve_grid_config(config_path: Optional[str], symbol: Optional[str]) -> Path:
    if config_path:
        candidate = Path(config_path)
        if not candidate.is_absolute():
            candidate = (PROJECT_ROOT / candidate).resolve()
        else:
            candidate = candidate.resolve()

        try:
            candidate.relative_to(GRID_CONFIG_DIR.resolve())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="配置文件必须位于 config/grid 目录下") from exc

        if not candidate.exists():
            raise HTTPException(status_code=404, detail="配置文件不存在")
        return candidate

    if not symbol:
        raise HTTPException(status_code=400, detail="必须提供 symbol 或 config_path")

    target_symbol = symbol.upper()
    matches = []
    for path in sorted(GRID_CONFIG_DIR.glob("*.yaml")):
        metadata = _read_grid_config_metadata(path)
        if metadata.get("symbol") == target_symbol:
            matches.append(path)

    if not matches:
        raise HTTPException(status_code=404, detail=f"未找到 {target_symbol} 的网格配置")
    if len(matches) > 1:
        raise HTTPException(status_code=400, detail=f"{target_symbol} 存在多个配置，请指定 config_path")
    return matches[0]


def _extract_config_path_from_command(command: str) -> Optional[str]:
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()

    for token in tokens:
        normalized = token.strip()
        if normalized.endswith(".yaml") and "config/grid/" in normalized.replace("\\", "/"):
            candidate = Path(normalized)
            if not candidate.is_absolute():
                candidate = (PROJECT_ROOT / candidate).resolve()
            try:
                return candidate.relative_to(PROJECT_ROOT).as_posix()
            except ValueError:
                return candidate.as_posix()
    return None


def _grid_log_path(symbol: str) -> Path:
    safe_symbol = re.sub(r"[^a-zA-Z0-9_-]+", "_", symbol.strip().lower()).strip("_") or "unknown"
    return GRID_LOG_DIR / f"grid_{safe_symbol}.log"


def _read_grid_config_metadata(config_path: Path) -> dict[str, Any]:
    try:
        with open(config_path, "r", encoding="utf-8") as file_obj:
            config_data = yaml.safe_load(file_obj) or {}
    except Exception as exc:
        logger.warning(f"读取网格配置失败 {config_path}: {exc}")
        config_data = {}

    grid_system = config_data.get("grid_system", {})
    symbol = str(grid_system.get("symbol", config_path.stem)).upper()
    return {
        "symbol": symbol,
        "exchange": str(grid_system.get("exchange", "")).lower(),
        "grid_type": grid_system.get("grid_type", ""),
        "config_path": config_path.relative_to(PROJECT_ROOT).as_posix(),
        "config_name": config_path.name,
        "leverage": grid_system.get("leverage"),
        "margin_mode": grid_system.get("margin_mode"),
        "grid_interval": grid_system.get("grid_interval"),
        "order_amount": grid_system.get("order_amount"),
        "price_decimals": grid_system.get("price_decimals"),
        "quantity_precision": grid_system.get("quantity_precision"),
        "dynamic_default": True,
        "log_file": _grid_log_path(symbol).relative_to(PROJECT_ROOT).as_posix(),
    }


async def _get_latest_scanner_snapshot(storage: ScannerHistoryStorage, symbol: str, exchange: Optional[str]) -> Optional[dict[str, Any]]:
    if not storage:
        return None

    rows = await storage.get_latest_snapshots(exchange=exchange, limit=200)
    target_symbol = str(symbol or "").upper()
    for row in rows:
        if str(row.get("symbol", "")).upper() == target_symbol:
            return row
    return None


def _apply_scanner_runtime_plan(config_data: dict[str, Any], scanner_row: Optional[dict[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    runtime_config = copy.deepcopy(config_data)
    warnings: list[str] = []
    if not scanner_row:
        return runtime_config, warnings

    grid_system = runtime_config.get("grid_system", {})
    if str(grid_system.get("grid_type", "")) not in {"follow_long", "follow_short"}:
        return runtime_config, warnings

    recommended_action = str(scanner_row.get("recommended_action") or "watch_only")
    if recommended_action not in {"auto_launch", "keep_running"}:
        warnings.append(f"当前扫描推荐动作为 {recommended_action}，已仅同步安全参数，不改变人工启动权限")

    follow_grid_count = int(scanner_row.get("follow_grid_count_recommended") or grid_system.get("follow_grid_count") or 0)
    startup_active_grid_count = int(scanner_row.get("startup_active_grid_count") or grid_system.get("startup_active_grid_count") or 0)
    grid_interval = scanner_row.get("grid_interval_recommended")
    order_amount = scanner_row.get("order_amount_recommended")
    leverage = scanner_row.get("leverage_recommended")

    if follow_grid_count > 0:
        grid_system["follow_grid_count"] = follow_grid_count
    if startup_active_grid_count > 0:
        grid_system["startup_active_grid_count"] = min(startup_active_grid_count, grid_system["follow_grid_count"])
    elif grid_system.get("follow_grid_count"):
        grid_system["startup_active_grid_count"] = min(int(grid_system["follow_grid_count"]), 8)

    if grid_interval and float(grid_interval) > 0:
        grid_system["grid_interval"] = float(grid_interval)
    if order_amount and float(order_amount) > 0:
        grid_system["order_amount"] = float(order_amount)
    if leverage and int(leverage) > 0:
        grid_system["leverage"] = int(leverage)

    grid_system["scanner_recommended_action"] = recommended_action
    grid_system["scanner_rating"] = scanner_row.get("rating")
    grid_system["scanner_score"] = scanner_row.get("score")
    runtime_config["grid_system"] = grid_system
    return runtime_config, warnings


def _write_runtime_grid_config(base_config_path: Path, runtime_config: dict[str, Any]) -> Path:
    GRID_RUNTIME_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    runtime_path = GRID_RUNTIME_CONFIG_DIR / f"{base_config_path.stem}.web.runtime.yaml"
    with open(runtime_path, "w", encoding="utf-8") as file_obj:
        yaml.safe_dump(runtime_config, file_obj, allow_unicode=True, sort_keys=False)
    return runtime_path


async def _build_grid_preflight(config_file: Path, storage: Optional[ScannerHistoryStorage] = None) -> GridPreflightResponse:
    metadata = _read_grid_config_metadata(config_file)
    config_data = await load_grid_runtime_config(str(config_file))
    scanner_row = await _get_latest_scanner_snapshot(storage, metadata["symbol"], metadata["exchange"])
    config_data, scanner_warnings = _apply_scanner_runtime_plan(config_data, scanner_row)
    grid_config = create_grid_config(config_data)

    if metadata["exchange"] != "lighter":
        raise HTTPException(status_code=400, detail="预检目前仅支持 lighter 网格")

    from core.adapters.exchanges.adapters.lighter_rest import LighterRest

    lighter_config_path = PROJECT_ROOT / "config" / "exchanges" / "lighter_config.yaml"
    if not lighter_config_path.exists():
        raise HTTPException(status_code=500, detail="缺少 config/exchanges/lighter_config.yaml")

    with open(lighter_config_path, "r", encoding="utf-8") as file_obj:
        lighter_config = yaml.safe_load(file_obj) or {}

    rest = LighterRest(lighter_config)
    warnings: list[str] = list(scanner_warnings)

    try:
        initialize_result = await rest.initialize()
        initialized = bool(initialize_result or rest.is_connected() or rest.signer_client)
        market_info = await rest._get_market_info(metadata["symbol"])
        ticker = await rest.get_ticker(metadata["symbol"])
        balances = await rest.get_account_balance()

        auth_private_key = bool(
            os.getenv("LIGHTER_API_KEY_PRIVATE_KEY") or os.getenv("LIGHTER_PRIVATE_KEY")
        )
        auth_account_index = str(os.getenv("LIGHTER_ACCOUNT_INDEX", "")).strip()
        auth_api_index = str(
            os.getenv("LIGHTER_API_KEY_INDEX") or os.getenv("LIGHTER_API_INDEX") or "0"
        ).strip()

        checks = {
            "initialized": initialized,
            "signer_ready": bool(rest.signer_client),
            "market_found": bool(market_info),
            "ticker_price": str(getattr(ticker, "last", "") or "") if ticker else "",
            "auth_private_key": auth_private_key,
            "auth_account_index": bool(auth_account_index),
            "auth_api_index": auth_api_index,
        }

        preview_price = None
        if ticker and getattr(ticker, "last", None) is not None:
            preview_price = ticker.last
        elif market_info:
            preview_price = Decimal("0")

        order_preview: dict[str, Any] = {
            "grid_type": metadata["grid_type"],
            "order_amount": str(grid_config.order_amount),
            "grid_interval": str(grid_config.grid_interval),
            "quantity_precision": grid_config.quantity_precision,
            "config_price_decimals": grid_config.price_decimals,
        }
        effective_plan: dict[str, Any] = {
            "follow_grid_count": grid_config.follow_grid_count,
            "startup_active_grid_count": grid_config.startup_active_grid_count,
            "grid_count": grid_config.grid_count,
            "recommended_action": config_data.get("grid_system", {}).get("scanner_recommended_action"),
            "rating": config_data.get("grid_system", {}).get("scanner_rating"),
        }
        startup_margin_check: dict[str, Any] = {}

        if market_info:
            if preview_price and preview_price > 0 and grid_config.is_follow_mode():
                grid_config.update_price_range_for_follow_mode(preview_price)

            preview_params = rest._convert_limit_order_params(
                market_info,
                grid_config.order_amount,
                preview_price if preview_price and preview_price > 0 else Decimal("1"),
                "buy",
                client_order_id=1,
            )
            order_preview.update({
                "market_index": preview_params["market_index"],
                "market_price_decimals": market_info["price_decimals"],
                "price_multiplier": str(market_info["price_multiplier"]),
                "price_int_example": preview_params["price"],
                "base_amount": preview_params["base_amount"],
            })

            notional = Decimal(str(grid_config.order_amount)) * (preview_price if preview_price else Decimal("0"))
            order_preview["estimated_notional_usd"] = str(notional.quantize(Decimal("0.0001")))

            if grid_config.lower_price is not None and grid_config.upper_price is not None:
                total_notional = Decimal("0")
                for grid_index in range(1, grid_config.grid_count + 1):
                    grid_price = grid_config.get_grid_price(grid_index)
                    grid_amount = grid_config.get_formatted_grid_order_amount(grid_index)
                    grid_notional = grid_price * grid_amount
                    total_notional += grid_notional

                leverage = Decimal(str(max(grid_config.leverage, 1)))
                estimated_total_margin = total_notional / leverage
                estimated_total_margin_1x = total_notional
                available_usdc = Decimal("0")
                if balances:
                    available_usdc = max((Decimal(str(balance.free)) for balance in balances), default=Decimal("0"))
                    # 🔥 注意：Lighter REST API 的 Account 模型没有 buying_power/purchase_power 字段
                    # buying_power 只能通过 WebSocket user_stats 频道获取
                    # 这里使用 available_balance 作为可用保证金的来源

                startup_margin_check = _build_preflight_startup_margin_check(
                    grid_config,
                    preview_price,
                    available_usdc,
                )
                effective_plan["startup_margin_check"] = startup_margin_check
                estimated_startup_margin = Decimal(str(startup_margin_check.get("startup_margin_usdc") or "0"))
                estimated_startup_margin_1x = Decimal(str(startup_margin_check.get("startup_margin_1x_usdc") or "0"))

                order_preview.update({
                    "lower_price": str(grid_config.lower_price),
                    "upper_price": str(grid_config.upper_price),
                    "estimated_startup_margin_usdc": str(estimated_startup_margin.quantize(Decimal("0.0001"))),
                    "estimated_total_grid_margin_usdc": str(estimated_total_margin.quantize(Decimal("0.0001"))),
                    "estimated_startup_margin_1x_usdc": str(estimated_startup_margin_1x.quantize(Decimal("0.0001"))),
                    "estimated_total_grid_margin_1x_usdc": str(estimated_total_margin_1x.quantize(Decimal("0.0001"))),
                    "available_balance_usdc": str(available_usdc.quantize(Decimal("0.0001"))) if available_usdc else "0.0000",
                    "buying_power_usdc": str(available_usdc.quantize(Decimal("0.0001"))) if available_usdc else "0.0000",  # 使用 available_balance 替代
                    "startup_margin_source": "rest_available_balance",
                })

                if startup_margin_check.get("status") == "blocked":
                    warnings.append(str(startup_margin_check.get("summary")))
                elif startup_margin_check.get("status") in {"partial", "leverage_dependent"}:
                    warnings.append(str(startup_margin_check.get("summary")))

                if available_usdc and available_usdc < estimated_startup_margin:
                    warnings.append(
                        f"可用保证金不足以覆盖本次启动挂单，available={available_usdc:.4f} USDC, required={estimated_startup_margin:.4f} USDC"
                    )
                elif available_usdc and available_usdc < estimated_total_margin:
                    warnings.append(
                        f"可用保证金不足以覆盖全部网格，available={available_usdc:.4f} USDC, required={estimated_total_margin:.4f} USDC"
                    )

                if available_usdc and available_usdc >= estimated_total_margin and available_usdc < estimated_total_margin_1x:
                    warnings.append(
                        "按配置杠杆估算余额充足，但按 1x 估算不足；若实盘仍报 not enough margin，说明交易所端实际杠杆/保证金模式未按配置生效，需要先在 Lighter 网页端确认。"
                    )

            if preview_params["base_amount"] < 1000:
                warnings.append("base_amount 过小，可能触发交易所最小下单单位限制")

        if not initialized:
            warnings.append("Lighter REST 初始化失败")
        if not checks["signer_ready"]:
            warnings.append("SignerClient 未就绪")
        if not checks["market_found"]:
            warnings.append("未找到市场信息")
        if preview_price in (None, Decimal("0")):
            warnings.append("未获取到有效最新价，预检价格示例使用兜底值")
        if not effective_plan.get("startup_margin_check"):
            effective_plan["startup_margin_check"] = {
                "status": "unknown",
                "source": "rest_available_balance",
                "summary": "预检未生成启动保证金结论",
            }

        return GridPreflightResponse(
            symbol=metadata["symbol"],
            config_path=metadata["config_path"],
            checks=checks,
            order_preview=order_preview,
            effective_plan=effective_plan,
            warnings=warnings,
        )
    finally:
        try:
            await rest.disconnect()
        except Exception:
            pass


def _list_running_grids() -> list[dict[str, Any]]:
    result = _run_command(["pgrep", "-af", "run_grid_trading.py"])
    if result.returncode != 0 or not result.stdout.strip():
        return []

    running: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue

        pid_str, _, command = line.partition(" ")
        if not pid_str.isdigit():
            continue

        config_path = _extract_config_path_from_command(command)
        symbol = None
        if config_path:
            config_full = (PROJECT_ROOT / config_path).resolve()
            if config_full.exists():
                metadata = _read_grid_config_metadata(config_full)
                symbol = metadata.get("symbol")

        running.append({
            "pid": int(pid_str),
            "command": command,
            "config_path": config_path,
            "symbol": symbol,
            "uptime_seconds": _get_pid_uptime(int(pid_str)),
            "log_file": _grid_log_path(symbol).relative_to(PROJECT_ROOT).as_posix() if symbol else None,
        })

    return running


def _list_grid_configs() -> list[dict[str, Any]]:
    configs = []
    for path in sorted(GRID_CONFIG_DIR.glob("*.yaml")):
        configs.append(_read_grid_config_metadata(path.resolve()))
    return configs


def create_control_router() -> APIRouter:
    router = APIRouter()

    @router.get("/scanner/status")
    async def get_scanner_status(request: Request):
        """获取扫描器状态"""
        try:
            result = _run_command(["pgrep", "-f", "run_scanner.py"])

            pids = result.stdout.strip().split('\n') if result.stdout.strip() else []
            running = len(pids) > 0 and pids[0] != ''

            # 获取PID
            pid = int(pids[0]) if running else None

            # 获取运行时间
            uptime = None
            if pid:
                uptime = _get_pid_uptime(pid)

            # 读取最后几行日志
            log_lines = []
            log_file = Path("logs/scanner.log")
            if log_file.exists():
                log_lines = _read_last_lines(log_file)

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
            result = _run_command(["pgrep", "-f", "run_scanner.py"])

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
                [sys.executable, "grid_volatility_scanner/run_scanner.py", "--web", "--exchange", "lighter"],
                stdout=open(log_file, 'a'),
                stderr=subprocess.STDOUT,
                start_new_session=True,
                cwd=Path.cwd()
            )

            # 等待启动
            await asyncio.sleep(3)

            # 检查是否启动成功
            result = _run_command(["pgrep", "-f", "run_scanner.py"])

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
            # 查找进程
            result = _run_command(["pgrep", "-f", "run_scanner.py"])

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
            result = _run_command(["pgrep", "-f", "run_scanner.py"])

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
            result = _run_command(["pm2", "jlist"])

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
            result = _run_command(["pm2", "restart", "crypto_grid"])

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

    @router.get("/grid/status")
    async def get_grid_status(request: Request):
        """获取当前运行中的网格进程状态"""
        running = _list_running_grids()
        return {
            "grids": running,
            "total": len(running),
        }

    @router.get("/grid/configs")
    async def get_grid_configs(request: Request):
        """获取可用于控制面板启动的网格配置列表"""
        configs = _list_grid_configs()
        running_by_config = {
            item.get("config_path"): item
            for item in _list_running_grids()
            if item.get("config_path")
        }

        items = []
        for config in configs:
            running = running_by_config.get(config["config_path"])
            items.append({
                **config,
                "running": bool(running),
                "pid": running.get("pid") if running else None,
                "uptime_seconds": running.get("uptime_seconds") if running else None,
            })

        return {
            "configs": items,
            "total": len(items),
        }

    @router.post("/grid/start")
    async def start_grid(
        payload: GridActionPayload,
        request: Request,
        _auth: None = Depends(require_api_key),
    ):
        """启动指定网格交易进程"""
        config_file = _resolve_grid_config(payload.config_path, payload.symbol)
        metadata = _read_grid_config_metadata(config_file)
        runtime_config_file = config_file

        if payload.dynamic:
            storage = _get_storage(request)
            config_data = await load_grid_runtime_config(str(config_file))
            scanner_row = await _get_latest_scanner_snapshot(storage, metadata["symbol"], metadata["exchange"])
            config_data, _warnings = _apply_scanner_runtime_plan(config_data, scanner_row)
            runtime_config_file = _write_runtime_grid_config(config_file, config_data)

        for running in _list_running_grids():
            if running.get("config_path") in {
                metadata["config_path"],
                runtime_config_file.relative_to(PROJECT_ROOT).as_posix(),
            }:
                return {
                    "status": "already_running",
                    "message": f"{metadata['symbol']} 网格已在运行中",
                    "pid": running.get("pid"),
                    "config_path": metadata["config_path"],
                }

        GRID_LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_path = _grid_log_path(metadata["symbol"])
        runtime_config_path = runtime_config_file.relative_to(PROJECT_ROOT).as_posix()
        command = [sys.executable, "run_grid_trading.py", runtime_config_path]
        if payload.dynamic:
            command.append("--dynamic")
        if payload.debug:
            command.append("--debug")

        process = subprocess.Popen(
            command,
            stdout=open(log_path, "a", encoding="utf-8"),
            stderr=subprocess.STDOUT,
            cwd=PROJECT_ROOT,
            start_new_session=True,
        )
        await asyncio.sleep(3)

        if process.poll() is not None:
            return {
                "status": "error",
                "message": f"{metadata['symbol']} 启动失败，请检查日志",
                "config_path": runtime_config_path,
                "log_file": log_path.relative_to(PROJECT_ROOT).as_posix(),
                "log_lines": _read_last_lines(log_path, 20),
            }

        return {
            "status": "started",
            "message": f"{metadata['symbol']} 网格启动成功",
            "pid": process.pid,
            "symbol": metadata["symbol"],
            "config_path": runtime_config_path,
            "source_config_path": metadata["config_path"],
            "log_file": log_path.relative_to(PROJECT_ROOT).as_posix(),
        }

    @router.post("/grid/preflight", response_model=GridPreflightResponse)
    async def preflight_grid(
        payload: GridActionPayload,
        request: Request,
        _auth: None = Depends(require_api_key),
    ):
        """启动前只读预检，验证认证、市场和下单参数编码。"""
        config_file = _resolve_grid_config(payload.config_path, payload.symbol)
        return await _build_grid_preflight(config_file, _get_storage(request))

    @router.post("/grid/stop")
    async def stop_grid(
        payload: GridActionPayload,
        request: Request,
        _auth: None = Depends(require_api_key),
    ):
        """停止指定网格交易进程"""
        config_path = None
        symbol = payload.symbol.upper() if payload.symbol else None
        if payload.config_path:
            config_path = _resolve_grid_config(payload.config_path, None).relative_to(PROJECT_ROOT).as_posix()

        targets = []
        for running in _list_running_grids():
            if config_path and running.get("config_path") == config_path:
                targets.append(running)
            elif symbol and running.get("symbol") == symbol:
                targets.append(running)

        if not targets:
            return {
                "status": "not_running",
                "message": "目标网格未运行",
            }

        stopped = []
        for target in targets:
            pid = target["pid"]
            try:
                os.kill(pid, signal.SIGTERM)
                stopped.append(pid)
            except ProcessLookupError:
                continue

        await asyncio.sleep(2)
        for pid in stopped:
            try:
                os.kill(pid, 0)
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

        return {
            "status": "stopped",
            "message": f"已停止 {len(stopped)} 个网格进程",
            "stopped_pids": stopped,
        }

    @router.post("/grid/restart")
    async def restart_grid(
        payload: GridActionPayload,
        request: Request,
        _auth: None = Depends(require_api_key),
    ):
        """重启指定网格交易进程"""
        await stop_grid(payload, request, _auth)
        await asyncio.sleep(2)
        result = await start_grid(payload, request, _auth)
        return {
            "status": "restarted",
            **result,
        }

    @router.post("/grid/start-bidirectional")
    async def start_bidirectional_grid(
        payload: GridActionPayload,
        request: Request,
        _auth: None = Depends(require_api_key),
    ):
        """
        🔥 启动双向网格（同时做多和做空）

        根据市场趋势自动调整多空方向权重：
        - 看涨趋势：做多权重高
        - 看跌趋势：做空权重高
        - 震荡行情：双向均衡

        启动两个进程：
        1. 做多网格（follow_long）
        2. 做空网格（follow_short）
        """
        config_file = _resolve_grid_config(payload.config_path, payload.symbol)
        metadata = _read_grid_config_metadata(config_file)

        # 检查是否已有运行中的网格
        running = _list_running_grids()
        for proc in running:
            if metadata["symbol"].lower() in proc.get("config_path", "").lower():
                return {
                    "status": "already_running",
                    "message": f"{metadata['symbol']} 已有网格在运行中",
                    "pid": proc.get("pid"),
                    "config_path": proc.get("config_path"),
                }

        results = {"long": None, "short": None}

        # 🔥 启动做多网格
        long_config_path = _find_or_create_direction_config(
            config_file, metadata["symbol"], "long"
        )
        if long_config_path:
            long_payload = GridActionPayload(
                symbol=metadata["symbol"],
                config_path=str(long_config_path),
                dynamic=payload.dynamic,
                debug=payload.debug,
            )
            results["long"] = await start_grid(long_payload, request, _auth)

        # 🔥 启动做空网格
        short_config_path = _find_or_create_direction_config(
            config_file, metadata["symbol"], "short"
        )
        if short_config_path:
            short_payload = GridActionPayload(
                symbol=metadata["symbol"],
                config_path=str(short_config_path),
                dynamic=payload.dynamic,
                debug=payload.debug,
            )
            results["short"] = await start_grid(short_payload, request, _auth)

        return {
            "status": "started_bidirectional",
            "message": f"{metadata['symbol']} 双向网格已启动",
            "symbol": metadata["symbol"],
            "long": results["long"],
            "short": results["short"],
        }

    def _find_or_create_direction_config(
        base_config_path: Path,
        symbol: str,
        direction: str,  # "long" or "short"
    ) -> Optional[Path]:
        """
        查找或创建方向配置文件

        Args:
            base_config_path: 基础配置文件路径
            symbol: 交易对符号
            direction: 方向（long/short）

        Returns:
            方向配置文件路径
        """
        symbol_lower = symbol.lower()

        # 尝试找到对应方向的配置文件
        pattern = f"lighter-{direction}-perp-{symbol_lower}.yaml"
        direction_config = GRID_CONFIG_DIR / pattern

        if direction_config.exists():
            return direction_config

        # 如果不存在，从基础配置创建
        try:
            with open(base_config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            if not config or 'grid_system' not in config:
                return base_config_path

            # 修改网格类型
            grid_system = config.get('grid_system', {})
            grid_system['grid_type'] = f'follow_{direction}'

            # 调整剥头皮参数（做空方向相反）
            if direction == 'short':
                # 做空的剥头皮从底部往上数
                trigger = grid_system.get('scalping_trigger_percent', 55)
                # 保持相同触发百分比，但方向相反

            config['grid_system'] = grid_system

            # 保存到运行时配置
            GRID_RUNTIME_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            runtime_path = GRID_RUNTIME_CONFIG_DIR / f"{symbol_lower}_{direction}_runtime.yaml"

            with open(runtime_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

            logger.info(f"✅ 创建方向配置: {runtime_path}")
            return runtime_path

        except Exception as e:
            logger.error(f"创建方向配置失败: {e}")
            return base_config_path

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
            elif service.startswith("grid:"):
                symbol = service.split(":", 1)[1].strip().lower()
                log_file = _grid_log_path(symbol)
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
