#!/usr/bin/env python3
"""马丁格尔夜间选币系统 — 基于锁妖塔数据 + FMZ 20策略学习

流程:
  1. 锁妖塔全量扫描 → 获取每个币的88因子+99KOL投票
  2. 70分选币系统（从20个FMZ马丁格尔策略学到）
  3. 计算OKX马丁格尔机器人参数
  4. 输出今晚12点设置表

用法:
    python quant_factors/martingale_picks.py
    python quant_factors/martingale_picks.py --top 30
"""
import sys, os, json, time
from datetime import datetime

QF = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(QF)
sys.path.insert(0, QF)
sys.path.insert(0, BASE)

from run_daily_picks import analyze_coin, fetch_list, fetch_ohlc, CAP_REGISTRY, api_get
from okx_data_adapter import build_features_single
from capabilities import evaluate_all


def score_martingale(r):
    """70分选币系统 — 从20个FMZ策略学到
    
    每个维度10分，满分70分
    参考策略来源标注在括号中
    """
    score = 0
    reasons = []
    
    # ① 震荡度 (10分) ← 策略5:数学自适应网格
    adx = r.get('adx', 0)
    if adx < 20:
        score += 10
        reasons.append(f"震荡度=10分(ADX={adx}<25 来自数学自适应网格545765)")
    elif adx < 25:
        score += 5
        reasons.append(f"震荡度=5分(ADX={adx}<25 临界)")
    else:
        reasons.append(f"震荡度=0分(ADX={adx}≥25 趋势太强不适合马丁格尔)")
    
    # ② 位置安全 (10分) ← 策略6:动态移动网格540533
    kcp = r.get('kc_pos', 0.5)
    if 0.3 <= kcp <= 0.7:
        score += 10
        reasons.append(f"位置=10分(kc_pos={kcp:.2f} 通道中部)")
    elif 0.2 <= kcp <= 0.8:
        score += 5
        reasons.append(f"位置=5分(kc_pos={kcp:.2f} 偏离通道)")
    else:
        reasons.append(f"位置=0分(kc_pos={kcp:.2f} 通道极端 不适合)")
    
    # ③ 方向确认 (10分) ← 策略13:超级趋势629
    direction = r.get('direction', 'neutral')
    ltf_bias = r.get('ltf_bias', 'neutral')
    htf_bias = r.get('htf_bias', 'neutral')
    mtf_bias = r.get('mtf_bias', 'neutral')
    
    # 确保马丁格尔方向与至少一个时间框架一致
    biases = [b for b in [ltf_bias, mtf_bias, htf_bias] if b != 'neutral']
    if not biases:
        reasons.append(f"方向=0分(所有框架都中性)")
    elif all(b == direction for b in biases):
        score += 10
        reasons.append(f"方向=10分(三重框架与{direction}一致)")
    elif direction in biases:
        score += 5
        reasons.append(f"方向=5分(部分框架与{direction}一致)")
    else:
        reasons.append(f"方向=0分(无框架支持{direction})")
    
    # ④ KOL分歧度 (10分) ← 策略8:专业网格513759
    lt_l = r.get('ltf_long', 0)
    lt_s = r.get('ltf_short', 0)
    total = lt_l + lt_s
    if total > 0:
        ratio = max(lt_l, lt_s) / total
        if 0.5 <= ratio <= 0.7:
            score += 10
            reasons.append(f"KOL=10分(多空均衡 多{lt_l}/空{lt_s})")
        elif 0.7 < ratio <= 0.85:
            score += 5
            reasons.append(f"KOL=5分(分歧偏一边 多{lt_l}/空{lt_s})")
        else:
            reasons.append(f"KOL=0分(一边倒 多{lt_l}/空{lt_s} 不适合震荡)")
    else:
        reasons.append("KOL=0分(无KOL投票)")
    
    # ⑤ 价格水位 (10分) ← 策略3:智能定投521018
    entry = r.get('entry', 0)
    s1 = r.get('s1', entry * 0.95)
    r1 = r.get('r1', entry * 1.05)
    
    if s1 < entry < r1:
        # 做多：越接近S1越好
        if direction == 'long':
            dist_to_s1 = (entry - s1) / entry if entry > 0 else 0
            if dist_to_s1 < 0.05:
                score += 10
                reasons.append(f"水位=10分(靠近支撑S1={s1:.4f})")
            elif dist_to_s1 < 0.1:
                score += 5
                reasons.append(f"水位=5分(距支撑S1={dist_to_s1:.1%})")
            else:
                reasons.append(f"水位=0分(距支撑太远)")
        # 做空：越接近R1越好
        elif direction == 'short':
            dist_to_r1 = (r1 - entry) / entry if entry > 0 else 0
            if dist_to_r1 < 0.05:
                score += 10
                reasons.append(f"水位=10分(靠近阻力R1={r1:.4f})")
            elif dist_to_r1 < 0.1:
                score += 5
                reasons.append(f"水位=5分(距阻力R1={dist_to_r1:.1%})")
            else:
                reasons.append(f"水位=0分(距阻力太远)")
        else:
            reasons.append("水位=5分(方向中性 酌情)")
            score += 5
    else:
        reasons.append("水位=0分(价格超出支撑阻力范围)")
    
    # ⑥ 流动性 (10分) ← 策略4:永续平衡520273
    oi = r.get('open_interest', 0)
    if oi > 5000000:
        score += 10
        reasons.append(f"流动性=10分(OI={oi/1e6:.1f}M)")
    elif oi > 1000000:
        score += 5
        reasons.append(f"流动性=5分(OI={oi/1e6:.1f}M)")
    elif oi > 500000:
        score += 3
        reasons.append(f"流动性=3分(OI={oi/1e6:.1f}M)")
    else:
        reasons.append(f"流动性=0分(OI={oi/1e6:.1f}M 不足)")
    
    # ⑦ 波动稳定性 (10分) ← 策略1:暗度陈仓347955
    fr_abs = abs(r.get('funding_rate', 0))
    if fr_abs < 0.0001:
        score += 10
        reasons.append(f"费率=10分(fr={fr_abs:.6f} 稳定)")
    elif fr_abs < 0.0005:
        score += 5
        reasons.append(f"费率=5分(fr={fr_abs:.6f} 略高)")
    else:
        reasons.append(f"费率=0分(fr={fr_abs:.6f} 太高 不适合马丁格尔)")
    
    return score, reasons


def calc_martingale_params(r, total_balance=50):
    """计算OKX马丁格尔机器人参数 — 从20个策略学到
    
    策略来源:
    - 总账分配: 策略4(永续平衡520273)、策略18(平衡策略214943)
    - 仓位递减: 策略1(暗度陈仓347955)、策略2(飞轮量化542065)
    - 间距ATR: 策略5(数学自适应网格545765)、策略7(自动步进网格520975)
    - 止盈止损: 策略12(隔夜区间532865)、策略15(KOL蒸馏538802)
    - 挂单方式: 策略20(跨交易所做市521178)
    - 分批出场: 策略19(冰山委托521245)
    """
    entry = r.get('entry', 0)
    direction = r.get('direction', 'long')
    adx = r.get('adx', 15)
    okx_lev = r.get('okx_lev', 10)
    r1 = r.get('r1', entry * 1.02)
    s1 = r.get('s1', entry * 0.98)
    s2 = r.get('s2', entry * 0.95)
    
    # 从15m K线估算ATR (策略7: 自动步进网格)
    atr_pct = 0.01  # 默认1%
    cdl_15m = r.get('df_15m', [])
    if len(cdl_15m) >= 15:
        closes = [c['close'] for c in cdl_15m[-15:]]
        highs = [c['high'] for c in cdl_15m[-15:]]
        lows = [c['low'] for c in cdl_15m[-15:]]
        trs = []
        for i in range(1, len(closes)):
            tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
            trs.append(tr)
        atr = sum(trs) / len(trs) if trs else entry * 0.01
        atr_pct = atr / entry if entry > 0 else 0.01
    
    # ── 1. 总资金分配 (策略4、策略18) ──
    # 50U总资金，50%保证金(25U)，50%备用金(25U)
    margin_total = total_balance * 0.50  # 25U
    
    # ── 2. 确定安全杠杆 (策略15: KOL蒸馏) ──
    # 安全杠杆 = min(OKX最大杠杆, 2x)
    safe_lev = min(okx_lev, 2)
    
    # ── 3. 仓位递减分配 (策略1、策略2) ──
    # 4层: 40% 25% 20% 15%
    layer_pcts = [0.40, 0.25, 0.20, 0.15]
    layer_margins = [margin_total * p for p in layer_pcts]
    
    # ── 4. 加仓间距 (策略5、策略7) ──
    # 间距 = ATR × 2（波动大间距大）
    # 对低价币(<$1) ATR可能极小, 需要保底
    add_distance_pct = max(atr_pct * 2, 0.005)  # 至少0.5%
    # 如果ADX较高(趋势较强)，间距要放宽
    if adx > 20:
        add_distance_pct *= 1.5
    # 高价币(>$10)波动大, 间距要收窄
    if entry > 10:
        add_distance_pct = min(add_distance_pct, 0.015)
    else:
        add_distance_pct = min(add_distance_pct, 0.05)  # 低价币最多5%
    
    # ── 5. 止盈目标 (策略12: 隔夜区间) ──
    # 做多止盈 = min((R1/entry-1), 3%)
    # 做空止盈 = min((1-S2/entry), 3%)
    if direction == 'long':
        tp_pct = min((r1 / entry - 1) if entry > 0 else 0.02, 0.03)
    else:
        tp_pct = min((1 - s2 / entry) if entry > 0 else 0.02, 0.03)
    tp_pct = max(tp_pct, 0.008)  # 至少0.8%
    
    # ── 6. 止损 (策略12、策略15) ──
    if direction == 'long':
        sl_pct = min((entry - s1) / entry if entry > 0 else 0.02, 0.05)
    else:
        sl_pct = min((s2 - entry) / entry if entry > 0 else 0.02, 0.05)
    sl_pct = max(sl_pct, 0.015)  # 至少1.5%
    
    # ── 7. 计算每层U数 ──
    # OKX马丁格尔的参数:
    # 初次下单保证金 = 第一层U数
    # 加仓单保证金 = 后续每层U数
    # 注意: OKX的"加仓单保证金"是所有加仓共用一个值
    # 但我们可以设为一个平均值
    
    # 初次下单保证金 (U)
    init_margin = layer_margins[0] if len(layer_margins) > 0 else 10
    
    # 加仓单保证金 = 后续几层的平均值
    add_margins = layer_margins[1:] if len(layer_margins) > 1 else [10]
    add_margin = sum(add_margins) / len(add_margins)
    
    # 加仓金额倍数 = 递减(但OKX只支持>1)
    # 策略1说1.5-1.8倍，但我们是递减分配
    # 转为等效的固定倍数: 平均后层/前层
    if len(layer_margins) >= 2:
        avg_multi = add_margin / init_margin if init_margin > 0 else 1.0
        add_amt_multi = max(avg_multi, 1.0)  # OKX需要≥1
    else:
        add_amt_multi = 1.1
    
    # 加仓价差倍数 = 固定1倍(各层间距相同)
    add_spacing_multi = 1.0
    
    # 最大加仓次数 = 层数-1
    max_add = len(layer_pcts) - 1
    
    return {
        'direction': direction,
        'entry_price': entry,
        'total_balance': total_balance,
        'margin_total': round(margin_total, 2),
        'safe_leverage': safe_lev,
        # OKX马丁格尔参数
        'init_margin': round(init_margin, 2),
        'add_margin': round(add_margin, 2),
        'add_trigger_pct': round(add_distance_pct * 100, 1),  # 跌多少%加仓
        'tp_pct': round(tp_pct * 100, 1),  # 止盈%
        'sl_pct': round(sl_pct * 100, 1),  # 止损%
        'max_add_count': max_add,  # 最大加仓次数
        'add_amt_multi': round(add_amt_multi, 2),  # 加仓金额倍数
        'add_spacing_multi': round(add_spacing_multi, 2),  # 加仓价差倍数
        # 详细层信息
        'layers': [
            {
                'layer': i + 1,
                'type': '首次' if i == 0 else '加仓',
                'margin_usdt': round(m, 2),
                'price_if_down': round(entry * (1 - add_distance_pct * i), 4) if direction == 'long' else round(entry * (1 + add_distance_pct * i), 4)
            }
            for i, m in enumerate(layer_margins)
        ]
    }


def run(top_n=30, total_balance=50):
    """主函数"""
    print()
    print('  ╔══════════════════════════════════════╗')
    print('  ║   马丁格尔夜间选币系统 v1.0           ║')
    print(f'  ║   {datetime.now().strftime("%Y-%m-%d %H:%M")}            ║')
    print('  ╚══════════════════════════════════════╝')
    print()
    print('  数据源: 锁妖塔量化系统')
    print(f'  策略参考: 20个FMZ马丁格尔/网格策略')
    print(f'  评分系统: 70分制 (7维度×10分)')
    print(f'  总资金: {total_balance}U | 保证金预算: {total_balance*0.5:.0f}U')
    print()
    
    # ── 1. 获取币种列表 ──
    coins_list = fetch_list(top_n)
    print(f'  扫描币种: {len(coins_list)}个')
    print()
    
    # ── 2. 加载KOL配置 ──
    reg = CAP_REGISTRY
    rids = set(reg.keys())
    profs = {}
    pd_ = os.path.join(BASE, 'profiles_v2')
    for f in sorted(os.listdir(pd_)):
        if f.endswith('.json'):
            try:
                p = json.load(open(os.path.join(pd_, f), encoding='utf-8'))
                profs[f.replace('.json', '')] = p
            except Exception:
                pass
    
    # 预取杠杆
    lev_map = {}
    try:
        inst = api_get('/api/v5/public/instruments?instType=SWAP')
        if inst.get('code') == '0':
            for d in inst.get('data', []):
                di = d['instId']
                if di.endswith('-USDT-SWAP'):
                    base_n = di.replace('-USDT-SWAP', '')
                    lev_map[base_n] = int(d.get('lever', 20))
    except Exception:
        pass
    
    # ── 3. 扫描每个币 ──
    candidates = []
    for i, coin in enumerate(coins_list):
        base = coin['base']
        print(f'  [{i+1}/{len(coins_list)}] {base}...', end=' ')
        
        # 用宽松参数过锁妖塔(为了拿到数据)
        r = analyze_coin(base, reg, rids, profs, 
                         min_r1=0.5, min_oi=50000, 
                         lev_map=lev_map, kol_weights=None)
        if r is None:
            print('跳过')
            continue
        
        # 70分评分
        score, reasons = score_martingale(r)
        
        # 过滤: 总分<30的直接排除
        if score < 30:
            print(f'{score}分 排除')
            continue
        
        # 计算马丁格尔参数
        params = calc_martingale_params(r, total_balance)
        
        candidates.append({
            'base': base,
            'score': score,
            'direction': r['direction'],
            'entry': r['entry'],
            'adx': r['adx'],
            'rsi': r['rsi'],
            'params': params,
            'reasons': reasons,
            'raw': r
        })
        
        print(f'{score}分 ✅')
        time.sleep(0.05)
    
    # ── 4. 按分数排序 ──
    candidates.sort(key=lambda x: x['score'], reverse=True)
    
    # ── 5. 输出 ──
    print()
    print('  ' + '=' * 90)
    print(f'  ★ 马丁格尔今晚推荐 {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    print(f'  推荐策略: 分数≥50=重仓做 | 40-49=轻仓做 | <40=不做')
    print('  ' + '=' * 90)
    print()
    
    if not candidates:
        print('  ❌ 今晚没有合适的币做马丁格尔')
        print('  原因: 所有币都不满足安全条件')
        print()
        return
    
    # 显示排名
    print(f'  {"排名":>3s} {"币种":<6s} {"方向":>3s} {"评分":>5s} {"ADX":>5s} {"入场价":>10s} {"建议":>12s}')
    print(f'  {"-"*50}')
    
    for i, c in enumerate(candidates[:10], 1):
        dir_str = '🟢多' if c['direction'] == 'long' else '🔴空'
        advice = '✅ 重仓做' if c['score'] >= 50 else ('⚠️ 轻仓做' if c['score'] >= 40 else '❌ 不做')
        # 极低价币显示更多小数位
        if c['entry'] < 0.001:
            price_str = f'${c["entry"]:.8f}'
        elif c['entry'] < 1:
            price_str = f'${c["entry"]:.6f}'
        elif c['entry'] < 100:
            price_str = f'${c["entry"]:.4f}'
        else:
            price_str = f'${c["entry"]:.2f}'
        print(f'  {i:>3d} {c["base"]:<6s} {dir_str:>3s} {c["score"]:>3d}/70 {c["adx"]:>4.1f}  {price_str:>12s} {advice:>12s}')
    
    print()
    
    # ── 6. 输出TOP3的详细参数 ──
    top_n = min(3, len(candidates))
    for rank in range(top_n):
        c = candidates[rank]
        if c['score'] < 40:
            continue  # 分数太低不输出参数
            
        print(f'  {"="*90}')
        print(f'  ★ 推荐 #{rank+1}: {c["base"]} (评分 {c["score"]}/70)')
        print(f'  {"="*90}')
        print(f'  方向: {"🟢做多" if c["direction"]=="long" else "🔴做空"}')
        print(f'  当前价: ${c["entry"]:.4f}' if c['entry'] < 100 else f'  当前价: ${c["entry"]:.2f}')
        print(f'  ADX: {c["adx"]:.1f} | RSI: {c["rsi"]:.0f}')
        print()
        
        p = c['params']
        
        print(f'  ┌── OKX马丁格尔机器人参数 ──────────────────┐')
        print(f'  │  交易对: {c["base"]}-USDT-SWAP                 │')
        print(f'  │  方向: {"做多" if p["direction"]=="long" else "做空"}                               │')
        print(f'  │  杠杆: {p["safe_leverage"]}x                                   │')
        print(f'  │                                             │')
        print(f'  │  首次下单保证金: ≥ {p["init_margin"]:>5.2f} USDT              │')
        print(f'  │  加仓单保证金:   ≥ {p["add_margin"]:>5.2f} USDT              │')
        print(f'  │  跌多少加仓:     {p["add_trigger_pct"]:>5.1f} %')
        print(f'  │  单周期止盈目标: {p["tp_pct"]:>5.1f} %')
        print(f'  │  止损目标:       {p["sl_pct"]:>5.1f} %')
        print(f'  │  最大加仓次数:   {p["max_add_count"]:>5d} 次')
        print(f'  │  加仓金额倍数:   {p["add_amt_multi"]:>5.2f} 倍')
        print(f'  │  加仓价差倍数:   {p["add_spacing_multi"]:>5.2f} 倍')
        print(f'  └─────────────────────────────────────────────┘')
        print()
        
        # 详细层展示
        print(f'  ┌── 层层分解 ────────────────────────────────┐')
        for layer in p['layers']:
            mark = '(当前价)' if layer['layer'] == 1 else f'(跌{p["add_trigger_pct"]:.1f}%触发)'
            price_dir = '↓' if c['direction'] == 'long' else '↑'
            print(f'  │  第{layer["layer"]}层({layer["type"]}) | {layer["margin_usdt"]:>5.2f}U | '
                  f'触发价{price_dir}${layer["price_if_down"]:<8.4f} {mark}')
        print(f'  └─────────────────────────────────────────────┘')
        print()
        
        # 评分明细
        print(f'  ┌── 70分评分明细 ────────────────────────────┐')
        for reason in c['reasons'][:7]:
            print(f'  │  {reason[:60]}')
        print(f'  └─────────────────────────────────────────────┘')
        print()
    
    # ── 7. 总结 ──
    print()
    print(f'  {"="*50}')
    print(f'  今晚操作建议:')
    qualified = [c for c in candidates if c['score'] >= 40]
    if qualified:
        print(f'  ✅ 做 {len(qualified[:3])} 个币的马丁格尔')
        print(f'  ⏰ 00:00 前在OKX设置好')
        print(f'  ⏰ 08:00 检查成交情况')
        for c in qualified[:3]:
            p = c['params']
            print(f'     {c["base"]} | {p["init_margin"]}U首仓 | 跌{p["add_trigger_pct"]}%加 | 涨{p["tp_pct"]}%止盈')
    else:
        print(f'  ❌ 今晚没有合适的币')
        print(f'  建议: 休息，或者手动做趋势交易')
    print(f'  {"="*50}')
    print()


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--top', type=int, default=30)
    p.add_argument('--balance', type=float, default=50)
    a = p.parse_args()
    run(top_n=a.top, total_balance=a.balance)
