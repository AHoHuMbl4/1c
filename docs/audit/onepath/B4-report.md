# B4: SQL-ступень + меню прочтений + compose/gate в новом z20

Срез: 12.09. Источник справки: `z20_ask_main_http_legacy.py` (только чтение).
Новый файл: `ubuntu/serenedb/ask/z20_ask_main_http.py` (не в `_bootstrap` до B6).
Замок: `ubuntu/serenedb/test_one_path.py` (фаза «после сноса pre-wiki clarify» O5 §2.6).
Git/база/полигон не трогались. Legacy / `_bootstrap` / прочие test_* не правились.

## Что сделано

### 0. Чистка промптов (ядро R1/R2; B5-хвост не тронут)

| Правка | Где | Результат |
|---|---|---|
| Вырезан блок `ask` / middle-road из `ANSWER_SYS`; поле `ask` убрано из JSON | `z18_compose.py` | `[код]` |
| `_ask_back` → всегда `""` (потребитель ask_back в новом тракте не появляется) | `z18_compose.py` | `[код]` |
| `CLARIFY_SYS` обнулён; `clarify_text` → `""` (имя оставлено: legacy OUR_PROMPTS до flip) | `z07_rrf_vectors.py` | `[код]` |
| `arbitrate` + inline sys_msg снесены | `z01_infra_trace_llm.py` | `[код]` |
| `OUR_PROMPTS` без CLARIFY; + `WIKI_PICK_SYS`, `WIKI_VERIFY_SYS` | новый z20:755–756 | `[код]` |
| INTENT `amount.op` += `"="`; `period2` в промт **не** добавлялся | `z01` INTENT_SYS | `[код]` |

Не тронуто (B5): why в VERIFY, user-утечки axes/col, дедуп COVERAGE, MUST в compose user.

### 1–8. Тракт answer() (B4)

| Ступень | Строки (новый z20) | Дыра O3 / контракт |
|---|---|---|
| Helpers: `readings_menu`, captions, sole reading | 1393–1498 | единый построитель; O5 ALLOWED |
| `_settle_measure` / `_measure_menu_opts` | 1485–1550 | №10 count_defer; №12 единственность без ранжира |
| `_settle_axis` (без silent rerank) | 1553–1627 | №8/№12 ось как reading |
| `_onepath_compose_gate` (+ atoms z15, gate, period_empty) | 1630–1843 | №11 z18/z19; одно число; без ask_back-clarify |
| 1. Intent + deadline | 1853–1880 | №13 |
| 2. Readings без лидера | 1882–1920 | №8 |
| 3–5. Wiki / билет; coverage после | 1922–1974 | №4, №9, №14 |
| 6. Меню window/measure/axis **ДО SQL** | 1981–2063 | №8, №10, №12 |
| Compare-окна → readings; ответ через compose | 1995–2008, 2110+ | №11 z11; нет sales_compare-терминала |
| 7. SQL: groups / compare / rows+aggregate / stock-net при выбранных | 2065–2199 | whitelist SQL; src из wiki |
| 8. Compose+gate + diag src/readings/choice/settle | 2201–2220 | №11, №13 |
| `stale_note` | Handler (B2, без изменений) | №11 z19 |

## Итоговые числа

| Метрика | Значение |
|---|---|
| Строк нового файла | **2918** (инфра B2 ~1400 + тракт B4; ориентир ≤1500 недостижим без сноса bit-identical инфры) |
| `def answer` | 1846–2220 |
| Замок `test_one_path` | **41/0** |

## Проверки (обязательные)

| # | Проверка | Результат |
|---|---|---|
| 1 | `python3 -m py_compile` z20 + z18 + z01 + z07 | **OK** |
| 2 | `timeout 120 python3 test_one_path.py` | **41/0 зелёные** |
| 3 | Grep-негатив запрещённых имён | **OK** (0) |

Запрещённые (0 совпадений в новом z20): `pick_measure`, `kind_axis_rerank`,
`max(by`, `_fork_atom`, `arb_pool`, `entity_form_gate_open`, `measure_in_kin`.
`sales_compare_windows` — только для окон-readings (1 вызов); терминал
`render_atom_pair` в `answer` отсутствует.

Замок наращен (O5 §2.6 «после сноса pre-wiki clarify»):
- полная **(а)** — 0 Dict/`return` kind=clarify мимо `readings_menu`/`clarify_opts_response`;
- **(в)** — 0 `SQL_CALLS` до `wiki_primary_entity_cascade`;
- **(г)** — прежний чёрный список + B4-имена.

Behaviour-замки (measure_menu/compose/gate/…) **не** гонялись — полигон B5.

## Дыры O3 закрытые в B4

| № | Как закрыто |
|---|---|
| 8 | Меню window/measure/axis до любого ответного SQL |
| 10 | `count_defer_measure_clarify` → мерное меню гасится |
| 11 | Проводка z11 compare→compose, z12 stock-net как SQL-форма, z15 atoms, z18 compose+gate, z19 stale_note (Handler) |
| 12 | Единственность: sole reading / билет; без ранжиров-выбирателей |
| 13 | `AskDeadline` после intent, до wiki, до SQL, до compose |

## Намеренно не сделано (B5+)

- Shadow L67 / behaviour-замки на новом файле
- why/user-утечки / дедуп COVERAGE
- Flip bootstrap (B6)
- Полный (б) «вторые числа» в `test_one_path` (B7)

## Дальше

Волна **B5**: полигон behaviour-замков + shadow; гигиена leftover промптов.
