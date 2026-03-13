"""
绩效记录器 - Performance Tracker

记录网格交易的参数和结果，为ML模型提供训练数据。
使用SQLite存储，与Web Dashboard共享数据库。
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict

import aiosqlite

logger = logging.getLogger(__name__)


@dataclass
class PerformanceRecord:
    """绩效记录"""
    instance_id: str
    symbol: str
    exchange: str
    grid_type: str
    grid_interval: float
    order_amount: float
    follow_distance: int
    scalping_trigger_percent: int
    leverage: int
    volatility: float
    trend_strength: float
    period_start: str
    period_end: str
    annualized_return: float
    max_drawdown: float
    trade_count: int
    total_pnl: float
    sharpe_ratio: float
    is_ai_recommended: bool = False


class PerformanceTracker:
    """
    绩效记录器

    职责：
    1. 记录网格运行参数和结果
    2. 累积训练数据
    3. 查询历史绩效供模型训练使用
    4. 评估参数调整效果

    数据库：使用Web Dashboard共享的SQLite数据库
    """

    def __init__(self, db_path: str = "data/grid_scanner.db"):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None
        self._initialized = False

        # 运行中的实例跟踪
        self._active_instances: Dict[str, Dict] = {}

    async def initialize(self):
        """初始化数据库连接"""
        import os
        os.makedirs(os.path.dirname(self.db_path) or '.', exist_ok=True)

        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL;")
        await self._db.execute("PRAGMA synchronous=NORMAL;")

        # 创建绩效表（如果不存在）
        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS grid_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                grid_type TEXT DEFAULT 'follow_long',
                grid_interval REAL DEFAULT 0,
                order_amount REAL DEFAULT 0,
                follow_distance INTEGER DEFAULT 1,
                scalping_trigger_percent INTEGER DEFAULT 80,
                leverage INTEGER DEFAULT 10,
                volatility REAL DEFAULT 0,
                trend_strength REAL DEFAULT 0,
                period_start TIMESTAMP,
                period_end TIMESTAMP,
                annualized_return REAL DEFAULT 0,
                max_drawdown REAL DEFAULT 0,
                trade_count INTEGER DEFAULT 0,
                total_pnl REAL DEFAULT 0,
                sharpe_ratio REAL DEFAULT 0,
                is_ai_recommended INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_perf_instance ON grid_performance(instance_id);
            CREATE INDEX IF NOT EXISTS idx_perf_symbol ON grid_performance(symbol);
            CREATE INDEX IF NOT EXISTS idx_perf_period ON grid_performance(period_start, period_end);
        """)

        await self._db.commit()
        self._initialized = True
        logger.info(f"✅ 绩效记录器初始化完成: {self.db_path}")

    async def close(self):
        """关闭数据库连接"""
        if self._db:
            await self._db.close()
            self._db = None

    def start_tracking(
        self,
        instance_id: str,
        symbol: str,
        exchange: str,
        config: dict,
        volatility: float = 0.0,
        trend_strength: float = 0.0,
        is_ai_recommended: bool = False,
    ):
        """
        开始跟踪一个网格实例

        Args:
            instance_id: 实例唯一ID
            symbol: 交易对
            exchange: 交易所
            config: 网格配置字典
            volatility: 当前波动率
            trend_strength: 当前趋势强度
            is_ai_recommended: 是否使用了AI推荐参数
        """
        self._active_instances[instance_id] = {
            'symbol': symbol,
            'exchange': exchange,
            'config': config,
            'volatility': volatility,
            'trend_strength': trend_strength,
            'is_ai_recommended': is_ai_recommended,
            'start_time': datetime.now(),
            'start_pnl': 0.0,
            'max_pnl': 0.0,
            'min_pnl': 0.0,
            'trade_count': 0,
        }
        logger.debug(f"开始跟踪实例 {instance_id}: {symbol}")

    def update_trade(
        self,
        instance_id: str,
        pnl_delta: float = 0.0,
    ):
        """更新交易记录"""
        if instance_id in self._active_instances:
            inst = self._active_instances[instance_id]
            inst['trade_count'] += 1
            # 更新累计盈亏
            inst['max_pnl'] = max(inst['max_pnl'], inst.get('running_pnl', 0) + pnl_delta)
            inst['min_pnl'] = min(inst['min_pnl'], inst.get('running_pnl', 0) + pnl_delta)
            inst['running_pnl'] = inst.get('running_pnl', 0) + pnl_delta

    async def save_period_record(
        self,
        instance_id: str,
        annualized_return: float,
        max_drawdown: float,
        total_pnl: float,
        sharpe_ratio: float = 0.0,
    ):
        """
        保存一个周期的绩效记录

        Args:
            instance_id: 实例ID
            annualized_return: 年化收益率（%）
            max_drawdown: 最大回撤（%）
            total_pnl: 总盈亏
            sharpe_ratio: 夏普比率
        """
        if not self._initialized or instance_id not in self._active_instances:
            return

        inst = self._active_instances[instance_id]
        config = inst['config']
        now = datetime.now()

        record = PerformanceRecord(
            instance_id=instance_id,
            symbol=inst['symbol'],
            exchange=inst['exchange'],
            grid_type=config.get('grid_type', 'follow_long'),
            grid_interval=float(config.get('grid_interval', 0)),
            order_amount=float(config.get('order_amount', 0)),
            follow_distance=int(config.get('follow_distance', 1)),
            scalping_trigger_percent=int(config.get('scalping_trigger_percent', 80)),
            leverage=int(config.get('leverage', 10)),
            volatility=inst['volatility'],
            trend_strength=inst['trend_strength'],
            period_start=inst['start_time'].isoformat(),
            period_end=now.isoformat(),
            annualized_return=annualized_return,
            max_drawdown=max_drawdown,
            trade_count=inst['trade_count'],
            total_pnl=total_pnl,
            sharpe_ratio=sharpe_ratio,
            is_ai_recommended=inst['is_ai_recommended'],
        )

        await self._save_record(record)

        # 重置起始时间（为下一个周期准备）
        inst['start_time'] = now
        inst['trade_count'] = 0
        inst['start_pnl'] = total_pnl
        inst['max_pnl'] = 0.0
        inst['min_pnl'] = 0.0

    async def _save_record(self, record: PerformanceRecord):
        """保存记录到数据库"""
        try:
            await self._db.execute("""
                INSERT INTO grid_performance
                (instance_id, symbol, exchange, grid_type, grid_interval,
                 order_amount, follow_distance, scalping_trigger_percent,
                 leverage, volatility, trend_strength, period_start,
                 period_end, annualized_return, max_drawdown, trade_count,
                 total_pnl, sharpe_ratio, is_ai_recommended)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.instance_id, record.symbol, record.exchange,
                record.grid_type, record.grid_interval, record.order_amount,
                record.follow_distance, record.scalping_trigger_percent,
                record.leverage, record.volatility, record.trend_strength,
                record.period_start, record.period_end,
                record.annualized_return, record.max_drawdown,
                record.trade_count, record.total_pnl, record.sharpe_ratio,
                1 if record.is_ai_recommended else 0,
            ))
            await self._db.commit()
            logger.debug(f"绩效记录已保存: {record.instance_id} ({record.symbol})")
        except Exception as e:
            logger.error(f"保存绩效记录失败: {e}")

    async def get_training_data(
        self,
        symbol: Optional[str] = None,
        min_samples: int = 10,
        days: int = 90,
    ) -> Optional[List[Dict]]:
        """
        获取ML训练数据

        Args:
            symbol: 可选，过滤特定代币
            min_samples: 最少样本数
            days: 最近N天的数据

        Returns:
            训练数据列表，每个元素包含特征和目标值
        """
        if not self._initialized:
            return None

        since = (datetime.now() - timedelta(days=days)).isoformat()

        query = """
            SELECT grid_interval, order_amount, follow_distance,
                   scalping_trigger_percent, leverage, volatility,
                   trend_strength, annualized_return, max_drawdown,
                   trade_count, total_pnl, sharpe_ratio
            FROM grid_performance
            WHERE period_start >= ?
        """
        params: list = [since]
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)

        # 过滤有效数据：年化收益非零且交易次数>0
        query += " AND trade_count > 0 AND annualized_return != 0"
        query += " ORDER BY period_start DESC"

        async with self._db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            data = [dict(r) for r in rows]

        if len(data) < min_samples:
            logger.info(f"训练数据不足: {len(data)} < {min_samples}")
            return None

        return data

    async def get_performance_summary(
        self,
        instance_id: Optional[str] = None,
        symbol: Optional[str] = None,
        days: int = 30,
    ) -> Dict:
        """获取绩效汇总"""
        if not self._initialized:
            return {}

        since = (datetime.now() - timedelta(days=days)).isoformat()

        query = "SELECT * FROM grid_performance WHERE period_start >= ?"
        params: list = [since]
        if instance_id:
            query += " AND instance_id = ?"
            params.append(instance_id)
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)

        async with self._db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            data = [dict(r) for r in rows]

        if not data:
            return {'total_records': 0}

        total_pnl = sum(r['total_pnl'] for r in data)
        avg_return = sum(r['annualized_return'] for r in data) / len(data)
        avg_drawdown = sum(r['max_drawdown'] for r in data) / len(data)
        total_trades = sum(r['trade_count'] for r in data)

        ai_records = [r for r in data if r['is_ai_recommended']]
        non_ai_records = [r for r in data if not r['is_ai_recommended']]

        return {
            'total_records': len(data),
            'total_pnl': total_pnl,
            'avg_annualized_return': avg_return,
            'avg_max_drawdown': avg_drawdown,
            'total_trades': total_trades,
            'ai_recommended_count': len(ai_records),
            'ai_avg_return': (sum(r['annualized_return'] for r in ai_records) / len(ai_records)) if ai_records else 0,
            'non_ai_avg_return': (sum(r['annualized_return'] for r in non_ai_records) / len(non_ai_records)) if non_ai_records else 0,
        }

    def get_active_instances(self) -> List[str]:
        """获取当前跟踪的活跃实例列表"""
        return list(self._active_instances.keys())
