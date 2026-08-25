# Аудит переусложнения пути ответа (okna, 25.08.2026)

**Статус:** только разбор; код, эталоны, прибор и стейджинг `:8092` не менялись.  
**Опора:** [`PLAN_ANSWER_CONTRACT.md`](PLAN_ANSWER_CONTRACT.md) §2–§5, §8;
[`PLAN_UPGRADE_NATIVE.md`](PLAN_UPGRADE_NATIVE.md) Ф6;
[`SCORER_CLASSES_2026-08-25.md`](SCORER_CLASSES_2026-08-25.md);
[`HOW_NOT_TO.md`](HOW_NOT_TO.md) §0;
проекты [`work/rank-path-fix-design.md`](../work/rank-path-fix-design.md),
[`work/silent-refusal-fix-design.md`](../work/silent-refusal-fix-design.md),
[`work/entity-compare-form-design.md`](../work/entity-compare-form-design.md);
журнал okna `ask_journal` (**1687** строк, `host=127.0.0.1 port=17890`);
код [`ubuntu/serenedb/serene_ask.py`](../ubuntu/serenedb/serene_ask.py) (только чтение).

---

## 1. Числа сложности

| Метрика | Значение | Источник |
|---|---:|---|
| Строк в `serene_ask.py` (весь файл) | **14 899** | `wc -l` |
| Строк в `answer()` (разбор → гейт → return) | **3 016** | AST, строки 11050–14065 |
| Строк обёртки `answer_checked` + `_answer_checked_core` | **125** | AST |
| Функций в модуле | **405** | `rg '^def '` |
| Имён функций, вызываемых из тела `answer()` | **183** (локальных) | AST call graph, 1 уровень |
| Развилок `if`/`elif` внутри `answer()` | **335** | подсчёт по телу |
| Точек `return` в `answer()` | **60** | подсчёт по телу |
| Env-флагов `ASK_*` в коде | **73** | парсинг `os.environ.get('ASK_…')` |
| Явно задано в env боя `:8091` | **4** (+ `ASK_SQL_RRF=1` по докам боя) | `/etc/1c-serene-ask-postgres.env`, `/etc/1c-serene-ask.env`, [`REGRESSION_BASE1.md`](REGRESSION_BASE1.md) |
| Флагов пути с дефолтом «выкл» и без плана включения на `:8091` | **6** | §5 ниже |
| Слоёв, способных погасить готовый ответ (§4) | **14** | разбор кода + журнал |
| Записей `ask_journal` okna | **1 687** | SQL `count(*)` |
| Находок с доказательством (§3) | **10** | таблица §3 |

---

## 2. Env-флаги: сколько, что в бою

### 2.1. Включено на бою `:8091` (okna)

| Флаг | Значение | Где видно |
|---|---|---|
| `ASK_LISTEN_PORT` | 8091 | `/etc/1c-serene-ask-postgres.env` |
| `ASK_SCORER` | `lm_dirichlet` | там же |
| `ASK_TOKEN`, `ASK_THINKING_OFF_BODY` | 1 | `/etc/1c-serene-ask.env` |
| `ASK_SQL_RRF` | 1 | [`REGRESSION_BASE1.md`](REGRESSION_BASE1.md), [`F6_ROLLOUT_CHECKLIST.md`](F6_ROLLOUT_CHECKLIST.md); в побазовом env строки нет — держится отдельной записью/бэкапом с 23.08 |

### 2.2. Дефолт «включено» без строки в env (всегда активны на `:8091`)

`ASK_FORK_DETECT=1`, `ASK_FORK_OUTCOMES=1`, `ASK_ALIAS_VETO=1`, `ASK_ENOUGH=1`,
`ASK_SIGNAL_DISAGREE=1`, `ASK_REQUIRE_SUPPORT=1`, `ASK_ARBITER_DETECTS=1`, `ASK_NOT_FOR=1`,
`ASK_SKIP_SERVICE_RIVALS=1`, `ASK_VETO_HEAD_WINS=1`, `ASK_ORDER_BY_MEANING=1`,
`ASK_JOURNAL=1`, `ASK_CHOICE_MEMORY=1` (shadow), `ASK_TRACE=1`.

### 2.3. Выключено на `:8091`, на стейджинге включалось по Ф6 — не «мёртвый код», а очередь выката

`ASK_RESOLVER_IVF`, `ASK_HEALTH_NATIVE_FRESHNESS`, `ASK_SOLR_SYNONYMS`,
`ASK_CALENDAR_AXIS`, `ASK_SALES_RANK_CANON` — см. [`F6_ROLLOUT_CHECKLIST.md`](F6_ROLLOUT_CHECKLIST.md).

### 2.4. Дефолт 0, на okna не включалось, плана включения нет

| Флаг | Дефект при «включить без данных» |
|---|---|
| `ASK_MEMORY_APPLY` | `ask_choice_memory` **0** строк при **1 687** журнала и **106** `ticket_used` ([`MEMORY_COLLISIONS_2026-08-25.md`](MEMORY_COLLISIONS_2026-08-25.md)) |
| `ASK_RAW_FOCUS_TRUST` | аварийный люк; обход гейтов промтом |
| `ASK_PROBE` | только probe-процесс `:8092` |
| `ASK_ALIAS_BY_CONCEPTS` | эксперимент 05.08, замок не гонялся на okna |
| `ASK_VETO_NEEDS_RANK` | 0 в env боя и стейджинга |
| `ASK_SLOT_COVER` | 0 в env; замок `test_enough.py` |

---

## 3. Таблица находок

| # | Класс | Что | Доказательство | Упростится | Риск | Чем закрыть риск |
|---|---|---|---|---|---|---|
| **H1** | 1 — дубли слоёв | Два подряд SQL-фильтра кандидатов при `want=sum`: блок «с величиной» и блок «с деньгами» — **один и тот же** запрос к `CORPUS` | ```11761:11795:ubuntu/serenedb/serene_ask.py``` — идентичный `SELECT … nums IS NOT NULL AND len(map_keys(nums)) > 0` | −1 запрос к базе на sum-вопрос; −15 строк | Низкий: второй проход не меняет множество | Замок entity_choice / AB gold okna без регресса |
| **H2** | 1 — дубли | **Два** вызова `fork_detector_scan`: ранний (голова `cands`) и исходный (`arb_pool`) | ```11811:11867``` и ```12552:12614:ubuntu/serenedb/serene_ask.py```; оба зовут `fork_detector_scan` | −1 полный SQL-круг на вопросах с `len(arb_pool)>1` | Средний: пулы разные (`cands[:16]` vs `arb_pool`) — нельзя слепо склеить | Shadow: сравнить `fork.classes` раннего и позднего на журнале; один scan + кэш `_fork_early` |
| **H3** | 1 — дубли | После `fork_outcome=unique` всё равно идёт круг арбитра → **46** clarify | SQL: `fork_outcome='unique' AND outcome='clarify'` → **46** / **66** unique (**70%**) | K5 (**2** FAIL): атом уже есть — терминальный ответ без arbiter | Средний: unique без `computed` atom должен остаться clarify | Правило из [`work/silent-refusal-fix-design.md`](../work/silent-refusal-fix-design.md): `unique`+`proof_status=computed` → early return; не трогать C |
| **H4** | 5 — лестница | Цепочка «fork → arbiter → mute → answers_diverge → clarify» при уже посчитанном atom | **246** записей: `outcome IN (clarify,figures)` и `atoms` содержит `proof_status":"computed"`; K5a/K5b в [`SCORER_CLASSES_2026-08-25.md`](SCORER_CLASSES_2026-08-25.md) | K5 + предотвращение K4→K5 после compare | Высокий без контракта §5: гейт всё ещё нужен против прозы модели | `render_atom_pair` на gate-fail; slot `compare`≠`rank` ([`silent-refusal-fix-design.md`](../work/silent-refusal-fix-design.md)) |
| **H5** | 3 — эвристика | Вход в sales-канон через `sales_sum_intent` (подстроки «продали»/«купил»/…), а не структура rank×sales | ```4590:4618:ubuntu/serenedb/serene_ask.py```; K1b «купил» → документ без lock ([`rank-path-fix-design.md`](../work/rank-path-fix-design.md) §0) | K1+K2+K3 (**4**/9 FAIL) одним контуром | Средний: compare-вопросы («лучше/хуже») завязаны на тот же список | `sales_rank_engaged` = rank + `sales_lift_possible`, без морфологии; AB 24 okna |
| **H6** | 3 — эвристика | `sales_force_money_measure` перебивает qty на rank («какого товара…») | K1a: diag `sales_measure_canon how=sales_canon` Количество→Всего ([`SCORER_CLASSES_2026-08-25.md`](SCORER_CLASSES_2026-08-25.md) §K1) | K1a | Низкий при `ASK_SALES_RANK_CANON=1` (уже в коде, **0** на `:8091`) | Выкат Ф6.5 + gold okna |
| **H7** | 5 — лестница | `answer_slot_mode`: `form=compare` → принудительно `rank` | K5b: `slot_mode=rank`, gate режет compare, refuse ([`silent-refusal-fix-design.md`](../work/silent-refusal-fix-design.md) §0) | K4+K5 на compare-форме | Средний: rank-ответы не должны стать compare | Явная ветка `form=compare` в slot_mode + compare SQL ([`entity-compare-form-design.md`](../work/entity-compare-form-design.md)) |
| **H8** | 4 — осиротевший | `ASK_MEMORY_APPLY=0` навсегда: память shadow-only | `ask_choice_memory` **0** строк; флаг читается только в `_try_memory_apply` | −ветка `_try_memory_apply` после стабилизации памяти | Низкий сейчас (no-op) | Сначала [`MEMORY_COLLISIONS_2026-08-25.md`](MEMORY_COLLISIONS_2026-08-25.md) — иначе включение опасно |
| **H9** | 2 — не срабатывало | `fork_outcome=A` на живом потоке | SQL: **6** / **1687** (**0,4%**) | Не снимать: редкий, но контрактный исход §2 | — | — |
| **H10** | 2 — не срабатывало | `doubt=true` | **45** / **1687** (**2,7%**); из них clarify **23** | Не снимать без shadow: сигнал §3 переходный | Потеря stop2/writer_pair на 2,7% | Shadow diff `ASK_SIGNAL_DISAGREE=0` на dev (уже в плане §3) |

---

## 4. Четырнадцать защит, которые могут погасить ответ

Порядок по коду `answer()` → `answer_checked()`:

1. `serene_enough` до поиска  
2. `serene_enough` после счёта  
3. Ранний `no_data` / `stock_balance` / coverage  
4. `fork_outcome` C → clarify  
5. `fork_outcome` unique **не** терминален → arbiter (H3)  
6. `stop2_active` + rivals  
7. `writer_pair` / `doubt` → расширение `arb_pool`  
8. `answers_diverge` / `mute` → clarify  
9. `_alias_clarify` (`ALIAS_VETO`)  
10. `measure_ambiguous` → clarify  
11. `axis_focus` / `rank_axis_missing` → clarify  
12. Исходящий `gate()` fail  
13. `refuse_text` / пустой `TOTAL_TEXT` при gate-fail (H4, K5b)  
14. `rank_gate_fallback` / `period_empty` вместо числа  

Журнал: **458** clarify + **195** figures + **107** unavailable из **1687** — больше трети запросов не заканчиваются `kind=answer`.

---

## 5. Три главных кандидата на упрощение (по убыванию выгоды)

1. **Терминальный посчитанный atom (H3+H4, класс K5)** — одно правило выдачи §5 вместо лестницы fork→arbiter→gate→refuse; чинит **2/9** FAIL и страхует K4 после починки compare.  
2. **Структурный sales-rank канон вместо лексических гейтов (H5+H6, K1–K3)** — заменить цепочку `sales_sum_intent` / `sales_force_money_measure` / measure-clarify на `sales_rank_engaged` + данные; **4/9** FAIL одним механизмом ([`rank-path-fix-design.md`](../work/rank-path-fix-design.md)).  
3. **Один fork-scan на вопрос (H2)** — убрать второй `fork_detector_scan` за счёт переиспользования `_fork_early`; минус SQL и латентность без новых правил, при сохранении двух пулов через пересчёт на том же scan там, где пулы совпадают.

---

## 6. Что из шести классов провалов чинится снятием лишнего (а не добавлением)

| Класс SCORER | N | Снятие лишнего (не новый код) |
|---|---:|---|
| **K5** Ответ в atoms, наружу отказ | 2 | H3+H4: unique terminal + gate-fail → `render_atom_pair`, не arbiter/refuse |
| **K1–K3** Rank-путь | 4 | H5+H6: один structural canon вместо 3–4 лексических гейтов (выкат `ASK_SALES_RANK_CANON`, не новые подстроки) |
| **K4** Compare форма | 1 | H7: убрать принудительный `rank` slot_mode — иначе compare снова спрячется за K5 |
| **K6** Не та сущность | 2 | **не** снятием: нужны формы F в детекторе ([`entity-compare-form-design.md`](../work/entity-compare-form-design.md)) |
| H1 (дубль SQL фильтра) | — | не класс провала; экономия запроса |
| H2 (дубль fork_scan) | — | латентность, не качество на текущем скорере |

Флаги Ф6 на стейджинге **0** diff вердиктов на 24 gold ([`SCORER_CLASSES_2026-08-25.md`](SCORER_CLASSES_2026-08-25.md) §3) — переусложнение качества okna сейчас **не** в IVF/solr/calendar, а в rank/slot/gate.

---

## 7. Ответ владельцу: есть ли место, где проще = лучше?

**Да.** Переусложнение не «весь файл 15k строк», а **наложение трёх поколений**: (а) сигнальный арбiter (doubt/stop2/writer_pair), (б) детектор fork A/B/C, (в) исходящий gate/refuse. Поколения (а) и (б) **оба** решают неоднозначность; журнал показывает, что (б) уже даёт исход, но (а) всё ещё перехватывает **unique** и **computed** атомы (H3, H4). Плюс лексические sales-гейты (H5) множат ветки там, где контракт §6bis требует одного структурного правила.

Пустого результата нет: есть и честные дубли (H1), и переходный хвост с документированным планом снятия (§3 [`PLAN_ANSWER_CONTRACT.md`](PLAN_ANSWER_CONTRACT.md)).

**Вывод одной фразой:** качество okna упирается не в нехватку флагов, а в **два параллельных судьи неоднозначности и лексические заплатки rank/sales**, которые проектные доки уже предлагают заменить одним data-driven правилом — снятие лишнего там даст **6/9** FAIL без расширения `serene_ask.py`.
