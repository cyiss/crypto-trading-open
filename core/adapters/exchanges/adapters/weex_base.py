"""
WEEX 交易所适配器 - 基础工具模块

WEEX 是一个中心化的永续合约交易所。

本模块包含：
- 环境与端点选择（生产/测试网）
- 时间格式转换
- 交易对/合约名称规范化
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class WeexEnv(Enum):
    """WEEX 环境枚举"""
    TESTNET = "testnet"
    PROD = "prod"


@dataclass(frozen=True)
class WeexEndpointConfig:
    """WEEX 端点配置"""
    rest_endpoint: str
    ws_endpoint: str


@dataclass(frozen=True)
class WeexEnvConfig:
    """WEEX 环境配置"""
    rest: WeexEndpointConfig
    ws: WeexEndpointConfig


def get_env_config(environment: WeexEnv) -> WeexEnvConfig:
    """
    获取 WEEX 环境配置
    
    Args:
        environment: 环境类型
        
    Returns:
        环境配置对象
    """
    if environment == WeexEnv.PROD:
        return WeexEnvConfig(
            rest=WeexEndpointConfig(
                rest_endpoint="https://api-contract.weex.com",
                ws_endpoint="wss://ws-contract.weex.com"
            ),
            ws=WeexEndpointConfig(
                rest_endpoint="https://api-contract.weex.com",
                ws_endpoint="wss://ws-contract.weex.com"
            )
        )
    elif environment == WeexEnv.TESTNET:
        return WeexEnvConfig(
            rest=WeexEndpointConfig(
                rest_endpoint="https://testnet-api-contract.weex.com",
                ws_endpoint="wss://testnet-ws-contract.weex.com"
            ),
            ws=WeexEndpointConfig(
                rest_endpoint="https://testnet-api-contract.weex.com",
                ws_endpoint="wss://testnet-ws-contract.weex.com"
            )
        )
    else:
        raise ValueError(f"Unknown environment={environment}")


def datetime_to_unix_ms(dt: datetime) -> int:
    """将 datetime 转换为 Unix 毫秒时间戳"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def unix_ms_to_datetime(ms: Optional[int]) -> datetime:
    """将 Unix 毫秒时间戳转换为 datetime"""
    if not ms:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


class WeexBase:
    """
    WEEX REST / WS 模块共享基类
    """

    def __init__(self, config: Dict[str, Any]):
        """
        初始化 WEEX 基础配置
        
        Args:
            config: 配置字典
        """
        self.config_dict = config

        # 环境选择：优先 extra_params.env，否则根据 testnet 推导
        extra = config.get("extra_params", {}) if isinstance(config.get("extra_params", {}), dict) else {}
        env_str = str(extra.get("env") or "").lower().strip()
        if not env_str:
            env = WeexEnv.TESTNET if bool(config.get("testnet")) else WeexEnv.PROD
        else:
            env = WeexEnv(env_str)

        self.env: WeexEnv = env
        self.env_config: WeexEnvConfig = get_env_config(env)

        # 允许通过 extra_params 显式覆盖端点（默认使用官方端点）
        self.rest_endpoint = str(extra.get("rest_endpoint") or self.env_config.rest.rest_endpoint).rstrip("/")
        self.ws_endpoint = str(extra.get("ws_endpoint") or self.env_config.ws.ws_endpoint).rstrip("/")

        # 鉴权信息
        self.api_key: str = str(getattr(config, "api_key", "") or config.get("api_key") or "")
        self.api_secret: str = str(getattr(config, "api_secret", "") or config.get("api_secret") or "")
        self.api_passphrase: Optional[str] = (
            getattr(config, "api_passphrase", None) or config.get("api_passphrase")
        )

    def normalize_symbol(self, symbol: str) -> str:
        """
        规范化交易对符号为 WEEX 格式
        
        WEEX 永续合约的典型命名示例：cmt_btcusdt
        
        Args:
            symbol: 输入符号
            
        Returns:
            规范化后的符号
        """
        if not symbol:
            return symbol
        
        s = symbol.strip()
        # 替换分隔符
        s = s.replace("/", "_").replace("-", "_")
        s = s.lower()
        
        # 如果不包含 cmt_ 前缀，添加
        if not s.startswith("cmt_"):
            # 移除可能的 _perp 后缀
            if s.endswith("_perp"):
                s = s[:-5]
            s = f"cmt_{s}"
        
        return s
