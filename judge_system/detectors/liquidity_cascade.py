"""
流动性级联捕捉检测器

从 FMZ 策略 "动态流动性级联捕捉策略" 转换
PineScript → Python

核心逻辑:
  监控价格与均线的偏离程度，识别流动性枯竭/级联事件
  - 价格大幅偏离均线 → 流动性枯竭 → 可能反转
  - 价格快速回归均线 → 流动性恢复 → 趋势确认

审判用途:
  检测锁妖塔推荐时市场是否处于极端状态
  - 做多推荐但价格远高于均线 = 追高风险 ⚠️
  - 做空推荐但价格远低于均线 = 杀跌风险 ⚠️
  - 价格在均线附近 = 正常交易环境 ✅
"""

import numpy as np
import pandas as pd

from judge_system.base_detector import BaseDetector, DetectorResult
from judge_system.judge_config import JudgeConfig


class LiquidityCascadeDetector(BaseDetector):
    """流动性级联捕捉检测器"""

    def __init__(self):
        super().__init__(name="liquidity_cascade")
        self.cfg = JudgeConfig

    def _sma(self, values: np.ndarray, period: int) -> np.ndarray:
        result = np.full_like(values, np.nan)
        if len(values) < period:
            return result
        for i in range(period - 1, len(values)):
            result[i] = np.mean(values[i - period + 1:i + 1])
        return result

    def detect(self, symbol: str, df: pd.DataFrame, **kwargs) -> DetectorResult:
        if df is None or len(df) < 60:
            return DetectorResult(
                detector_name=self.name,
                direction='neutral',
                score=0.0,
                confidence=0.0,
                detail='数据不足(需>=60根K线)'
            )

        close = df['close'].values
        high = df['high'].values
        low = df['low'].values

        # 1. 计算基准均线
        ma = self._sma(close, self.cfg.CASCADE_MA_PERIOD)

        if np.isnan(ma[-1]):
            return DetectorResult(
                detector_name=self.name,
                direction='neutral',
                score=0.0,
                confidence=0.0,
                detail='均线数据不足'
            )

        # 2. 计算价格偏离程度
        deviation = (close - ma) / ma  # 正=价格在均线上方，负=下方

        # 3. 计算波动率 (ATR代理)
        tr = np.maximum(high[1:] - low[1:],
                        np.abs(high[1:] - close[:-1]),
                        np.abs(low[1:] - close[:-1]))
        atr = np.mean(tr[-14:]) if len(tr) >= 14 else np.mean(tr)
        atr_pct = atr / close[-1] if close[-1] != 0 else 0

        # 4. 当前偏离状态
        current_dev = deviation[-1]
        abs_dev = abs(current_dev)

        # 历史偏离统计
        bars_per_unit = kwargs.get('bars_per_unit', 24)
        window = max(30, int(96 / bars_per_unit))  # ~24小时
        hist_dev = deviation[-min(window, len(deviation)):]
        hist_mean = np.mean(hist_dev)
        hist_std = np.std(hist_dev)

        # Z-Score: 当前偏离相对于历史的标准差
        z_score = (current_dev - hist_mean) / hist_std if hist_std > 0 else 0

        # 5. 级联检测
        detail_parts = []
        score = 0.0

        # 极端偏离检测
        if abs_dev > self.cfg.CASCADE_EXTREME_THRESHOLD:
            if current_dev > 0:
                detail_parts.append(f"极端偏离:价格超均线{abs_dev*100:.1f}%(可能回调)")
                score -= 0.5  # 过高 → 看空
            else:
                detail_parts.append(f"极端偏离:价格低均线{abs_dev*100:.1f}%(可能反弹)")
                score += 0.5  # 过低 → 看多
            confidence_base = 0.8
        elif abs_dev > self.cfg.CASCADE_DEVIATION_THRESHOLD:
            if current_dev > 0:
                detail_parts.append(f"显著偏离:价格超均线{abs_dev*100:.1f}%")
                score -= 0.25
            else:
                detail_parts.append(f"显著偏离:价格低均线{abs_dev*100:.1f}%")
                score += 0.25
            confidence_base = 0.6
        else:
            detail_parts.append(f"价格在均线附近(偏离{abs_dev*100:.2f}%)")
            confidence_base = 0.3

        # Z-Score 辅助判断
        if abs(z_score) > 2.0:
            detail_parts.append(f"Z-Score={z_score:.1f}(统计极端)")
            if z_score > 0:
                score -= 0.15  # 极端的正ZScore → 回调风险
            else:
                score += 0.15  # 极端的负ZScore → 反弹机会
            confidence_base = min(1.0, confidence_base + 0.2)

        # 波动率环境
        vol_detail = f"ATR={atr_pct*100:.2f}%"
        if atr_pct > 0.05:
            vol_detail += "(高波动)"
        elif atr_pct < 0.015:
            vol_detail += "(低波动)"
        detail_parts.append(vol_detail)

        score = np.clip(score, -1.0, 1.0)
        direction = 'long' if score > 0.2 else ('short' if score < -0.2 else 'neutral')
        confidence = min(1.0, max(0.1, confidence_base * (1 + abs(score) * 0.5)))
        triggered = abs(score) > 0.3

        return DetectorResult(
            detector_name=self.name,
            direction=direction,
            score=score,
            confidence=confidence,
            triggered=triggered,
            detail=' | '.join(detail_parts),
            meta={
                'deviation_pct': round(current_dev * 100, 2),
                'z_score': round(z_score, 2),
                'atr_pct': round(atr_pct * 100, 2),
            }
        )
