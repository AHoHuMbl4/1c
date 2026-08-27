# Замер K6-мера v2 на okna, 2026-08-27 (today=2026-08-27).
# Снято: python3 work/k6-rank-v2/bench.py на gpu-erw / SereneDB :7890.
# Полный построчный вывод — bench.out (копия с хоста); JSON-дампы ниже — сводка.

## gold-23 (ab-gold-okna.tsv)

| | lead | top3 | top8 | out8 (>8) | miss |
|---|---:|---:|---:|---:|---:|
| v0 alias+expand | 2 | 3 | 4 | 19 | 0 |
| v1 answer_fit | 0 | 1 | 4 | 19 | 0 |
| **v2 live+kind** | **18** | **18** | **21** | **2** | **0** |

GATE: lead≥12 → **PASS** (18); v1 top3 regress → **0** (PASS).

Контроль K6:
- «сколько клиентов реально покупают?» place v0/v1/v2 = 51→51→9 (вне топ-8; kind=физические)
- «сколько у нас всего клиентов?» 1→4→4 (v1/v2 ломают alias-лидера; kind=физические)
- «сколько позиций у нас в прайсе?» 33→33→7 (в топ-8)

Провалы v2 lead (5): Q13 complement позиций; Q18 клиентов; Q19 прайс; Q20 покупают; Q23 документов.

## positions-5 (questions_positions.tsv)

| | lead | top3 | top8 | out8 | miss |
|---|---:|---:|---:|---:|---:|
| v0 | 0 | 0 | 1 | 4 | 0 |
| v1 | 0 | 0 | 0 | 5 | 0 |
| v2 | 0 | 0 | 4 | 1 | 0 |

Источник 5 «позиций»: §8 ACCEPTANCE_AMBIGUOUS таких формулировок нет;
набор = gold + ACCEPTANCE_OKNA_LIVE §B5 + ACCEPTANCE_UT.
