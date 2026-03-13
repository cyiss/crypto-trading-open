"""
扫描器历史持久化 - Scanner History Storage

将扫描器的实时结果持久化到SQLite数据库，供Web Dashboard展示和ML训练使用。
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import List, Optional, Dict, Any

import aiosqlite

logger = logging.getLogger(__name__)


class ScannerHistoryStorage:
    """
    扫描器历史存储器

    职责：
    1. 保存单次扫描的代币评级快照
    2. 保存扫描器汇总信息
    3. 查询历史数据（支持分页、过滤）
    4. 获取APR趋势数据（供图表使用）
    """

    def __init__(self, db_path: str = "data/grid_scanner.db", retention_days: int = 7):
        self.db_path = db_path
        self.retention_days = retention_days
        self._db: Optional[aiosqlite.Connection] = None
        self._initialized = False
        self._last_cleanup_time: Optional[datetime] = None
        self._cleanup_interval_seconds = 3600

    async def initialize(self):
        """初始化数据库，创建表"""
        db_file = Path(self.db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL;")
        await self._db.execute("PRAGMA synchronous=NORMAL;")

        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS scanner_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                exchange TEXT NOT NULL,
                symbol TEXT NOT NULL,
                current_price REAL DEFAULT 0,
                grid_width_percent REAL DEFAULT 0,
                grid_interval_percent REAL DEFAULT 0,
                grid_count INTEGER DEFAULT 0,
                price_range TEXT DEFAULT '',
                running_seconds INTEGER DEFAULT 0,
                total_crosses INTEGER DEFAULT 0,
                buy_crosses INTEGER DEFAULT 0,
                sell_crosses INTEGER DEFAULT 0,
                complete_cycles INTEGER DEFAULT 0,
                cycles_per_hour REAL DEFAULT 0,
                avg_cycles_per_5min REAL DEFAULT 0,
                recent_5min_cycles INTEGER DEFAULT 0,
                estimated_apr REAL DEFAULT 0,
                volume_24h_usdc REAL DEFAULT 0,
                price_change_24h_percent REAL DEFAULT 0,
                rating TEXT DEFAULT '',
                score REAL DEFAULT 0,
                s_rating_duration_str TEXT DEFAULT '--'
            );

            CREATE INDEX IF NOT EXISTS idx_snapshots_time ON scanner_snapshots(scan_time);
            CREATE INDEX IF NOT EXISTS idx_snapshots_symbol ON scanner_snapshots(symbol);
            CREATE INDEX IF NOT EXISTS idx_snapshots_exchange ON scanner_snapshots(exchange);
            CREATE INDEX IF NOT EXISTS idx_snapshots_rating ON scanner_snapshots(rating);

            CREATE TABLE IF NOT EXISTS scanner_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_start_time TIMESTAMP,
                scan_end_time TIMESTAMP,
                exchange TEXT NOT NULL,
                total_symbols INTEGER DEFAULT 0,
                s_rated_count INTEGER DEFAULT 0,
                a_rated_count INTEGER DEFAULT 0,
                b_rated_count INTEGER DEFAULT 0,
                top_symbols TEXT DEFAULT '[]',
                scan_duration_seconds INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_summaries_time ON scanner_summaries(scan_end_time);

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

            CREATE INDEX IF NOT EXISTS idx_perf_symbol ON grid_performance(symbol);
            CREATE INDEX IF NOT EXISTS idx_perf_period ON grid_performance(period_start, period_end);
        """)

        await self._db.commit()
        self._initialized = True
        logger.info(f"✅ 扫描器历史数据库初始化完成: {self.db_path}")

    async def close(self):
        """关闭数据库连接"""
        if self._db:
            await self._db.close()
            self._db = None

    async def _maybe_cleanup_old_snapshots(self):
        """定期清理过期快照，避免数据库无限增长。"""
        if not self._initialized or self.retention_days <= 0:
            return

        now = datetime.now()
        if self._last_cleanup_time and (now - self._last_cleanup_time).total_seconds() < self._cleanup_interval_seconds:
            return

        cutoff = (now - timedelta(days=self.retention_days)).isoformat()
        try:
            await self._db.execute(
                "DELETE FROM scanner_snapshots WHERE scan_time < ?",
                (cutoff,),
            )
            await self._db.commit()
            self._last_cleanup_time = now
        except Exception as e:
            logger.error(f"清理过期快照失败: {e}")

    # ──────────────────────────────────────────────
    # 保存操作
    # ──────────────────────────────────────────────

    async def save_snapshot(
        self,
        symbol: str,
        exchange: str,
        result_dict: Dict[str, Any]
    ):
        """
        保存单个代币的扫描快照

        Args:
            symbol: 交易对符号
            exchange: 交易所名称
            result_dict: 从SimulationResult.to_dict()获取的字典
        """
        if not self._initialized:
            return

        try:
            await self._db.execute("""
                INSERT INTO scanner_snapshots
                (scan_time, exchange, symbol, current_price, grid_width_percent,
                 grid_interval_percent, grid_count, price_range, running_seconds,
                 total_crosses, buy_crosses, sell_crosses, complete_cycles,
                 cycles_per_hour, avg_cycles_per_5min, recent_5min_cycles,
                 estimated_apr, volume_24h_usdc, price_change_24h_percent,
                 rating, score, s_rating_duration_str)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                exchange,
                symbol,
                result_dict.get('current_price', 0),
                result_dict.get('grid_width', '0').replace('%', '') if isinstance(result_dict.get('grid_width'), str) else 0,
                result_dict.get('grid_interval', '0').replace('%', '') if isinstance(result_dict.get('grid_interval'), str) else 0,
                result_dict.get('grid_count', 0),
                result_dict.get('price_range', ''),
                result_dict.get('running_seconds', 0),
                result_dict.get('total_crosses', 0),
                result_dict.get('buy_crosses', 0),
                result_dict.get('sell_crosses', 0),
                result_dict.get('complete_cycles', 0),
                result_dict.get('cycles_per_hour', 0),
                result_dict.get('avg_cycles_per_5min', 0),
                result_dict.get('recent_5min_cycles', 0),
                result_dict.get('estimated_apr', 0),
                result_dict.get('volume_24h', 0),
                result_dict.get('price_change_24h', 0),
                result_dict.get('rating', ''),
                result_dict.get('score', 0),
                result_dict.get('s_rating_duration_str', '--'),
            ))
            await self._db.commit()
            await self._maybe_cleanup_old_snapshots()
        except Exception as e:
            logger.error(f"保存快照失败 [{symbol}]: {e}")

    async def save_batch_snapshots(
        self,
        exchange: str,
        results: List[Dict[str, Any]]
    ):
        """
        批量保存扫描快照

        Args:
            exchange: 交易所名称
            results: SimulationResult.to_dict()列表
        """
        if not self._initialized or not results:
            return

        now = datetime.now().isoformat()
        rows = []
        for r in results:
            rows.append((
                now, exchange, r.get('symbol', ''),
                r.get('current_price', 0),
                r.get('grid_width', '0').replace('%', '') if isinstance(r.get('grid_width'), str) else 0,
                r.get('grid_interval', '0').replace('%', '') if isinstance(r.get('grid_interval'), str) else 0,
                r.get('grid_count', 0),
                r.get('price_range', ''),
                r.get('running_seconds', 0),
                r.get('total_crosses', 0),
                r.get('buy_crosses', 0),
                r.get('sell_crosses', 0),
                r.get('complete_cycles', 0),
                r.get('cycles_per_hour', 0),
                r.get('avg_cycles_per_5min', 0),
                r.get('recent_5min_cycles', 0),
                r.get('estimated_apr', 0),
                r.get('volume_24h', 0),
                r.get('price_change_24h', 0),
                r.get('rating', ''),
                r.get('score', 0),
                r.get('s_rating_duration_str', '--'),
            ))

        try:
            await self._db.executemany("""
                INSERT INTO scanner_snapshots
                (scan_time, exchange, symbol, current_price, grid_width_percent,
                 grid_interval_percent, grid_count, price_range, running_seconds,
                 total_crosses, buy_crosses, sell_crosses, complete_cycles,
                 cycles_per_hour, avg_cycles_per_5min, recent_5min_cycles,
                 estimated_apr, volume_24h_usdc, price_change_24h_percent,
                 rating, score, s_rating_duration_str)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, rows)
            await self._db.commit()
            logger.debug(f"批量保存快照: {len(rows)} 条")
            await self._maybe_cleanup_old_snapshots()
        except Exception as e:
            logger.error(f"批量保存快照失败: {e}")

    async def save_summary(self, summary: Dict[str, Any]):
        """保存扫描汇总"""
        if not self._initialized:
            return

        try:
            await self._db.execute("""
                INSERT INTO scanner_summaries
                (scan_start_time, scan_end_time, exchange, total_symbols,
                 s_rated_count, a_rated_count, b_rated_count, top_symbols,
                 scan_duration_seconds)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                summary.get('start_time', datetime.now().isoformat()),
                summary.get('end_time', datetime.now().isoformat()),
                summary.get('exchange', ''),
                summary.get('total_symbols', 0),
                summary.get('s_rated_count', 0),
                summary.get('a_rated_count', 0),
                summary.get('b_rated_count', 0),
                json.dumps(summary.get('top_symbols', [])),
                summary.get('duration_seconds', 0),
            ))
            await self._db.commit()
        except Exception as e:
            logger.error(f"保存扫描汇总失败: {e}")

    # ──────────────────────────────────────────────
    # 查询操作
    # ──────────────────────────────────────────────

    async def get_latest_snapshots(
        self,
        exchange: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict]:
        """获取最新一次扫描的所有快照"""
        if not self._initialized:
            return []

        # 先找到最新一次扫描时间
        query = "SELECT MAX(scan_time) as latest FROM scanner_snapshots"
        params = []
        if exchange:
            query += " WHERE exchange = ?"
            params.append(exchange)

        async with self._db.execute(query, params) as cursor:
            row = await cursor.fetchone()
            if not row or not row[0]:
                return []
            latest_time = row[0]

        # 获取该时间点的所有快照
        query2 = """
            SELECT * FROM scanner_snapshots
            WHERE scan_time >= ?
        """
        params2 = [latest_time]
        if exchange:
            query2 += " AND exchange = ?"
            params2.append(exchange)

        query2 += " ORDER BY estimated_apr DESC LIMIT ?"
        params2.append(limit)

        async with self._db.execute(query2, params2) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_snapshots_by_time(
        self,
        hours: int = 24,
        exchange: Optional[str] = None,
        symbol: Optional[str] = None,
        rating: Optional[str] = None,
        page: int = 1,
        page_size: int = 50
    ) -> Dict:
        """按时间范围查询快照（支持分页）"""
        if not self._initialized:
            return {"total": 0, "data": []}

        since = (datetime.now() - timedelta(hours=hours)).isoformat()

        where = ["scan_time >= ?"]
        params: list = [since]
        if exchange:
            where.append("exchange = ?")
            params.append(exchange)
        if symbol:
            where.append("symbol = ?")
            params.append(symbol)
        if rating:
            where.append("rating LIKE ?")
            params.append(f"%{rating}%")

        where_clause = " AND ".join(where)

        # Count
        async with self._db.execute(
            f"SELECT COUNT(*) FROM scanner_snapshots WHERE {where_clause}",
            params
        ) as cursor:
            row = await cursor.fetchone()
            total = row[0] if row else 0

        # Data
        offset = (page - 1) * page_size
        query = f"""
            SELECT * FROM scanner_snapshots
            WHERE {where_clause}
            ORDER BY scan_time DESC
            LIMIT ? OFFSET ?
        """
        async with self._db.execute(query, params + [page_size, offset]) as cursor:
            rows = await cursor.fetchall()
            data = [dict(r) for r in rows]

        return {"total": total, "page": page, "page_size": page_size, "data": data}

    async def get_apr_trend(
        self,
        symbol: str,
        hours: int = 24,
        exchange: Optional[str] = None
    ) -> Dict:
        """获取某代币的APR历史趋势"""
        if not self._initialized:
            return {"symbol": symbol, "timestamps": [], "apr_values": [], "ratings": []}

        since = (datetime.now() - timedelta(hours=hours)).isoformat()

        query = """
            SELECT scan_time, estimated_apr, rating, complete_cycles,
                   cycles_per_hour, current_price
            FROM scanner_snapshots
            WHERE symbol = ? AND scan_time >= ?
        """
        params: list = [symbol, since]
        if exchange:
            query += " AND exchange = ?"
            params.append(exchange)

        query += " ORDER BY scan_time ASC"

        async with self._db.execute(query, params) as cursor:
            rows = await cursor.fetchall()

        return {
            "symbol": symbol,
            "timestamps": [r[0] for r in rows],
            "apr_values": [r[1] for r in rows],
            "ratings": [r[2] for r in rows],
            "complete_cycles": [r[3] for r in rows],
            "cycles_per_hour": [r[4] for r in rows],
            "prices": [r[5] for r in rows],
        }

    async def get_summaries(
        self,
        limit: int = 20,
        exchange: Optional[str] = None
    ) -> List[Dict]:
        """获取扫描汇总列表"""
        if not self._initialized:
            return []

        query = "SELECT * FROM scanner_summaries"
        params = []
        if exchange:
            query += " WHERE exchange = ?"
            params.append(exchange)
        query += " ORDER BY scan_end_time DESC LIMIT ?"
        params.append(limit)

        async with self._db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d['top_symbols'] = json.loads(d.get('top_symbols', '[]'))
                results.append(d)
            return results

    async def get_statistics(self, exchange: Optional[str] = None) -> Dict:
        """获取扫描器统计概览"""
        if not self._initialized:
            return {}

        where = ""
        params = []
        if exchange:
            where = " WHERE exchange = ?"
            params.append(exchange)

        stats = {}

        # 总快照数
        async with self._db.execute(f"SELECT COUNT(*) FROM scanner_snapshots{where}", params) as cursor:
            row = await cursor.fetchone()
            stats['total_snapshots'] = row[0] if row else 0

        # 代币数
        async with self._db.execute(
            f"SELECT COUNT(DISTINCT symbol) FROM scanner_snapshots{where}", params
        ) as cursor:
            row = await cursor.fetchone()
            stats['unique_symbols'] = row[0] if row else 0

        # 当前S/A级代币数（最新扫描）
        latest_time_query = "SELECT MAX(scan_time) FROM scanner_snapshots"
        async with self._db.execute(latest_time_query) as cursor:
            row = await cursor.fetchone()
            latest = row[0] if row else None

        if latest:
            rating_query = f"""
                SELECT rating, COUNT(*) as cnt FROM scanner_snapshots
                WHERE scan_time >= ? {('AND exchange = ?' if exchange else '')}
                GROUP BY rating
            """
            rparams = [latest] + (params if exchange else [])
            async with self._db.execute(rating_query, rparams) as cursor:
                rows = await cursor.fetchall()
                stats['rating_counts'] = {r[0]: r[1] for r in rows}

        # 平均APR
        async with self._db.execute(
            f"SELECT AVG(estimated_apr) FROM scanner_snapshots{where}", params
        ) as cursor:
            row = await cursor.fetchone()
            stats['avg_apr'] = round(row[0], 2) if row and row[0] else 0

        return stats

    # ──────────────────────────────────────────────
    # Grid Performance 操作
    # ──────────────────────────────────────────────

    async def save_grid_performance(self, perf: Dict[str, Any]):
        """保存网格交易绩效数据"""
        if not self._initialized:
            return

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
                perf.get('instance_id', ''),
                perf.get('symbol', ''),
                perf.get('exchange', ''),
                perf.get('grid_type', 'follow_long'),
                perf.get('grid_interval', 0),
                perf.get('order_amount', 0),
                perf.get('follow_distance', 1),
                perf.get('scalping_trigger_percent', 80),
                perf.get('leverage', 10),
                perf.get('volatility', 0),
                perf.get('trend_strength', 0),
                perf.get('period_start', datetime.now().isoformat()),
                perf.get('period_end', datetime.now().isoformat()),
                perf.get('annualized_return', 0),
                perf.get('max_drawdown', 0),
                perf.get('trade_count', 0),
                perf.get('total_pnl', 0),
                perf.get('sharpe_ratio', 0),
                1 if perf.get('is_ai_recommended', False) else 0,
            ))
            await self._db.commit()
        except Exception as e:
            logger.error(f"保存网格绩效失败: {e}")

    async def get_grid_performance(
        self,
        symbol: Optional[str] = None,
        instance_id: Optional[str] = None,
        days: int = 30,
        page: int = 1,
        page_size: int = 100,
    ) -> Dict[str, Any]:
        """查询网格绩效数据"""
        if not self._initialized:
            return {"total": 0, "page": page, "page_size": page_size, "data": []}

        since = (datetime.now() - timedelta(days=days)).isoformat()

        query = "SELECT * FROM grid_performance WHERE period_start >= ?"
        params: list = [since]

        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        if instance_id:
            query += " AND instance_id = ?"
            params.append(instance_id)

        async with self._db.execute(
            f"SELECT COUNT(*) FROM ({query}) AS perf_q",
            params,
        ) as cursor:
            row = await cursor.fetchone()
            total = row[0] if row else 0

        query += " ORDER BY period_start DESC LIMIT ? OFFSET ?"
        offset = (page - 1) * page_size

        async with self._db.execute(query, params + [page_size, offset]) as cursor:
            rows = await cursor.fetchall()
            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "data": [dict(r) for r in rows],
            }
