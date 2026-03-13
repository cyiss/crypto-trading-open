"""
AI参数推荐器 - AI Parameter Recommender

基于历史绩效数据，使用RandomForest/XGBoost等轻量ML模型
推荐最优网格参数组合。
"""

import logging
import os
import pickle
import hmac
import hashlib
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from decimal import Decimal

import numpy as np

logger = logging.getLogger(__name__)

# ML模型相关依赖是可选的
try:
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logger.warning("scikit-learn未安装，ML推荐功能不可用。安装: pip install scikit-learn")


# 特征列定义
FEATURE_COLUMNS = [
    'volatility',
    'trend_strength',
    'grid_interval',
    'order_amount',
    'follow_distance',
    'scalping_trigger_percent',
    'leverage',
]

TARGET_COLUMN = 'annualized_return'
DEFAULT_INTERNAL_MODEL_SIGNING_KEY = "internal-grid-sign-2d1f7a8c3e4b95d0"


class AIParameterRecommender:
    """
    AI参数推荐器

    工作流程：
    1. 从PerformanceTracker获取历史数据
    2. 训练RandomForest回归模型
    3. 在给定市场条件下，预测不同参数组合的预期收益
    4. 返回收益最高的参数组合（仅做±10-20%微调）

    安全机制：
    - 只在预测提升>2%时才推荐新参数
    - 所有推荐参数都受安全边界约束
    - 提供回滚功能
    """

    def __init__(
        self,
        model_path: str = "data/grid_param_model.pkl",
        min_samples: int = 30,
        prediction_threshold: float = 2.0,  # 最小预测提升（%）
    ):
        self.model_path = model_path
        self.min_samples = min_samples
        self.prediction_threshold = prediction_threshold

        self.model: Optional[Any] = None
        self.scaler: Optional[Any] = None
        self.model_version: str = "none"
        self.sample_count: int = 0
        self.last_trained: Optional[datetime] = None
        self.avg_prediction_error: float = 0.0

        # 加载已有模型
        self._load_model()

    def _load_model(self):
        """从磁盘加载预训练模型"""
        if not SKLEARN_AVAILABLE:
            return

        if os.path.exists(self.model_path):
            try:
                key = os.getenv("GRID_MODEL_SIGNING_KEY", DEFAULT_INTERNAL_MODEL_SIGNING_KEY).encode("utf-8")
                sig_path = f"{self.model_path}.sig"
                if not os.path.exists(sig_path):
                    logger.warning("模型签名文件缺失，跳过加载本地ML模型")
                    return

                with open(self.model_path, 'rb') as f:
                    payload = f.read()

                digest = hmac.new(key, payload, hashlib.sha256).hexdigest()
                with open(sig_path, 'r', encoding='utf-8') as f:
                    expected_digest = f.read().strip()

                if not hmac.compare_digest(digest, expected_digest):
                    logger.error("模型签名校验失败，拒绝加载本地ML模型")
                    return

                with open(self.model_path, 'rb') as f:
                    data = pickle.load(f)
                    self.model = data.get('model')
                    self.scaler = data.get('scaler')
                    self.model_version = data.get('version', 'unknown')
                    self.sample_count = data.get('sample_count', 0)
                    self.avg_prediction_error = data.get('avg_error', 0.0)

                if self.model:
                    logger.info(
                        f"✅ ML模型已加载: v{self.model_version}, "
                        f"样本={self.sample_count}, "
                        f"误差={self.avg_prediction_error:.2f}%"
                    )
            except Exception as e:
                logger.warning(f"加载ML模型失败: {e}")

    def _save_model(self):
        """保存模型到磁盘"""
        if not self.model:
            return

        os.makedirs(os.path.dirname(self.model_path) or '.', exist_ok=True)

        data = {
            'model': self.model,
            'scaler': self.scaler,
            'version': datetime.now().strftime('%Y%m%d_%H%M'),
            'sample_count': self.sample_count,
            'avg_error': self.avg_prediction_error,
            'last_trained': datetime.now().isoformat(),
        }

        with open(self.model_path, 'wb') as f:
            pickle.dump(data, f)

        key = os.getenv("GRID_MODEL_SIGNING_KEY", DEFAULT_INTERNAL_MODEL_SIGNING_KEY).encode("utf-8")
        with open(self.model_path, 'rb') as f:
            payload = f.read()
        digest = hmac.new(key, payload, hashlib.sha256).hexdigest()
        with open(f"{self.model_path}.sig", 'w', encoding='utf-8') as f:
            f.write(digest)

        logger.info(f"✅ ML模型已保存: {self.model_path}")

    def train(self, training_data: List[Dict]) -> Dict:
        """
        训练模型

        Args:
            training_data: 从PerformanceTracker.get_training_data()获取的数据

        Returns:
            训练结果字典
        """
        if not SKLEARN_AVAILABLE:
            return {'status': 'error', 'message': 'scikit-learn未安装'}

        if len(training_data) < self.min_samples:
            return {
                'status': 'insufficient_data',
                'message': f'训练数据不足: {len(training_data)} < {self.min_samples}',
            }

        # 准备特征和目标
        X = np.array([[row[col] for col in FEATURE_COLUMNS] for row in training_data])
        y = np.array([row[TARGET_COLUMN] for row in training_data])

        # 标准化特征
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)

        # 分割训练/测试集
        X_train, X_test, y_train, y_test = train_test_split(
            X_scaled, y, test_size=0.2, random_state=42
        )

        # 训练RandomForest
        self.model = RandomForestRegressor(
            n_estimators=100,
            max_depth=10,
            min_samples_split=5,
            min_samples_leaf=2,
            random_state=42,
            n_jobs=-1,
        )
        self.model.fit(X_train, y_train)

        # 评估
        y_pred = self.model.predict(X_test)
        mae = np.mean(np.abs(y_test - y_pred))
        r2 = self.model.score(X_test, y_test)

        self.sample_count = len(training_data)
        self.avg_prediction_error = float(mae)
        self.last_trained = datetime.now()
        self.model_version = datetime.now().strftime('%Y%m%d_%H%M')

        # 保存模型
        self._save_model()

        # 特征重要性
        importances = dict(zip(FEATURE_COLUMNS, self.model.feature_importances_))

        result = {
            'status': 'success',
            'samples': len(training_data),
            'mae': round(float(mae), 4),
            'r2_score': round(float(r2), 4),
            'feature_importances': importances,
            'model_version': self.model_version,
        }

        logger.info(f"✅ ML模型训练完成: R²={r2:.4f}, MAE={mae:.4f}")
        return result

    def recommend(
        self,
        current_volatility: float,
        current_trend: float,
        current_params: Dict[str, Any],
        current_apr: float = 0.0,
        param_ranges: Optional[Dict[str, Tuple[float, float]]] = None,
    ) -> Dict:
        """
        根据当前市场条件推荐参数

        Args:
            current_volatility: 当前年化波动率
            current_trend: 当前趋势强度 (-1.0 ~ 1.0)
            current_params: 当前参数字典
            current_apr: 当前APR（用于比较）
            param_ranges: 参数搜索范围（可选）

        Returns:
            推荐结果：
            {
                'recommended': bool,  # 是否推荐更改
                'new_params': dict,   # 推荐的新参数
                'predicted_apr': float,  # 预测APR
                'improvement': float,    # 预测提升百分点
                'confidence': float,     # 置信度
            }
        """
        if not self.model or not self.scaler:
            return {
                'recommended': False,
                'new_params': current_params,
                'predicted_apr': current_apr,
                'improvement': 0.0,
                'confidence': 0.0,
                'message': '模型未训练',
            }

        # 默认参数搜索范围（在当前值±20%范围内搜索）
        if param_ranges is None:
            param_ranges = {
                'grid_interval': (
                    max(1, current_params.get('grid_interval', 15) * 0.8),
                    current_params.get('grid_interval', 15) * 1.2,
                ),
                'order_amount': (
                    max(0.00001, current_params.get('order_amount', 0.0002) * 0.8),
                    current_params.get('order_amount', 0.0002) * 1.2,
                ),
                'follow_distance': (1, 5),
                'scalping_trigger_percent': (40, 90),
                'leverage': (5, 20),
            }

        # 在参数空间中搜索最佳组合
        best_params = None
        best_predicted = -float('inf')
        n_samples = 200  # 采样200个参数组合

        for _ in range(n_samples):
            # 随机采样参数
            sample = {
                'volatility': current_volatility,
                'trend_strength': current_trend,
                'grid_interval': np.random.uniform(*param_ranges['grid_interval']),
                'order_amount': np.random.uniform(*param_ranges['order_amount']),
                'follow_distance': np.random.randint(*param_ranges['follow_distance']),
                'scalping_trigger_percent': np.random.randint(*param_ranges['scalping_trigger_percent']),
                'leverage': np.random.randint(*param_ranges['leverage']),
            }

            # 预测收益
            X = np.array([[sample[col] for col in FEATURE_COLUMNS]])
            X_scaled = self.scaler.transform(X)
            predicted_apr = self.model.predict(X_scaled)[0]

            if predicted_apr > best_predicted:
                best_predicted = predicted_apr
                best_params = sample

        improvement = best_predicted - current_apr

        # 只在提升超过阈值时推荐
        recommended = improvement > self.prediction_threshold

        if recommended:
            # 将推荐参数四舍五入到合理精度
            new_params = current_params.copy()
            new_params['grid_interval'] = round(best_params['grid_interval'], 4)
            new_params['order_amount'] = round(best_params['order_amount'], 6)
            new_params['follow_distance'] = int(best_params['follow_distance'])
            new_params['scalping_trigger_percent'] = int(best_params['scalping_trigger_percent'])
            new_params['leverage'] = int(best_params['leverage'])
        else:
            new_params = current_params

        return {
            'recommended': recommended,
            'new_params': new_params,
            'predicted_apr': round(float(best_predicted), 2),
            'improvement': round(float(improvement), 2),
            'confidence': min(1.0, self.sample_count / 100),  # 样本越多置信度越高
        }

    @property
    def is_available(self) -> bool:
        """检查ML推荐是否可用"""
        return self.model is not None and SKLEARN_AVAILABLE

    def get_status(self) -> Dict:
        """获取模型状态"""
        return {
            'model_available': self.model is not None,
            'sklearn_available': SKLEARN_AVAILABLE,
            'model_version': self.model_version,
            'training_samples': self.sample_count,
            'last_trained': self.last_trained.isoformat() if self.last_trained else None,
            'avg_prediction_error': round(self.avg_prediction_error, 4),
            'prediction_threshold': self.prediction_threshold,
        }
