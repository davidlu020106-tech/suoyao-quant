"""
CVD (累计成交量差值) 背离检测器

从 FMZ 策略 "CVD背离量化交易策略" 转换
PineScript → Python

核心逻辑:
  1. 计算 CVD = EMA(成交量 × sign(收盘价-开盘价))
  2. 检测 CVD 与价格的背离:
     - 顶背离: 价格创新高，但 CVD 未创新高 → 看跌信号
     - 底背离: 价格创新低，但 CVD 未创新低 → 看涨信号

审判用途:
  检测锁妖塔推荐方向是否与真实资金流向一致
  - 锁妖塔看多但有CVD顶背离 → ⚠️ 虚假上涨
  - 锁妖塔看空但有CVD底背离 → ⚠️ 虚假下跌
"""

import numpy as np
import pandas as pd

from judge_system.base_detector import BaseDetector, DetectorResult
from judge_system.judge_config import JudgeConfig


class CvdDivergenceDetector(BaseDetector):
    """CVD背离检测器"""

    def __init__(self):
        super().__init__(name="cvd_divergence")
        self.cfg = JudgeConfig

    def _find_pivots(self, values: np.ndarray, order: int = 5) -> tuple:
        """
        找到摆动高点和低点

        Returns:
            (high_idx, high_vals, low_idx, low_vals)
        """
        high_idx = []
        high_vals = []
        low_idx = []
        low_vals = []

        for i in range(order, len(values) - order):
            # 局部高点
            if all(values[i] >= values[i-j] for j in range(1, order+1)) and \
               all(values[i] >= values[i+j] for j in range(1, order+1)):
                high_idx.append(i)
                high_vals.append(values[i])
            # 局部低点
            if all(values[i] <= values[i-j] for j in range(1, order+1)) and \
               all(values[i] <= values[i+j] for j in range(1, order+1)):
                low_idx.append(i)
                low_vals.append(values[i])

        return np.array(high_idx), np.array(high_vals), np.array(low_idx), np.array(low_vals)

    def detect(self, symbol: str, df: pd.DataFrame, **kwargs) -> DetectorResult:
        if df is None or len(df) < 50:
            return DetectorResult(
                detector_name=self.name,
                direction='neutral',
                score=0.0,
                confidence=0.0,
                detail='数据不足(需>=50根K线)'
            )

        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        open_p = df['open'].values
        volume = df['volume'].values if 'volume' in df.columns else np.ones_like(close)
        # 如果没有volume列，用价格波动幅度模拟
        if 'volume' not in df.columns or np.all(volume == volume[0]):
            volume = (high - low) / close * 100

        # 1. 计算 CVD
        # CVD = Σ(volume × sign(close - open)) 的EMA
        raw_cvd = np.where(close >= open_p, volume, -volume)
        cvd = self._ema(raw_cvd, self.cfg.CVD_EMA_LENGTH)

        if np.isnan(cvd).any():
            cvd = np.nan_to_num(cvd, 0)

        # 2. 找到摆动点
        # ★ 修复: 根据数据周期自动调整pivot窗口
        bars_per_unit = kwargs.get('bars_per_unit', 24)  # 默认1H=24根/天
        pivot_order = max(5, int(20 / bars_per_unit * 24))  # 目标=20根1H≈5根4H≈80根15m
        high_idx, high_vals, low_idx, low_vals = self._find_pivots(close, pivot_order)
        cvd_high_vals = cvd[high_idx] if len(high_idx) > 0 else np.array([])
        cvd_low_vals = cvd[low_idx] if len(low_idx) > 0 else np.array([])

        # 3. 检测背离
        bearish_divergence = False  # 顶背离: 价格↑但CVD↓
        bullish_divergence = False   # 底背离: 价格↓但CVD↑
        div_score = 0.0
        detail_parts = []

        # 顶背离检测: 最后两个价格高点创新高，但CVD高点未创新高
        if len(high_vals) >= 2:
            last_two_price = high_vals[-2:]
            last_two_cvd = cvd_high_vals[-2:] if len(cvd_high_vals) >= 2 else np.array([])

            if len(last_two_cvd) >= 2:
                if last_two_price[-1] > last_two_price[-2] and last_two_cvd[-1] < last_two_cvd[-2]:
                    bearish_divergence = True
                    div_score -= 0.6
                    decline_pct = (last_two_cvd[-2] - last_two_cvd[-1]) / abs(last_two_cvd[-2]) * 100
                    detail_parts.append(f"顶背离:价新高但CVD降{decline_pct:.1f}%")
                elif last_two_price[-1] > last_two_price[-2] and last_two_cvd[-1] > last_two_cvd[-2]:
                    # 价格和CVD一起涨 = 健康上涨
                    div_score += 0.3
                    detail_parts.append("价涨量增(健康上涨)")

        # 底背离检测: 最后两个价格低点创新低，但CVD低点未创新低
        if len(low_vals) >= 2:
            last_two_price = low_vals[-2:]
            last_two_cvd = cvd_low_vals[-2:] if len(cvd_low_vals) >= 2 else np.array([])

            if len(last_two_cvd) >= 2:
                if last_two_price[-1] < last_two_price[-2] and last_two_cvd[-1] > last_two_cvd[-2]:
                    bullish_divergence = True
                    div_score += 0.6
                    rise_pct = (last_two_cvd[-1] - last_two_cvd[-2]) / abs(last_two_cvd[-2]) * 100
                    detail_parts.append(f"底背离:价新低但CVD升{rise_pct:.1f}%")
                elif last_two_price[-1] < last_two_price[-2] and last_two_cvd[-1] < last_two_cvd[-2]:
                    div_score -= 0.3
                    detail_parts.append("价跌量缩(健康下跌)")

        # 4. 最近CVD趋势
        recent_len = min(int(96 / bars_per_unit), len(cvd))  # ~24小时窗口
        recent_cvd = cvd[-recent_len:]
        cvd_trend = (recent_cvd[-1] - recent_cvd[0]) / abs(recent_cvd[0]) * 100 if recent_cvd[0] != 0 else 0
        if cvd_trend > 5:
            detail_parts.append(f"CVD上升{cvd_trend:.1f}%(资金流入)")
            div_score += 0.2
        elif cvd_trend < -5:
            detail_parts.append(f"CVD下降{cvd_trend:.1f}%(资金流出)")
            div_score -= 0.2

        # 综合判定
        score = np.clip(div_score, -1.0, 1.0)
        if score > 0.2:
            direction = 'long'
        elif score < -0.2:
            direction = 'short'
        else:
            direction = 'neutral'

        confidence = min(1.0, abs(score) + 0.3)
        triggered = abs(score) > 0.35
        detail = ' | '.join(detail_parts) if detail_parts else '无显著背离'

        return DetectorResult(
            detector_name=self.name,
            direction=direction,
            score=score,
            confidence=confidence,
            triggered=triggered,
            detail=detail,
            meta={
                'bearish_divergence': bearish_divergence,
                'bullish_divergence': bullish_divergence,
                'cvd_trend_pct': round(cvd_trend, 2),
            }
        )
