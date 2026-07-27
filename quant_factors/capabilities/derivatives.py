"""Derivatives signal capabilities (7 caps).

Live OKX data support: funding_rate + open_interest columns.
Plug into any DataFrame with those columns to get real signals.
"""
import numpy as np
import pandas as pd
from .registry import register, CapabilityOutput


@register('cap_031_funding_extreme_neg', 'derivatives_signal', 'long', 0.65)
def funding_neg(f):
    """Extremely negative funding rate → short squeeze risk, bullish."""
    fr = f.get('funding_rate', pd.Series(0, index=f.index))
    trig = fr < -0.0005  # < -0.05%
    score = np.where(trig, np.clip(-fr * 600, 0.3, 0.8), 0.0)
    return CapabilityOutput(triggered=trig, score=score, bias='long', confidence=0.65)


@register('cap_032_funding_extreme_pos', 'derivatives_signal', 'short', 0.6)
def funding_pos(f):
    """Extremely positive funding rate → long crowded, bearish."""
    fr = f.get('funding_rate', pd.Series(0, index=f.index))
    trig = fr > 0.0005  # > 0.05%
    score = np.where(trig, np.clip(fr * 600, 0.3, 0.8), 0.0)
    return CapabilityOutput(triggered=trig, score=score, bias='short', confidence=0.6)


@register('cap_033_oi_climb', 'derivatives_signal', 'neutral', 0.5)
def oi_climb(f):
    """Open interest level — high OI = active market, trend confirmation."""
    oi = f.get('open_interest', pd.Series(0, index=f.index))
    trig = oi > 10_000_000
    score = np.where(oi > 50_000_000, 0.4,
                     np.where(oi > 10_000_000, 0.25,
                              np.where(oi > 1_000_000, 0.1, 0.0)))
    return CapabilityOutput(triggered=trig, score=score, bias='neutral', confidence=0.5)


@register('cap_034_liquidation_cluster', 'derivatives_signal', 'neutral', 0.55, impl='mock', na_reason='need liquidation heatmap API')
def liq_cluster(f):
    """Liquidation clusters — still requires external heatmap data."""
    n = len(f) if hasattr(f, '__len__') else 1
    return CapabilityOutput(triggered=np.zeros(n, bool), score=np.zeros(n), bias='neutral', confidence=0.0)


@register('cap_059_funding_divergence', 'derivatives_signal', 'long', 0.55)
def funding_div(f):
    """Funding-price divergence: price down but funding positive → bullish;
    price up but funding negative → bearish."""
    fr = f.get('funding_rate', pd.Series(0, index=f.index))
    rsi = f.get('rsi14', pd.Series(50, index=f.index))
    trig = ((fr > 0.0005) & (rsi < 40)) | ((fr < -0.0005) & (rsi > 60))
    score = np.where((fr > 0.0005) & (rsi < 40), 0.5,
                     np.where((fr < -0.0005) & (rsi > 60), -0.5, 0.0))
    return CapabilityOutput(triggered=trig, score=score, bias='long', confidence=0.55)


@register('cap_060_basis_blowout', 'derivatives_signal', 'short', 0.55, impl='mock', na_reason='need futures mark price')
def basis_blowout(f):
    """Basis blowout — requires futures mark price vs spot price."""
    n = len(f) if hasattr(f, '__len__') else 1
    return CapabilityOutput(triggered=np.zeros(n, bool), score=np.zeros(n), bias='short', confidence=0.0)


@register('cap_061_options_skew', 'derivatives_signal', 'long', 0.5, impl='mock', na_reason='need options chain')
def options_skew(f):
    """Options skew — requires options chain data from OKX."""
    n = len(f) if hasattr(f, '__len__') else 1
    return CapabilityOutput(triggered=np.zeros(n, bool), score=np.zeros(n), bias='long', confidence=0.0)
