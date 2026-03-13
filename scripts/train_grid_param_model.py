#!/usr/bin/env python3
"""
模型训练脚本 - Train Grid Parameter Model

用法:
    python scripts/train_grid_param_model.py
    python scripts/train_grid_param_model.py --db data/grid_scanner.db --symbol BTC
    python scripts/train_grid_param_model.py --data-only  # 只输出数据统计，不训练

功能:
1. 从grid_performance表读取历史数据
2. 数据清洗和统计
3. 训练RandomForest回归模型
4. 输出模型评估结果
5. 保存模型到data/grid_param_model.pkl
"""

import argparse
import asyncio
import logging
import sys
import os
from pathlib import Path

# 添加项目根目录
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.services.ml.performance_tracker import PerformanceTracker
from core.services.ml.parameter_recommender import AIParameterRecommender

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(description='训练网格参数优化模型')
    parser.add_argument('--db', default='data/grid_scanner.db', help='数据库路径')
    parser.add_argument('--symbol', default=None, help='只训练特定代币的数据')
    parser.add_argument('--days', type=int, default=90, help='使用最近N天的数据')
    parser.add_argument('--min-samples', type=int, default=30, help='最少样本数')
    parser.add_argument('--output', default='data/grid_param_model.pkl', help='模型输出路径')
    parser.add_argument('--data-only', action='store_true', help='只输出数据统计，不训练')
    args = parser.parse_args()

    print("=" * 60)
    print("🔧 网格参数优化模型训练器")
    print("=" * 60)

    # 1. 初始化绩效记录器
    tracker = PerformanceTracker(args.db)
    await tracker.initialize()

    # 2. 获取训练数据
    print(f"\n📊 获取训练数据...")
    print(f"   数据库: {args.db}")
    print(f"   时间范围: 最近{args.days}天")
    if args.symbol:
        print(f"   代币过滤: {args.symbol}")

    data = await tracker.get_training_data(
        symbol=args.symbol,
        min_samples=args.min_samples,
        days=args.days,
    )

    if not data:
        print(f"\n❌ 训练数据不足 (需要至少{args.min_samples}条记录)")
        print("   提示: 需要先运行网格交易并启用绩效记录")
        await tracker.close()
        return

    print(f"   ✓ 获取到 {len(data)} 条有效记录")

    # 3. 数据统计
    if args.data_only or True:  # 始终显示统计
        print(f"\n📈 数据统计:")
        print(f"   样本数: {len(data)}")
        avg_return = sum(r['annualized_return'] for r in data) / len(data)
        avg_drawdown = sum(r['max_drawdown'] for r in data) / len(data)
        avg_trades = sum(r['trade_count'] for r in data) / len(data)
        print(f"   平均年化收益: {avg_return:.2f}%")
        print(f"   平均最大回撤: {avg_drawdown:.2f}%")
        print(f"   平均交易次数: {avg_trades:.0f}")

        # 参数范围
        intervals = [r['grid_interval'] for r in data]
        amounts = [r['order_amount'] for r in data]
        print(f"   grid_interval范围: {min(intervals):.4f} ~ {max(intervals):.4f}")
        print(f"   order_amount范围: {min(amounts):.6f} ~ {max(amounts):.6f}")

    if args.data_only:
        await tracker.close()
        return

    # 4. 训练模型
    print(f"\n🤖 训练ML模型...")
    recommender = AIParameterRecommender(model_path=args.output)
    result = recommender.train(data)

    if result['status'] == 'success':
        print(f"\n✅ 模型训练成功!")
        print(f"   版本: v{result['model_version']}")
        print(f"   训练样本: {result['samples']}")
        print(f"   MAE(平均绝对误差): {result['mae']:.4f}")
        print(f"   R²得分: {result['r2_score']:.4f}")
        print(f"\n   特征重要性:")
        for feat, imp in sorted(result['feature_importances'].items(), key=lambda x: -x[1]):
            bar = "█" * int(imp * 40)
            print(f"     {feat:30s} {imp:.4f} {bar}")
        print(f"\n   模型已保存到: {args.output}")
    else:
        print(f"\n❌ 训练失败: {result.get('message', 'unknown error')}")

    await tracker.close()
    print("\n完成!")


if __name__ == "__main__":
    asyncio.run(main())
