"""
情绪震荡器检测器

从 FMZ 策略 "Sentiment Oscillator" 转换
PineScript → Python

核心逻辑:
  基于价格动量计算市场情绪:
  1. 计算价格动量 (短期收益率)
  2. 快EMA和慢EMA交叉 = 情绪转变信号
  3. 极端情绪值 → 可能反转

审判用途:
  检测锁妖塔推荐时的市场情绪状态
  - 极端看涨情绪 + 锁妖塔看多 = 一致性陷阱⚠️
  - 极端看跌情绪 + 锁妖塔看空 = 一致性陷阱⚠️
  - 情绪适中 + 锁妖塔有方向 = 健康信号✅
"""

import numpy as np
import pandas as pd

from judge_system.base_detector import BaseDetector, DetectorResult
from judge_system.judge_config import JudgeConfig


class SentimentOscillatorDetector(BaseDetector):
    """情绪震荡器检测器"""

    def __init__(self):
        super().__init__(name="sentiment_oscillator")
        self.cfg = JudgeConfig

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

        # 1. 计算情绪基础值：归一化的价格动量
        # 使用 lookback 周期的收益率作为原始情绪
        lookback = self.cfg.SENTIMENT_LOOKBACK
        returns = np.diff(close) / close[:-1]
        
        # 填充至原始长度
        raw_sentiment = np.full_like(close, np.nan)
        raw_sentiment[1:] = returns
        
        # 滚动均值平滑作为情绪线
        sentiment = np.full_like(close, np.nan)
        for i in range(lookback, len(close)):
            sentiment[i] = np.mean(raw_sentiment[i-lookback+1:i+1])
        
        # 处理NaN
        sentiment = np.nan_to_num(sentiment, nan=0.0)
        if np.all(sentiment == 0):
            return DetectorResult(
                detector_name=self.name,
                direction='neutral',
                score=0.0,
                confidence=0.0,
                detail='情绪数据异常'
            )

        # 2. 标准化情绪值到 [-1, 1]
        sent_std = np.std(sentiment[-lookback*2:]) if len(sentiment) > lookback*2 else np.std(sentiment)
        if sent_std > 0:
            sentiment_norm = sentiment / (sent_std * 3)  # 3σ 范围
        else:
            sentiment_norm = sentiment
        sentiment_norm = np.clip(sentiment_norm, -1.0, 1.0)

        # 3. 快慢EMA
        fast_ema = self._ema(sentiment_norm, self.cfg.SENTIMENT_FAST_EMA)
        slow_ema = self._ema(sentiment_norm, self.cfg.SENTIMENT_SLOW_EMA)
        
        # 信号线
        signal = self._ema(sentiment_norm, self.cfg.SENTIMENT_SIGNAL_LEN)

        # 4. 当前情绪值
        current_sentiment = sentiment_norm[-1]
        # 只有有足够数据时才使用EMA值, 否则设为None跳过EMA交叉检测
        slow_ema_valid = not np.isnan(slow_ema[-1]) if len(slow_ema) > 0 else False
        current_fast = fast_ema[-1] if not np.isnan(fast_ema[-1]) else 0
        current_slow = slow_ema[-1] if slow_ema_valid else 0
        current_signal = signal[-1] if not np.isnan(signal[-1]) else 0

        detail_parts = []
        score = 0.0

        # 情绪极端值检测
        if current_sentiment > self.cfg.SENTIMENT_OVERBOUGHT:
            detail_parts.append(f"极端看涨(情绪={current_sentiment:.2f})")
            score -= 0.4  # 极端看涨 = 回调风险
        elif current_sentiment < self.cfg.SENTIMENT_OVERSOLD:
            detail_parts.append(f"极端看跌(情绪={current_sentiment:.2f})")
            score += 0.4  # 极端看跌 = 反弹机会
        elif current_sentiment > 0.3:
            detail_parts.append(f"偏看涨(情绪={current_sentiment:.2f})")
            score -= 0.15
        elif current_sentiment < -0.3:
            detail_parts.append(f"偏看跌(情绪={current_sentiment:.2f})")
            score += 0.15
        else:
            detail_parts.append(f"情绪中性({current_sentiment:.2f})")

        # EMA交叉检测 (只有慢EMA有足够数据时才有效)
        if slow_ema_valid and not np.isnan(current_fast):
            if current_fast > current_slow and current_fast > 0:
                detail_parts.append("快EMA上穿慢EMA(情绪转暖)")
                score += 0.2
            elif current_fast < current_slow and current_fast < 0:
                detail_parts.append("快EMA下穿慢EMA(情绪转冷)")
                score -= 0.2

        # ★ MACD柱 (快-慢) + 信号线交叉 (FMZ原版核心信号)
        macd_line = fast_ema - slow_ema  # MACD线
        macd_hist = macd_line - signal   # 柱状图 = MACD - Signal
        current_macd = macd_line[-1] if not np.isnan(macd_line[-1]) else 0
        current_hist = macd_hist[-1] if not np.isnan(macd_hist[-1]) else 0
        prev_hist = macd_hist[-2] if len(macd_hist) >= 2 and not np.isnan(macd_hist[-2]) else 0

        # MACD与信号线交叉
        if slow_ema_valid:
            # MACD上穿Signal → 动能转多
            if current_macd > current_signal and macd_line[-2] <= signal[-2] if len(macd_line) >= 2 else False:
                detail_parts.append("MACD上穿信号线(动能转多)")
                score += 0.25
            # MACD下穿Signal → 动能转空
            elif current_macd < current_signal and macd_line[-2] >= signal[-2] if len(macd_line) >= 2 else False:
                detail_parts.append("MACD下穿信号线(动能转空)")
                score -= 0.25

        # 柱状图转正/转负
        if current_hist > 0 and prev_hist <= 0:
            detail_parts.append(f"动量柱转正({current_hist:.3f})")
            score += 0.15
        elif current_hist < 0 and prev_hist >= 0:
            detail_parts.append(f"动量柱转负({current_hist:.3f})")
            score -= 0.15

        # 情绪趋势
        sent_trend = sentiment_norm[-1] - sentiment_norm[-min(20, len(sentiment_norm))]
        if sent_trend > 0.2:
            detail_parts.append(f"情绪快速升温({sent_trend:.2f})")
            score -= 0.1  # 快速升温后容易回调
        elif sent_trend < -0.2:
            detail_parts.append(f"情绪快速降温({sent_trend:.2f})")
            score += 0.1  # 快速降温后容易反弹

        score = np.clip(score, -1.0, 1.0)
        direction = 'long' if score > 0.2 else ('short' if score < -0.2 else 'neutral')
        confidence = min(1.0, abs(current_sentiment) * 0.6 + 0.2)
        triggered = abs(score) > 0.3

        return DetectorResult(
            detector_name=self.name,
            direction=direction,
            score=score,
            confidence=confidence,
            triggered=triggered,
            detail=' | '.join(detail_parts),
            meta={
                'sentiment_value': round(float(current_sentiment), 4),
                'fast_ema': round(float(current_fast), 4),
                'slow_ema': round(float(current_slow), 4),
                'sentiment_trend': round(float(sent_trend), 4),
            }
        )
