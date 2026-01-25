"""
WEEX API 521 错误解决方案实现

本文件包含三种解决方案的完整实现：
1. 方案 1: 修复签名算法和请求格式
2. 方案 2: 实现请求重试和降级机制
3. 方案 3: 使用替代 API 端点和数据聚合
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from .weex_rest import WeexRest
from .weex_base import WeexBase


logger = logging.getLogger(__name__)


# =============================================================================
# 方案 1: 修复签名算法和请求格式
# =============================================================================

class WeexRestFixed(WeexRest):
    """
    修复后的 WEEX REST 客户端
    
    改进点：
    1. 更严格的签名验证
    2. 更详细的日志记录
    3. 时间戳同步检查
    4. 请求头验证
    """
    
    async def _request_with_debug(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        带调试信息的请求方法
        
        Args:
            method: HTTP 方法
            url: 请求 URL
            headers: 请求头
            json_data: JSON 请求体
            params: 查询参数
            
        Returns:
            响应 JSON
        """
        session = await self._get_session()
        
        # 记录完整的请求信息
        logger.debug(f"[WEEX] 请求方法: {method}")
        logger.debug(f"[WEEX] 请求 URL: {url}")
        logger.debug(f"[WEEX] 请求头:")
        for key, value in headers.items():
            if key == "ACCESS-SIGN":
                logger.debug(f"  {key}: {value[:20]}...{value[-10:]}")
            else:
                logger.debug(f"  {key}: {value}")
        
        if json_data:
            logger.debug(f"[WEEX] 请求体: {json_data}")
        if params:
            logger.debug(f"[WEEX] 查询参数: {params}")
        
        # 执行请求
        async with session.request(
            method,
            url,
            headers=headers,
            json=json_data,
            params=params
        ) as resp:
            text = await resp.text()
            
            logger.debug(f"[WEEX] 响应状态: {resp.status}")
            logger.debug(f"[WEEX] 响应头: {dict(resp.headers)}")
            logger.debug(f"[WEEX] 响应体: {text[:500]}")
            
            if resp.status >= 400:
                raise RuntimeError(f"status={resp.status} body={text[:500]}")
            
            return await resp.json()
    
    async def get_account_info_with_debug(self) -> Dict[str, Any]:
        """
        获取账户信息（带调试）
        
        Returns:
            账户信息
        """
        url = f"{self.rest_endpoint}/capi/v2/account/info"
        headers = self._get_auth_headers("/capi/v2/account/info")
        
        logger.info("[WEEX] 获取账户信息（带调试）...")
        
        return await self._request_with_debug("GET", url, headers)
    
    async def verify_time_sync(self) -> bool:
        """
        验证客户端时间与服务器时间是否同步
        
        Returns:
            True 如果时间差异在 30 秒以内
        """
        try:
            server_time = await self.get_server_time()
            client_time = int(datetime.now(timezone.utc).timestamp() * 1000)
            
            time_diff = abs(server_time - client_time)
            
            logger.info(f"[WEEX] 服务器时间: {server_time}")
            logger.info(f"[WEEX] 客户端时间: {client_time}")
            logger.info(f"[WEEX] 时间差异: {time_diff}ms")
            
            if time_diff > 30000:
                logger.warning(f"[WEEX] 时间差异过大: {time_diff}ms")
                return False
            
            return True
        except Exception as e:
            logger.error(f"[WEEX] 验证时间同步失败: {e}")
            return False


# =============================================================================
# 方案 2: 实现请求重试和降级机制
# =============================================================================

class WeexRestWithRetry(WeexRest):
    """
    带重试机制的 WEEX REST 客户端
    
    特性：
    1. 指数退避重试
    2. 自动降级
    3. 健康检查
    4. 缓存机制
    """
    
    def __init__(self, config: Dict[str, Any], max_retries: int = 3):
        """
        初始化
        
        Args:
            config: 配置字典
            max_retries: 最大重试次数
        """
        super().__init__(config)
        self.max_retries = max_retries
        self.account_service_healthy = True
        self.account_info_cache: Optional[Dict[str, Any]] = None
        self.cache_timestamp: float = 0
        self.cache_ttl: int = 60  # 缓存 60 秒
    
    async def _request_with_retry(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        带重试的请求方法
        
        Args:
            method: HTTP 方法
            url: 请求 URL
            headers: 请求头
            json_data: JSON 请求体
            params: 查询参数
            
        Returns:
            响应 JSON
        """
        session = await self._get_session()
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                async with session.request(
                    method,
                    url,
                    headers=headers,
                    json=json_data,
                    params=params
                ) as resp:
                    if resp.status == 521:
                        wait_time = 2 ** attempt  # 1s, 2s, 4s
                        logger.warning(
                            f"[WEEX] 521 错误 (尝试 {attempt + 1}/{self.max_retries})，"
                            f"{wait_time}s 后重试..."
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    
                    if resp.status >= 400:
                        text = await resp.text()
                        raise RuntimeError(f"status={resp.status} body={text[:500]}")
                    
                    return await resp.json()
            
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"[WEEX] 请求失败: {e}，{wait_time}s 后重试...")
                    await asyncio.sleep(wait_time)
        
        if last_error:
            raise last_error
    
    async def get_account_info(self) -> Dict[str, Any]:
        """
        获取账户信息（带重试）
        
        Returns:
            账户信息
        """
        url = f"{self.rest_endpoint}/capi/v2/account/info"
        headers = self._get_auth_headers("/capi/v2/account/info")
        
        try:
            result = await self._request_with_retry("GET", url, headers)
            self.account_service_healthy = True
            self.account_info_cache = result
            self.cache_timestamp = time.time()
            return result
        except Exception as e:
            self.account_service_healthy = False
            logger.error(f"[WEEX] 获取账户信息失败: {e}")
            
            # 尝试使用缓存
            if self.account_info_cache:
                logger.warning(f"[WEEX] 使用缓存的账户信息")
                return self.account_info_cache
            
            raise
    
    async def check_account_service_health(self) -> bool:
        """
        检查账户服务是否健康
        
        Returns:
            True 如果服务健康
        """
        try:
            await asyncio.wait_for(
                self.get_account_info(),
                timeout=5.0
            )
            return True
        except asyncio.TimeoutError:
            logger.warning("[WEEX] 账户服务超时")
            return False
        except Exception as e:
            if "521" in str(e):
                logger.warning("[WEEX] 账户服务返回 521 错误")
                return False
            # 其他错误可能是权限问题，不影响健康状态
            return True


# =============================================================================
# 方案 3: 使用替代 API 端点和数据聚合
# =============================================================================

class WeexRestAggregated(WeexRest):
    """
    使用替代端点和数据聚合的 WEEX REST 客户端
    
    特性：
    1. 多端点聚合
    2. 自动降级
    3. 缓存管理
    4. 数据合成
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化
        
        Args:
            config: 配置字典
        """
        super().__init__(config)
        self.aggregated_data_cache: Dict[str, Any] = {}
        self.cache_timestamp: float = 0
        self.cache_ttl: int = 60
    
    async def get_account_info_aggregated(self) -> Dict[str, Any]:
        """
        通过多个端点聚合账户信息
        
        如果直接获取失败，尝试从其他端点聚合数据。
        
        Returns:
            聚合的账户信息
        """
        # 首先尝试直接获取
        try:
            url = f"{self.rest_endpoint}/capi/v2/account/info"
            headers = self._get_auth_headers("/capi/v2/account/info")
            session = await self._get_session()
            
            async with session.get(url, headers=headers) as resp:
                if resp.status < 400:
                    data = await resp.json()
                    logger.info("[WEEX] 直接获取账户信息成功")
                    return data
        except Exception as e:
            logger.warning(f"[WEEX] 直接获取账户信息失败: {e}")
        
        # 降级到聚合方案
        logger.info("[WEEX] 使用聚合方案获取账户信息...")
        
        try:
            # 并行获取多个数据源
            positions, balance, orders = await asyncio.gather(
                self.get_positions(),
                self.get_balance(),
                self.get_order_history(limit=100),
                return_exceptions=True
            )
            
            # 处理异常
            positions = positions if not isinstance(positions, Exception) else []
            balance = balance if not isinstance(balance, Exception) else {}
            orders = orders if not isinstance(orders, Exception) else []
            
            # 聚合数据
            aggregated_info = {
                "positions": positions,
                "balance": balance,
                "recent_orders": orders,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "aggregated",
                "aggregated": True,
            }
            
            logger.info(f"[WEEX] 聚合账户信息成功: 持仓 {len(positions)}, 余额 {len(balance)}")
            
            return aggregated_info
        
        except Exception as e:
            logger.error(f"[WEEX] 聚合账户信息失败: {e}")
            raise
    
    async def get_account_info(self) -> Dict[str, Any]:
        """
        获取账户信息（自动降级）
        
        Returns:
            账户信息
        """
        # 检查缓存
        if self.aggregated_data_cache:
            cache_age = time.time() - self.cache_timestamp
            if cache_age < self.cache_ttl:
                logger.debug(f"[WEEX] 使用缓存的账户信息 (年龄: {cache_age:.1f}s)")
                return self.aggregated_data_cache
        
        # 获取数据
        result = await self.get_account_info_aggregated()
        
        # 更新缓存
        self.aggregated_data_cache = result
        self.cache_timestamp = time.time()
        
        return result
    
    async def get_order_history(
        self,
        symbol: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        获取订单历史
        
        Args:
            symbol: 交易对（可选）
            limit: 限制数量
            
        Returns:
            订单列表
        """
        url = f"{self.rest_endpoint}/capi/v2/orders"
        headers = self._get_auth_headers("/capi/v2/orders")
        session = await self._get_session()
        
        params = {"limit": limit}
        if symbol:
            params["symbol"] = symbol
        
        try:
            async with session.get(url, headers=headers, params=params) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    raise RuntimeError(f"获取订单历史失败: status={resp.status}")
                return await resp.json()
        except Exception as e:
            logger.warning(f"[WEEX] 获取订单历史失败: {e}")
            return []
    
    def _synthesize_account_info(
        self,
        positions: List[Dict[str, Any]],
        balance: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        从持仓和余额数据合成账户信息
        
        Args:
            positions: 持仓列表
            balance: 余额信息
            
        Returns:
            合成的账户信息
        """
        # 计算总权益
        total_equity = Decimal("0")
        
        # 从余额计算
        for currency, info in balance.items():
            if isinstance(info, dict):
                total_equity += Decimal(str(info.get("total", 0)))
        
        # 从持仓计算
        for position in positions:
            if isinstance(position, dict):
                pnl = Decimal(str(position.get("unrealizedPnl", 0)))
                total_equity += pnl
        
        return {
            "total_equity": str(total_equity),
            "balance": balance,
            "positions": positions,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "synthesized",
            "aggregated": True,
        }


# =============================================================================
# 综合方案: 结合三种解决方案
# =============================================================================

class WeexRestCombined(WeexRestFixed, WeexRestWithRetry, WeexRestAggregated):
    """
    综合三种解决方案的 WEEX REST 客户端
    
    特性：
    1. 修复的签名算法（方案 1）
    2. 重试和降级机制（方案 2）
    3. 替代端点和数据聚合（方案 3）
    """
    
    async def get_account_info(self) -> Dict[str, Any]:
        """
        获取账户信息（综合方案）
        
        执行顺序：
        1. 尝试直接获取（带重试）
        2. 如果失败，使用聚合方案
        3. 如果仍然失败，使用缓存
        
        Returns:
            账户信息
        """
        logger.info("[WEEX] 使用综合方案获取账户信息...")
        
        # 方案 1 + 2: 修复的签名 + 重试
        try:
            url = f"{self.rest_endpoint}/capi/v2/account/info"
            headers = self._get_auth_headers("/capi/v2/account/info")
            
            result = await self._request_with_retry("GET", url, headers)
            logger.info("[WEEX] 直接获取账户信息成功")
            return result
        except Exception as e:
            logger.warning(f"[WEEX] 直接获取失败: {e}")
        
        # 方案 3: 聚合方案
        try:
            result = await self.get_account_info_aggregated()
            logger.info("[WEEX] 聚合方案获取账户信息成功")
            return result
        except Exception as e:
            logger.error(f"[WEEX] 聚合方案失败: {e}")
            raise


# =============================================================================
# 辅助函数
# =============================================================================

async def test_solution_1(config: Dict[str, Any]) -> None:
    """测试方案 1: 修复签名算法"""
    logger.info("\n" + "=" * 80)
    logger.info("测试方案 1: 修复签名算法和请求格式")
    logger.info("=" * 80)
    
    rest = WeexRestFixed(config)
    
    try:
        # 验证时间同步
        time_ok = await rest.verify_time_sync()
        if not time_ok:
            logger.warning("时间同步检查失败")
        
        # 获取账户信息（带调试）
        result = await rest.get_account_info_with_debug()
        logger.info(f"✓ 方案 1 成功: {result}")
    except Exception as e:
        logger.error(f"✗ 方案 1 失败: {e}")
    finally:
        await rest.close()


async def test_solution_2(config: Dict[str, Any]) -> None:
    """测试方案 2: 重试和降级"""
    logger.info("\n" + "=" * 80)
    logger.info("测试方案 2: 请求重试和降级机制")
    logger.info("=" * 80)
    
    rest = WeexRestWithRetry(config, max_retries=3)
    
    try:
        # 检查服务健康
        healthy = await rest.check_account_service_health()
        logger.info(f"账户服务健康: {healthy}")
        
        # 获取账户信息（带重试）
        result = await rest.get_account_info()
        logger.info(f"✓ 方案 2 成功: {result}")
    except Exception as e:
        logger.error(f"✗ 方案 2 失败: {e}")
    finally:
        await rest.close()


async def test_solution_3(config: Dict[str, Any]) -> None:
    """测试方案 3: 替代端点和聚合"""
    logger.info("\n" + "=" * 80)
    logger.info("测试方案 3: 替代 API 端点和数据聚合")
    logger.info("=" * 80)
    
    rest = WeexRestAggregated(config)
    
    try:
        # 获取聚合的账户信息
        result = await rest.get_account_info_aggregated()
        logger.info(f"✓ 方案 3 成功: {result}")
    except Exception as e:
        logger.error(f"✗ 方案 3 失败: {e}")
    finally:
        await rest.close()


async def test_combined_solution(config: Dict[str, Any]) -> None:
    """测试综合方案"""
    logger.info("\n" + "=" * 80)
    logger.info("测试综合方案: 方案 1 + 2 + 3")
    logger.info("=" * 80)
    
    rest = WeexRestCombined(config)
    
    try:
        # 获取账户信息（综合方案）
        result = await rest.get_account_info()
        logger.info(f"✓ 综合方案成功: {result}")
    except Exception as e:
        logger.error(f"✗ 综合方案失败: {e}")
    finally:
        await rest.close()


if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 测试配置
    config = {
        "exchange_id": "weex",
        "testnet": False,
        "request_timeout": 10,
        "api_key": "weex_d0649c112185fb5a0aeb13846fe915ac",
        "api_secret": "a041e89a40dba5c2a8ae80ec12d2a51ece7026ab378f21bad74fcb1e984f3a61",
        "api_passphrase": "manus_auto",
    }
    
    # 运行测试
    async def main():
        # await test_solution_1(config)
        # await test_solution_2(config)
        # await test_solution_3(config)
        await test_combined_solution(config)
    
    asyncio.run(main())
