"""
检测器基类 — 所有审判检测器的统一接口

每个检测器输入 OHLC 数据，输出方向评分和置信度。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd


@dataclass
class DetectorResult:
    """
    检测器输出结果

    Attributes:
        detector_name: 检测器名称
        direction: 方向 'long' / 'short' / 'neutral'
        score: 评分 [-1.0, +1.0]，正=看多，负=看空
        confidence: 置信度 [0.0, 1.0]
        triggered: 是否触发信号
        detail: 详细说明（触发原因等）
        meta: 额外元数据
    """
    detector_name: str
    direction: str = 'neutral'
    score: float = 0.0
    confidence: float = 0.0
    triggered: bool = False
    detail: str = ''
    meta: dict = field(default_factory=dict)

    @property
    def is_long(self) -> bool:
        return self.direction == 'long'

    @property
    def is_short(self) -> bool:
        return self.direction == 'short'

    @property
    def is_neutral(self) -> bool:
        return self.direction == 'neutral'


class BaseDetector(ABC):
    """
    检测器基类

    所有审判检测器继承此类，实现 detect() 方法。

    输入: symbol + OHLC DataFrame → 输出: DetectorResult
    """

    def __init__(self, name: str = None):
        self.name = name or self.__class__.__name__

    @staticmethod
    def _ema(values: 'np.ndarray', period: int) -> 'np.ndarray':
        """共享EMA计算 — 所有检测器统一使用"""
        import numpy as np
        alpha = 2.0 / (period + 1)
        result = np.full_like(values, np.nan)
        result[0] = values[0]
        for i in range(1, len(values)):
            result[i] = alpha * values[i] + (1 - alpha) * result[i-1]
        return result

    @abstractmethod
    def detect(self, symbol: str, df: pd.DataFrame, **kwargs) -> DetectorResult:
        """
        对指定币种执行检测

        Args:
            symbol: 币种名称（如 'BTC', 'ETH'）
            df: OHLC DataFrame，必须包含列:
                open, high, low, close, volume
            **kwargs: 额外参数（如资金费率、持仓量等）

        Returns:
            DetectorResult 检测结果
        """
        ...

    def __call__(self, symbol: str, df: pd.DataFrame, **kwargs) -> DetectorResult:
        return self.detect(symbol, df, **kwargs)

    def __str__(self) -> str:
        return f"{self.name}"
