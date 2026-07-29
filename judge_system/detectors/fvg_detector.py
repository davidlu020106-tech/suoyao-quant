"""
FVG (公允价值缺口) 检测器

从 FMZ 策略 "FVG动量短线交易策略" 转换
PineScript → Python

核心逻辑:
  看涨FVG: low[1] > high[3]  → 当前K线低点 > 前3根K线高点 = 向上缺口
  看跌FVG: high[1] < low[3]  → 当前K线高点 < 前3根K线低点 = 向下缺口

审判用途:
  检测锁妖塔推荐时刻是否存在 FVG 支撑/阻力
  - 做多推荐时，下方有看涨FVG = 支撑确认 ✅
  - 做空推荐时，上方有看跌FVG = 阻力确认 ✅
  - 无FVG支撑的推荐 = 信号偏弱 ⚠️
"""

import numpy as np
import pandas as pd

from judge_system.base_detector import BaseDetector, DetectorResult
from judge_system.judge_config import JudgeConfig


class FvgDetector(BaseDetector):
    """公允价值缺口检测器"""

    def __init__(self):
        super().__init__(name="fvg_detector")
        self.cfg = JudgeConfig

    def detect(self, symbol: str, df: pd.DataFrame, **kwargs) -> DetectorResult:
        if df is None or len(df) < 10:
            return DetectorResult(
                detector_name=self.name,
                direction='neutral',
                score=0.0,
                confidence=0.0,
                detail='数据不足'
            )

        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        open_p = df['open'].values

        # 检测看涨FVG: low[i-1] > high[i-3]
        bullish_fvg = np.full(len(close), False)
        bearish_fvg = np.full(len(close), False)

        for i in range(3, len(close)):
            # 看涨FVG: 当前K线最低点 > 前3根K线最高点
            if low[i-1] > high[i-3]:
                bullish_fvg[i] = True
            # 看跌FVG: 当前K线最高点 < 前3根K线最低点
            if high[i-1] < low[i-3]:
                bearish_fvg[i] = True

        # 最新K线的FVG状态
        last_bullish = bullish_fvg[-1] or bullish_fvg[-2] if len(close) > 1 else False
        last_bearish = bearish_fvg[-1] or bearish_fvg[-2] if len(close) > 1 else False

        # 统计近期的FVG频率
        bars_per_unit = kwargs.get('bars_per_unit', 24)
        recent = max(20, int(96 / bars_per_unit))  # ~24小时窗口
        recent_bullish = np.sum(bullish_fvg[-recent:]) if len(close) > recent else 0
        recent_bearish = np.sum(bearish_fvg[-recent:]) if len(close) > recent else 0

        # 计算缺口幅度（最新FVG的价差百分比）
        gap_pct = 0.0
        detail_parts = []

        if last_bullish:
            # 向上的缺口幅度 = low[-2] / high[-4] - 1
            gap_pct = (low[-2] / high[-4] - 1) * 100 if len(close) >= 4 else 0
            detail_parts.append(f"看涨FVG活跃(幅度{gap_pct:.2f}%)")
        elif last_bearish:
            gap_pct = (1 - high[-2] / low[-4]) * 100 if len(close) >= 4 else 0
            detail_parts.append(f"看跌FVG活跃(幅度{gap_pct:.2f}%)")

        if recent_bullish > 0:
            detail_parts.append(f"近20K线看涨FVG:{recent_bullish}次")
        if recent_bearish > 0:
            detail_parts.append(f"近20K线看跌FVG:{recent_bearish}次")

        # 综合评分
        # 看涨FVG多 → 看多信号；看跌FVG多 → 看空信号
        net_fvg = recent_bullish - recent_bearish
        fvg_total = recent_bullish + recent_bearish

        if fvg_total == 0:
            score = 0.0
            direction = 'neutral'
            confidence = 0.0
            detail = '无FVG信号'
        else:
            # score 范围 [-1, 1]，正=看多
            score = np.clip(net_fvg / max(fvg_total, 1), -1.0, 1.0)
            if score > 0.2:
                direction = 'long'
            elif score < -0.2:
                direction = 'short'
            else:
                direction = 'neutral'
            confidence = min(1.0, fvg_total / 10.0)
            detail = ' | '.join(detail_parts)

        triggered = abs(score) > 0.2 and confidence > 0.3

        return DetectorResult(
            detector_name=self.name,
            direction=direction,
            score=score,
            confidence=confidence,
            triggered=triggered,
            detail=detail
        )
