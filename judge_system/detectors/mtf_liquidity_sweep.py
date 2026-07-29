"""
多时间框架流动性扫荡检测器

从 FMZ 策略 "多时段流动性扫荡趋势确认量化交易策略" 转换
PineScript → Python

核心逻辑:
  1. 高时间框架(4H)确定趋势方向
  2. 低时间框架(15m)检测是否突破HTF高/低点
  3. 突破HTF高点 + HTF看涨 → 做多信号
  4. 跌破HTF低点 + HTF看跌 → 做空信号

审判用途:
  验证锁妖塔信号在高时间框架上是否得到支持
  - 锁妖塔看多 + HTF也看多 = 高置信度 ✅
  - 锁妖塔看多但HTF看跌 = 逆势信号，低置信度 ⚠️
"""

import numpy as np
import pandas as pd

from judge_system.base_detector import BaseDetector, DetectorResult
from judge_system.judge_config import JudgeConfig


class MtfLiquiditySweepDetector(BaseDetector):
    """多时间框架流动性扫荡检测器"""

    def __init__(self):
        super().__init__(name="mtf_liquidity_sweep")
        self.cfg = JudgeConfig

    def detect(self, symbol: str, df: pd.DataFrame, **kwargs) -> DetectorResult:
        if df is None or len(df) < 100:
            return DetectorResult(
                detector_name=self.name,
                direction='neutral',
                score=0.0,
                confidence=0.0,
                detail='数据不足(需>=100根K线)'
            )

        close = df['close'].values
        high = df['high'].values
        low = df['low'].values

        # 使用K线数据模拟多时间框架
        # 日线数据 → 直接使用作为HTF
        # 15m/5m 数据 → 需要降采样模拟
        # 这里我们直接用数据本身作为LTF，用它的均线趋势作为HTF

        # HTF趋势判断: 使用较慢的均线 (模拟4H级别)
        ema50 = self._ema(close, 50)
        ema200 = self._ema(close, 200)

        # 最近数据点
        last = -1
        htf_bullish = False
        htf_bearish = False

        if not np.isnan(ema50[last]) and not np.isnan(ema200[last]):
            # HTF趋势: EMA50 > EMA200 = 看涨趋势
            if ema50[last] > ema200[last] and close[last] > ema50[last]:
                htf_bullish = True
            elif ema50[last] < ema200[last] and close[last] < ema50[last]:
                htf_bearish = True

        # HTF高低点 (近20根K线)
        lookback = 20
        htf_high = np.max(high[-lookback:]) if len(high) >= lookback else high[-1]
        htf_low = np.min(low[-lookback:]) if len(low) >= lookback else low[-1]

        # LTF突破检测 (最近几根K线)
        recent_high = np.max(high[-5:]) if len(high) >= 5 else high[-1]
        recent_low = np.min(low[-5:]) if len(low) >= 5 else low[-1]

        # 突破HTF高点 = 看涨信号
        breakout_high = recent_high > htf_high * 1.001  # 0.1% 突破确认
        # 跌破HTF低点 = 看空信号
        breakout_low = recent_low < htf_low * 0.999

        # 综合评分
        score = 0.0
        detail_parts = []

        if htf_bullish:
            detail_parts.append("HTF看涨(多头趋势)")
            score += 0.3
            if breakout_high:
                detail_parts.append("突破HTF高点✅")
                score += 0.4
            elif breakout_low:
                detail_parts.append("HTF看涨中但跌破低点⚠️")
                score -= 0.3
        elif htf_bearish:
            detail_parts.append("HTF看跌(空头趋势)")
            score -= 0.3
            if breakout_low:
                detail_parts.append("跌破HTF低点✅")
                score -= 0.4
            elif breakout_high:
                detail_parts.append("HTF看跌中但突破高点⚠️")
                score += 0.3
        else:
            detail_parts.append("HTF震荡(无明确趋势)")

        # 价格在HTF区间内的位置
        price_position = (close[last] - htf_low) / (htf_high - htf_low) if htf_high > htf_low else 0.5
        if price_position > 0.8:
            detail_parts.append("价格在HTF区间上沿")
            score -= 0.1  # 接近阻力
        elif price_position < 0.2:
            detail_parts.append("价格在HTF区间下沿")
            score += 0.1  # 接近支撑

        score = np.clip(score, -1.0, 1.0)
        direction = 'long' if score > 0.2 else ('short' if score < -0.2 else 'neutral')
        confidence = min(1.0, (abs(score) + 0.2) * (0.7 if (htf_bullish or htf_bearish) else 0.4))
        triggered = abs(score) > 0.35

        return DetectorResult(
            detector_name=self.name,
            direction=direction,
            score=score,
            confidence=confidence,
            triggered=triggered,
            detail=' | '.join(detail_parts),
            meta={
                'htf_bullish': htf_bullish,
                'htf_bearish': htf_bearish,
                'breakout_high': breakout_high,
                'breakout_low': breakout_low,
                'price_position': round(price_position, 3),
            }
        )
