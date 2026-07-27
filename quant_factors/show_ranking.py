#!/usr/bin/env python3
"""综合排名 — 一键输出多空合并排名"""
import json, os, sys

QF = os.path.dirname(os.path.abspath(__file__))
path = os.path.join(QF, 'altcoin_5m_kol_ranking.json')
if not os.path.exists(path):
    print('先跑一次全量扫描: python run_5m_kol_consensus.py --top 86')
    sys.exit(1)

with open(path) as f:
    data = json.load(f)

def fmt_px(p):
    if p > 10: return '$' + format(p, '.2f')
    elif p > 1: return '$' + format(p, '.4f')
    elif p > 0.01: return '$' + format(p, '.4f')
    else: return '$' + format(p, '.6f')

# 综合信号 = kol_avg(偏度) × 30 + 多空评分差 × 0.3
for r in data:
    r['signal'] = r['kol_avg'] * 30 + (r['score'] - r['score_short']) * 0.3

data.sort(key=lambda r: r['signal'])

W = 120
print('=' * W)
print('  锁妖塔综合排名 (按信号从空到多排列)')
print('=' * W)
h = '{:>3s} {:<7s} {:>4s} {:>8s} {:>7s} {:>8s} {:>10s} {:>10s} {:>10s} {:>5s} {:>5s} {:>6s}'
print(h.format('#', '币种', '方向', 'KOL', '信号', '评分差', '入场价', '费率%', 'OI', 'ADX', 'RSI', '建议'))
print('-' * W)

for i, r in enumerate(data, 1):
    sig = r['signal']
    if sig < -0.5: direction = '空'
    elif sig > 0.5: direction = '多'
    else: direction = '-'
    kl = r['kol_long']; ks = r['kol_short']
    sc = r['score']; sc_s = r['score_short']
    sc_diff = sc - sc_s
    fr = r.get('funding_rate', 0) * 100
    oi = r.get('open_interest', 0)
    adx = r.get('adx', 0)
    rsi = r['rsi']
    
    if direction == '空' and ks > 60 and rsi < 60 and sc_s >= 3.0:
        act = 'SHORT'
    elif direction == '多' and kl > 50 and rsi > 40 and sc >= 3.0:
        act = 'LONG'
    else:
        act = 'WATCH'
    
    ent = r['entry']
    line = '{:3d} {:<7s} {:>4s} {:>3d}/{:<3d} {:>7.2f} {:>+7.2f} {:>10s} {:>+9.4f}% {:>10.0f} {:>5.1f} {:>5.1f} {:>6s}'
    print(line.format(i, r['base'], direction, kl, ks, sig, sc_diff, fmt_px(ent), fr, oi, adx, rsi, act))

print('-' * W)
strong_short = sum(1 for r in data if r['signal'] < -0.5)
strong_long = sum(1 for r in data if r['signal'] > 0.5)
print('共 {} 币种 | 偏空 {} 偏多 {} 中性 {} | 信号分正=看多 负=看空'.format(
    len(data), strong_short, strong_long, len(data) - strong_short - strong_long))
