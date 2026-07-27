#!/usr/bin/env python3
"""Render interactive Plotly HTML: BTC candles + consensus box + trader lines."""
import os, json
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

BASE = os.path.expanduser('~/shared/materials/crypto_traders_distill')

# Load data
features = pd.read_parquet(f'{BASE}/quant_factors/features.parquet')
factors = pd.read_parquet(f'{BASE}/quant_factors/factors.parquet')
signals = pd.read_parquet(f'{BASE}/quant_factors/trader_signals_btc.parquet')
ic_df = pd.read_csv(f'{BASE}/quant_factors/trader_composite_ic.csv').set_index('handle')
snap = json.load(open(f'{BASE}/quant_factors/consensus_snapshot.json'))

btc_feats = features.loc['BTCUSDT'].sort_index()
btc_factors = factors[factors['symbol'] == 'BTCUSDT'].sort_index()

# Show last 240 days + project 30 days of consensus
lookback_days = 240
proj_days = 30
cutoff = btc_feats.index[-1] - pd.Timedelta(days=lookback_days)
view = btc_feats[btc_feats.index >= cutoff].copy()

latest_date = btc_feats.index[-1]
latest_close = float(btc_feats.iloc[-1]['close'])
proj_end = latest_date + pd.Timedelta(days=proj_days)

# ============================================================
# Compute consensus bands from firing factors
# ============================================================
firing_factors = snap['firing_factors']
firing_dir = {}
for f in firing_factors:
    firing_dir[f['id']] = f['score']

# For each firing factor, look up historical fwd_30d distribution and compute implied price box
factor_cols = [c for c in btc_factors.columns if c.startswith('cap_') or c.startswith('emg_')]
consensus_boxes = []
for cid, score in firing_dir.items():
    if cid not in factor_cols: continue
    direction = 'long' if score > 0 else 'short'
    # rows where factor had same sign
    matching = btc_factors[btc_factors[cid] * score > 0]
    fwds = matching['fwd_30d'].dropna()
    if len(fwds) < 5: continue
    p25 = fwds.quantile(0.25)
    p50 = fwds.quantile(0.5)
    p75 = fwds.quantile(0.75)
    hit = ((fwds > 0) if direction == 'long' else (fwds < 0)).mean()
    consensus_boxes.append({
        'cap_id': cid,
        'direction': direction,
        'score': score,
        'implied_low': latest_close * (1 + p25),
        'implied_mid': latest_close * (1 + p50),
        'implied_high': latest_close * (1 + p75),
        'hit_rate': float(hit),
        'n_hist': len(fwds),
    })

# Pool all factor boxes by direction, weight by (hit_rate * n_hist)
long_boxes = [b for b in consensus_boxes if b['direction'] == 'long']
short_boxes = [b for b in consensus_boxes if b['direction'] == 'short']

def pool_box(boxes):
    if not boxes: return None
    weights = np.array([b['hit_rate'] * np.log1p(b['n_hist']) for b in boxes])
    weights = np.where(weights <= 0, 0.01, weights)
    w = weights / weights.sum()
    return {
        'lo': float(np.average([b['implied_low'] for b in boxes], weights=w)),
        'mid': float(np.average([b['implied_mid'] for b in boxes], weights=w)),
        'hi': float(np.average([b['implied_high'] for b in boxes], weights=w)),
        'n': len(boxes),
    }

long_pool = pool_box(long_boxes)
short_pool = pool_box(short_boxes)

print(f'Long pool:  {long_pool}')
print(f'Short pool: {short_pool}')

# ============================================================
# Build figure
# ============================================================
fig = make_subplots(
    rows=2, cols=1,
    shared_xaxes=True,
    row_heights=[0.72, 0.28],
    vertical_spacing=0.04,
    subplot_titles=(f'BTC/USD · 共识 box （2026-04-11 @ ${latest_close:,.0f}）', '90 交易员 composite 信号 (IC ≥ +0.05)'),
)

# 1. Candlestick
fig.add_trace(
    go.Candlestick(
        x=view.index,
        open=view['open'], high=view['high'], low=view['low'], close=view['close'],
        name='BTC', increasing_line_color='#26a69a', decreasing_line_color='#ef5350',
        showlegend=False,
    ),
    row=1, col=1,
)

# 2. Moving averages
for ma_col, color, w in [('ma50','#ffb74d', 1.2), ('ma200','#e57373', 1.4)]:
    fig.add_trace(
        go.Scatter(x=view.index, y=view[ma_col], mode='lines', name=ma_col.upper(),
                   line=dict(color=color, width=w), showlegend=True),
        row=1, col=1,
    )

# 3. Consensus boxes (rectangles projected forward)
proj_x = [latest_date, proj_end, proj_end, latest_date, latest_date]

if short_pool:
    fig.add_trace(
        go.Scatter(
            x=proj_x,
            y=[short_pool['lo'], short_pool['lo'], short_pool['hi'], short_pool['hi'], short_pool['lo']],
            fill='toself', fillcolor='rgba(239,83,80,0.16)',
            line=dict(color='rgba(239,83,80,0.5)', width=1),
            name=f'看空共识 box ({short_pool["n"]} 因子)',
            hovertext=f'空头共识 ${short_pool["lo"]:,.0f} ~ ${short_pool["hi"]:,.0f}<br>中枢 ${short_pool["mid"]:,.0f}',
            hoverinfo='text',
        ),
        row=1, col=1,
    )
    # Midline
    fig.add_trace(
        go.Scatter(
            x=[latest_date, proj_end],
            y=[short_pool['mid']]*2,
            mode='lines',
            line=dict(color='rgba(239,83,80,0.7)', width=2, dash='dash'),
            name=f'空头中枢 ${short_pool["mid"]:,.0f}',
            showlegend=False,
        ),
        row=1, col=1,
    )

if long_pool:
    fig.add_trace(
        go.Scatter(
            x=proj_x,
            y=[long_pool['lo'], long_pool['lo'], long_pool['hi'], long_pool['hi'], long_pool['lo']],
            fill='toself', fillcolor='rgba(38,166,154,0.14)',
            line=dict(color='rgba(38,166,154,0.5)', width=1),
            name=f'看多共识 box ({long_pool["n"]} 因子)',
            hovertext=f'多头共识 ${long_pool["lo"]:,.0f} ~ ${long_pool["hi"]:,.0f}<br>中枢 ${long_pool["mid"]:,.0f}',
            hoverinfo='text',
        ),
        row=1, col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=[latest_date, proj_end],
            y=[long_pool['mid']]*2,
            mode='lines',
            line=dict(color='rgba(38,166,154,0.7)', width=2, dash='dash'),
            name=f'多头中枢 ${long_pool["mid"]:,.0f}',
            showlegend=False,
        ),
        row=1, col=1,
    )

# 4. Current price marker (horizontal line from today)
fig.add_trace(
    go.Scatter(
        x=[latest_date, proj_end],
        y=[latest_close, latest_close],
        mode='lines',
        line=dict(color='#ffffff', width=1.5, dash='dot'),
        name=f'当前 ${latest_close:,.0f}',
    ),
    row=1, col=1,
)

# 5. Bottom subplot: composite signals for top IC traders
top_traders = ic_df[ic_df['ic_30d'] > 0.05].sort_values('ic_30d', ascending=False).head(15).index.tolist()
school_colors = {
    'cycle': '#ffa726',
    'mixed': '#64b5f6',
    'pure_TA': '#ba68c8',
    'structural': '#4db6ac',
    'macro': '#90a4ae',
    'content_creator': '#f48fb1',
    'derivatives': '#81c784',
    'onchain': '#fff176',
    'contrarian': '#e57373',
}

for h in top_traders:
    if h not in signals.columns: continue
    sig_series = signals[h].loc[signals.index >= cutoff]
    school = ic_df.loc[h, 'school']
    color = school_colors.get(school, '#bdbdbd')
    ic_val = ic_df.loc[h, 'ic_30d']
    fig.add_trace(
        go.Scatter(
            x=sig_series.index, y=sig_series.values,
            mode='lines', name=f'{h} IC={ic_val:+.2f}',
            line=dict(color=color, width=1.3),
            opacity=0.85,
            hovertemplate=f'<b>{h}</b><br>%{{x|%Y-%m-%d}}: %{{y:.3f}}<extra></extra>',
        ),
        row=2, col=1,
    )

# Zero line on bottom
fig.add_hline(y=0, line_dash='dot', line_color='rgba(255,255,255,0.3)', row=2, col=1)

# Mean signal line
mean_sig = signals[top_traders].loc[signals.index >= cutoff].mean(axis=1)
fig.add_trace(
    go.Scatter(x=mean_sig.index, y=mean_sig.values, mode='lines', name='Top 15 均值',
               line=dict(color='#ffffff', width=2.5), opacity=0.95),
    row=2, col=1,
)

# Layout
fig.update_layout(
    template='plotly_dark',
    title=dict(
        text=f"<b>90 交易员共识预言机 · BTC/USD</b> &nbsp;·&nbsp; <span style='font-size:14px;color:#9ca3af'>量化因子合成 · {latest_date.date()}</span>",
        x=0.02, xanchor='left',
    ),
    height=860,
    xaxis_rangeslider_visible=False,
    legend=dict(orientation='v', yanchor='top', y=0.98, xanchor='left', x=1.02,
                bgcolor='rgba(0,0,0,0.3)', font=dict(size=10)),
    margin=dict(l=60, r=220, t=90, b=60),
    hovermode='x unified',
)
fig.update_yaxes(title_text='BTC Price (USD)', row=1, col=1)
fig.update_yaxes(title_text='Composite Signal', row=2, col=1, range=[-0.2, 0.2])
fig.update_xaxes(showgrid=True, gridcolor='rgba(255,255,255,0.08)')

# Big BULL/BEAR verdict banner
bias_val = snap['consensus']['trust_adjusted']
if bias_val < -0.01:
    verdict = 'BEARISH'
    verdict_color = '#ef5350'
    verdict_emoji = '🔴'
elif bias_val > 0.01:
    verdict = 'BULLISH'
    verdict_color = '#26a69a'
    verdict_emoji = '🟢'
else:
    verdict = 'NEUTRAL'
    verdict_color = '#9ca3af'
    verdict_emoji = '⚪'

eq = snap['consensus']['equal_weight']
fig.add_annotation(
    xref='paper', yref='paper', x=0.5, y=1.12,
    text=(
        f"<span style='font-size:28px;color:{verdict_color};font-weight:bold'>{verdict_emoji} {verdict}</span>"
        f"&nbsp;&nbsp;<span style='font-size:16px;color:#9ca3af'>Trust-adjusted: {bias_val:+.3f}</span>"
        f"<br><span style='font-size:13px;color:#d1d5db'>99 Traders: Long {eq['long']} · Short {eq['short']} · Neutral {eq['neutral']}</span>"
    ),
    showarrow=False, font=dict(size=14), align='center',
)

# Stats panel (left side)
schools = snap.get('by_school', {})
school_lines = []
for s, d in sorted(schools.items(), key=lambda x: x[1].get('mean_signal', 0)):
    if d['count'] < 3: continue
    ms = d['mean_signal']
    arrow = '🔴' if ms < -0.02 else '🟢' if ms > 0.02 else '⚪'
    school_lines.append(f"{arrow} {s}: {d['count']}人 avg={ms:+.3f}")

firing_lines = []
for ff in snap['firing_factors']:
    d = '🔴' if ff['score'] < 0 else '🟢'
    name = ff['id'].replace('cap_','').replace('emg_','')[:25]
    firing_lines.append(f"{d} {name} {ff['score']:+.2f}")

annotation_text = (
    f"<b>触发因子 ({len(snap['firing_factors'])})</b><br>"
    + '<br>'.join(firing_lines[:8])
    + f"<br><br><b>流派共识</b><br>"
    + '<br>'.join(school_lines[:6])
)
fig.add_annotation(
    xref='paper', yref='paper', x=0.01, y=0.65,
    text=annotation_text, showarrow=False,
    font=dict(size=10, color='#e5e7eb'),
    align='left', bgcolor='rgba(0,0,0,0.6)', bordercolor='rgba(255,255,255,0.15)',
    borderwidth=1, borderpad=8,
)

# Save
out_html = f'{BASE}/quant_factors/consensus_snapshot.html'
fig.write_html(out_html, include_plotlyjs='cdn')
print(f'\nsaved {out_html}')
print(f'file size: {os.path.getsize(out_html)//1024} KB')
