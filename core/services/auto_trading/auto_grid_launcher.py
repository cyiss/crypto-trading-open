"""
自动网格启动器 - Auto Grid Launcher

全自动流程：
1. 定期运行扫描器（虚拟网格模拟）
2. 筛选S/A级高波动代币
3. 自动生成网格配置
4. 启动网格交易实例
5. 持续监控评级变化，自动暂停/恢复
"""

import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class AutoGridLauncher:
    """
    自动网格启动器

    从扫描器发现的高评级代币中，自动启动网格交易。

    工作流程:
    1. 每隔scan_interval秒运行一次扫描器
    2. 获取扫描结果，筛选APR >= threshold的代币
    3. 为每个代币生成网格配置
    4. 通过grid_manager启动网格实例
    5. 持续监控，当评级降到C/D时暂停网格

    使用方式:
        launcher = AutoGridLauncher(
            scanner=scanner_instance,
            grid_manager=grid_manager_instance,
            min_rating='A',  # 只启动A级及以上
            scan_interval=3600,  # 每小时扫描一次
        )
        await launcher.start()
    """

    def __init__(
        self,
        scanner=None,
        grid_manager=None,
        min_rating: str = "A",
        scan_interval: int = 3600,
        auto_launch: bool = True,
        max_active_grids: int = 10,
        base_config: Optional[dict] = None,
    ):
        """
        Args:
            scanner: 扫描器实例（GridVolatilityScanner）
            grid_manager: 网格管理器实例（管理多个网格进程）
            min_rating: 最低启动评级（S/A/B/C/D）
            scan_interval: 扫描间隔（秒）
            auto_launch: 是否自动启动网格（False则只输出推荐）
            max_active_grids: 最大同时运行网格数
            base_config: 基础配置模板（覆盖default.yaml中的默认值）
        """
        self.scanner = scanner
        self.grid_manager = grid_manager
        self.min_rating = min_rating
        self.scan_interval = scan_interval
        self.auto_launch = auto_launch
        self.max_active_grids = max_active_grids

        # 评级优先级
        self._rating_priority = {"S": 5, "A": 4, "B": 3, "C": 2, "D": 1}

        # 状态追踪
        self._running = False
        self._active_symbols: Dict[str, dict] = {}  # {symbol: config}
        self._paused_symbols: Set[str] = set()
        self._scan_count: int = 0
        self._launch_count: int = 0
        self._last_scan_results: List[dict] = []
        self._last_scan_time: Optional[datetime] = None

        # 基础配置模板
        self._base_config = base_config or {
            'grid_type': 'follow_long',
            'follow_grid_count': 100,
            'follow_distance': 2,
            'leverage': 20,
            'scalping_enabled': True,
            'smart_scalping_enabled': True,
            'capital_protection_enabled': True,
            'capital_protection_trigger_percent': 25,
            'exit_cleanup_enabled': True,
        }

    async def start(self):
        """启动自动扫描循环"""
        self._running = True
        logger.info(
            f"🚀 自动网格启动器已启动: "
            f"评级>={self.min_rating}, "
            f"扫描间隔={self.scan_interval}s, "
            f"自动启动={'是' if self.auto_launch else '否'}"
        )

        while self._running:
            try:
                await self._scan_and_launch()
            except Exception as e:
                logger.error(f"自动扫描循环错误: {e}")

            # 等待下一次扫描
            await asyncio.sleep(self.scan_interval)

    def stop(self):
        """停止自动扫描"""
        self._running = False
        logger.info("🛑 自动网格启动器已停止")

    async def _scan_and_launch(self):
        """执行一次扫描和启动流程"""
        self._scan_count += 1
        self._last_scan_time = datetime.now()

        logger.info(f"📊 第{self._scan_count}次自动扫描开始...")

        # 1. 运行扫描器（如果提供的话）
        if self.scanner:
            scan_results = await self._run_scanner()
        else:
            scan_results = self._last_scan_results

        if not scan_results:
            logger.warning("扫描结果为空，跳过本次")
            return

        # 2. 筛选S/A级代币
        qualified = self._filter_qualified(scan_results)
        logger.info(f"   扫描{len(scan_results)}个代币，筛选出{len(qualified)}个合格代币")

        # 3. 为每个合格代币检查/启动网格
        for result in qualified:
            symbol = result.get('symbol', '')
            rating = self._extract_rating(result.get('rating', ''))

            if symbol in self._active_symbols:
                # 已在运行，检查是否需要调整
                self._check_existing_grid(symbol, rating, result)
            elif symbol not in self._paused_symbols:
                # 新代币，尝试启动
                if len(self._active_symbols) < self.max_active_grids:
                    await self._launch_grid(symbol, result)
                else:
                    logger.debug(f"   {symbol}: 已达最大网格数，跳过")

        # 4. 检查运行中的网格，暂停评级下降的
        await self._check_and_pause_grids(scan_results)

        logger.info(
            f"   扫描完成: {len(self._active_symbols)}个网格运行中, "
            f"{len(self._paused_symbols)}个暂停"
        )

    async def _run_scanner(self) -> List[dict]:
        """运行扫描器获取结果"""
        try:
            if hasattr(self.scanner, 'scan'):
                # 运行一次短扫描（5分钟）
                await self.scanner.scan(duration_seconds=300)
                results = self.scanner.get_results()
                return [r.to_dict() for r in results if hasattr(r, 'to_dict')]
        except Exception as e:
            logger.error(f"运行扫描器失败: {e}")
        return []

    def _filter_qualified(self, results: List[dict]) -> List[dict]:
        """筛选合格的代币"""
        min_priority = self._rating_priority.get(self.min_rating, 3)

        qualified = []
        for r in results:
            rating = self._extract_rating(r.get('rating', ''))
            priority = self._rating_priority.get(rating, 0)
            apr = float(r.get('estimated_apr', 0))

            if priority >= min_priority and apr > 50:  # 至少50% APR
                qualified.append(r)

        # 按APR排序
        qualified.sort(key=lambda x: float(x.get('estimated_apr', 0)), reverse=True)
        return qualified

    def _extract_rating(self, rating_str: str) -> str:
        """从评级字符串中提取评级字母"""
        if not rating_str:
            return "D"
        # 去掉emoji，提取S/A/B/C/D
        for letter in ["S", "A", "B", "C", "D"]:
            if letter in rating_str.upper():
                return letter
        return "D"

    async def _launch_grid(self, symbol: str, scan_result: dict):
        """为代币启动网格"""
        if not self.auto_launch:
            logger.info(f"   [DRY RUN] 将为{symbol}启动网格 (APR={scan_result.get('estimated_apr', 0):.0f}%)")
            return

        try:
            # 生成配置
            config = self._generate_config(symbol, scan_result)

            # 通过grid_manager启动
            if self.grid_manager and hasattr(self.grid_manager, 'launch_grid'):
                instance_id = await self.grid_manager.launch_grid(config)
                self._active_symbols[symbol] = {
                    'instance_id': instance_id,
                    'config': config,
                    'launch_time': datetime.now(),
                    'last_rating': self._extract_rating(scan_result.get('rating', '')),
                    'last_apr': float(scan_result.get('estimated_apr', 0)),
                }
                self._launch_count += 1
                logger.info(
                    f"✅ 为{symbol}启动网格: "
                    f"instance={instance_id}, "
                    f"APR={scan_result.get('estimated_apr', 0):.0f}%"
                )
            else:
                # 没有grid_manager，只记录
                self._active_symbols[symbol] = {
                    'config': config,
                    'launch_time': datetime.now(),
                    'last_rating': self._extract_rating(scan_result.get('rating', '')),
                    'last_apr': float(scan_result.get('estimated_apr', 0)),
                }
                logger.info(f"   [NO MANAGER] {symbol}配置已生成，等待grid_manager接管")

        except Exception as e:
            logger.error(f"   启动{symbol}网格失败: {e}")

    def _generate_config(self, symbol: str, scan_result: dict) -> dict:
        """根据扫描结果生成网格配置"""
        import copy
        config = copy.deepcopy(self._base_config)
        config.update({
            'symbol': symbol,
            'grid_interval': self._calc_grid_interval(scan_result),
            'order_amount': self._calc_order_amount(scan_result),
        })
        return config

    def _calc_grid_interval(self, scan_result: dict) -> float:
        """根据APR和波动率计算网格间距"""
        apr = float(scan_result.get('estimated_apr', 100))
        price = float(scan_result.get('current_price', 10000))

        # 高APR → 适当增大间距
        if apr > 500:
            ratio = 0.002  # 0.2%
        elif apr > 300:
            ratio = 0.0015
        else:
            ratio = 0.001

        return round(price * ratio, 2)

    def _calc_order_amount(self, scan_result: dict) -> float:
        """根据价格计算下单量（保持每格$10-20的价值）"""
        price = float(scan_result.get('current_price', 10000))
        target_value = 15.0  # 每格$15
        return round(target_value / price, 6)

    def _check_existing_grid(self, symbol: str, rating: str, scan_result: dict):
        """检查已运行的网格是否需要调整"""
        if symbol in self._active_symbols:
            info = self._active_symbols[symbol]
            new_apr = float(scan_result.get('estimated_apr', 0))
            old_apr = info.get('last_apr', 0)

            # 更新记录
            info['last_rating'] = rating
            info['last_apr'] = new_apr

            # APR大幅下降时记录警告
            if old_apr > 0 and new_apr < old_apr * 0.5:
                logger.warning(
                    f"⚠️ {symbol} APR大幅下降: {old_apr:.0f}% → {new_apr:.0f}%"
                )

    async def _check_and_pause_grids(self, scan_results: List[dict]):
        """检查运行中的网格，暂停评级过低的"""
        # 构建当前评级映射
        current_ratings = {}
        for r in scan_results:
            symbol = r.get('symbol', '')
            rating = self._extract_rating(r.get('rating', ''))
            current_ratings[symbol] = rating

        # 检查每个运行中的网格
        to_pause = []
        for symbol, info in self._active_symbols.items():
            current_rating = current_ratings.get(symbol, 'D')
            priority = self._rating_priority.get(current_rating, 0)

            if priority < 2:  # C/D级
                to_pause.append(symbol)
                logger.info(f"   {symbol} 降至{current_rating}级，准备暂停")

        for symbol in to_pause:
            await self._pause_grid(symbol)

    async def _pause_grid(self, symbol: str):
        """暂停网格"""
        if symbol in self._active_symbols:
            info = self._active_symbols.pop(symbol)
            self._paused_symbols.add(symbol)

            if self.grid_manager and hasattr(self.grid_manager, 'pause_grid'):
                instance_id = info.get('instance_id')
                if instance_id:
                    await self.grid_manager.pause_grid(instance_id)

            logger.info(f"⏸️ {symbol} 网格已暂停")

    async def resume_grid(self, symbol: str):
        """手动恢复暂停的网格"""
        if symbol in self._paused_symbols:
            self._paused_symbols.discard(symbol)
            logger.info(f"▶️ {symbol} 已从暂停列表移除，下次扫描时可能重新启动")

    def get_status(self) -> dict:
        """获取自动启动器状态"""
        return {
            'running': self._running,
            'scan_count': self._scan_count,
            'launch_count': self._launch_count,
            'active_grids': len(self._active_symbols),
            'paused_grids': len(self._paused_symbols),
            'active_symbols': list(self._active_symbols.keys()),
            'paused_symbols': list(self._paused_symbols),
            'last_scan_time': self._last_scan_time.isoformat() if self._last_scan_time else None,
            'min_rating': self.min_rating,
            'max_active_grids': self.max_active_grids,
        }
