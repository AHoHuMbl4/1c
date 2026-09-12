# V4: пакет правки замков к flip

Срез: 12.09. Только замки `ubuntu/serenedb/test_*.py` из списка задачи.
Код зон/тракта/`_bootstrap` не трогался. git-мутаций нет.

Прогон финала: `timeout 120 python3 test_X.py` по всем правленным — **все EXIT=0**.

| Замок | Что менял | До (V1) | После |
|---|---|---|---|
| `test_compose.py` | Негатив ask_back: `_ask_back` → `""`/`None`; текст ответа без вопросительного ask | 91/1 FAIL «уточнение достаётся» | **93 ok**, EXIT=0 |
| `test_fork_label_daybasis.py` | 2 проверки B → негатив: `fork_outcome_b` is None (лидер/люк не выбирают окно) | 11/2 FAIL лидер/люк | **13 ok**, EXIT=0 |
| `test_k4_clarify_vs_nodata.py` | B4: `sales_canon_locked` не даёт support | 26/1 FAIL | **27 ok**, EXIT=0 |
| `test_k4_guess_vs_clarify.py` | P1/P2/S3 → негатив pre-wiki clarify; диск: до `wiki_primary` в новом z20 нет `period_assumed`/`warehouse`/`stock_subject` call-site | 12 ok / 3 FAIL / 1 pend | **17 ok / 0 FAIL / 1 pend (S1)**, EXIT=0 |
| `test_b9_routing.py` | fork-B блок → `bres is None` (авто-лидер снесён); count/axis-clarify без изменений | AttributeError на `bres.get` | **8 ok**, EXIT=0 |
| `test_fork_atom_aggregate.py` | **УДАЛЁН** (O5: fork-зона под снос B7) | timeout 120 | файл отсутствует |
| `test_action_class.py` | `kind_axis_hits` lambda + `meaning_ok=True` (×3); fork-A/B авто → None (иначе падение после починки lambda) | TypeError `meaning_ok` | **46 PASS**, EXIT=0 |
| `test_stock_balance_path.py` | Убрана опора на `A.K6R`; негатив «K6R снесён»; early/wiki-only моки без K6R | AttributeError `K6R` | **49 ok**, EXIT=0 |
| `test_zone_names_resolvable.py` | Flip: оба z20 на диске; патч только legacy (как `_exec_zone`); parse/slice обеих веток; subprocess `ASK_ONEPATH=1` → `load_all` | зелёный на legacy-default | **109 passed**, EXIT=0 (default legacy + new-ветка) |

## Итог финального прогона

```
test_compose.py                 EXIT:0  (93)
test_fork_label_daybasis.py     EXIT:0  (13)
test_k4_clarify_vs_nodata.py    EXIT:0  (27)
test_k4_guess_vs_clarify.py     EXIT:0  (17 ok, 1 pending S1)
test_b9_routing.py              EXIT:0  (8)
test_action_class.py            EXIT:0  (46)
test_stock_balance_path.py      EXIT:0  (49)
test_zone_names_resolvable.py   EXIT:0  (109)
test_fork_atom_aggregate.py     УДАЛЁН
```

## Заметки для оркестратора

- `_bootstrap` / инверсия `ASK_LEGACY` — **не** в этом пакете; замок `test_zone_names_resolvable` уже проверяет правило патча по имени файла и load новой ветки через `ASK_ONEPATH=1`.
- В `test_action_class` помимо `meaning_ok` пришлось согласовать fork-A/B с `fork_outcome_*=None` (В4) — иначе замок краснел сразу после починки lambda.
- Pending S1 в `test_k4_guess_vs_clarify` («stock marker ловит №12») — прежний дефект маркера, не из списка V4.
