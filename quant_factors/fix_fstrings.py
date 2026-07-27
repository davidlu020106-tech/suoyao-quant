"""Fix f-string escaping issues in run_5m_kol_consensus.py"""
import re

with open('quant_factors/run_5m_kol_consensus.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: progress print - replace the dict access inside f-string
old1 = "print(f'  [{i+1}/{len(altcoins)}] {base:<10s} score={r[\"score\"]:.1f} R1=+{r[\"r1_up\"]:.2f}% R2=+{r[\"r2_up\"]:.2f}% lev={r[\"max_lev\"]:.0f}x  KOL: L={r[\"kol_long\"]} S={r[\"kol_short\"]} N={r[\"kol_neutral\"]}')"
new1 = "            r_sc = r['score']; r_r1u = r['r1_up']; r_r2u = r['r2_up']\n            r_lv = r['max_lev']; r_l = r['kol_long']; r_s = r['kol_short']; r_n = r['kol_neutral']\n            print(f'  [{i+1}/{len(altcoins)}] {base:<10s} score={r_sc:.1f} R1=+{r_r1u:.2f}% R2=+{r_r2u:.2f}% lev={r_lv:.0f}x  KOL: L={r_l} S={r_s} N={r_n}')"
content = content.replace(old1, new1)

# Fix 2: header with escaped quotes
old2 = "hdr = f'{\"#\":>3} {\"币种\":<8} {\"入场价\":<14} {\"TP1(R1)\":<14} {\"TP2(R2)\":<14} {\"杠杆\":>6} {\"评分\":>4} {\"R1涨\":>6} {\"R2涨\":>6} {\"RSI\":>5} {\"KOL多\":>6} {\"KOL空\":>6} {\"KOL中\":>6}'"
new2 = "hdr = '# 币种      入场价           TP1(R1)          TP2(R2)          杠杆  评分  R1涨   R2涨  RSI  KOL多  KOL空  KOL中'"
content = content.replace(old2, new2)

# Fix 3: ranking loop
old3 = "print(f'  {i:3d} {r[\"base\"]:<8s} {es:<14s} {r1s:<14s} {r2s:<14s} {r[\"max_lev\"]:>5.0f}x {r[\"score\"]:>4.1f} {r[\"r1_up\"]:>+5.2f}% {r[\"r2_up\"]:>+5.2f}% {r[\"rsi\"]:>5.1f} {r[\"kol_long\"]:>5d}人 {r[\"kol_short\"]:>5d}人 {r[\"kol_neutral\"]:>5d}人')"
new3 = "        b = r['base']; sc = r['score']; r1u = r['r1_up']; r2u = r['r2_up']\n        rsi_v = r['rsi']; ml = r['max_lev']\n        kl = r['kol_long']; ks = r['kol_short']; kn = r['kol_neutral']\n        print(f'{i:3d} {b:<8s} {es:<14s} {r1s:<14s} {r2s:<14s} {ml:>5.0f}x {sc:>4.1f} {r1u:>+5.2f}% {r2u:>+5.2f}% {rsi_v:>5.1f} {kl:>5d}人 {ks:>5d}人 {kn:>5d}人')"
content = content.replace(old3, new3)

# Fix 4: TOP 3 details
old4 = "print(f'  {r[\"base\"]}')"
old4b = "print(f'  {\"-\"*50}')"
old4c = "print(f'    入场:  ${r[\"entry\"]:.4f}  |  评分: {r[\"score\"]}/10  |  RSI: {r[\"rsi\"]:.1f}')"
old4d = "print(f'    TP1:   ${r[\"r1\"]:.4f}  (+{r[\"r1_up\"]:.2f}%)  |  TP2:   ${r[\"r2\"]:.4f}  (+{r[\"r2_up\"]:.2f}%)')"
old4e = "print(f'    爆仓:  ${r[\"s2\"]:.4f}  (-{r[\"s2_down\"]:.2f}%)  |  杠杆:  {r[\"max_lev\"]:.0f}x')"
old4f = "print(f'    KOL:   看多{r[\"kol_long\"]}人 / 看空{r[\"kol_short\"]}人 / 中性{r[\"kol_neutral\"]}人  |  偏={r[\"kol_avg\"]:+.4f}')"
old4g = "print(f'    因子:  触发{r[\"firing_total\"]}个 (多{firing_long} 空{firing_short})')"

new4 = "print(f'  {b}')"
new4b = "print('  ' + '-'*50)"
new4c = "print(f'    入场:  ${ent:.4f}  |  评分: {sc}/10  |  RSI: {rsi_v:.1f}')"
new4d = "print(f'    TP1:   ${r1v:.4f}  (+{r1u:.2f}%)  |  TP2:   ${r2v:.4f}  (+{r2u:.2f}%)')"
new4e = "print(f'    爆仓:  ${s2v:.4f}  (-{s2d:.2f}%)  |  杠杆:  {ml:.0f}x')"
new4f = "print(f'    KOL:   看多{kl}人 / 看空{ks}人 / 中性{kn}人  |  偏={ka:+.4f}')"
new4g = "print(f'    因子:  触发{ft}个')"

content = content.replace(old4, new4)
content = content.replace(old4b, new4b)
content = content.replace(old4c, new4c)
content = content.replace(old4d, new4d)
content = content.replace(old4e, new4e)
content = content.replace(old4f, new4f)
content = content.replace(old4g, new4g)

with open('quant_factors/run_5m_kol_consensus.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('All fixes applied')
