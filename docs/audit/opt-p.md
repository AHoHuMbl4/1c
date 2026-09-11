# OPT-P: параллельность последовательных переборов в тракте `/ask`

Режим: только чтение кода. Дата: 11.09.2026. Роль **P**.  
Код: `ubuntu/serenedb/ask/z02,z05,z06,z09,z10,z11,z12,z13,z20` + `entity_rank_v2.py`.  
Опора: зонд оркестратора 11.09 rid `b11dac07` (ниже = истина по wall);  
`MOL_PLAN_2026-09-11.md` §0–§5; `mol-par-m2.md` (устаревшая атрибуция K6).  
Коммитов нет.

---

## Вердикт

Указание владельца «последовательный перебор вариантов — распараллелить»
попадает **не** в «77 кандидатов × SQL», а в несколько **коротких** независимых
множеств: intent-сэмплы LLM, readings×`fork_scan`, arbiter×N sub-`answer`,
(опционально) оси kind для catalog-резолва и группы resolve.

Крупнейшие секунды зонда (`stock` 50,6 с; хвост до «собраны» 25,3 с) — это
**не** кандидаты-в-цикле: в stock-фильтрах SQL уже батчевый (`IN` / один
`EXISTS`), а `entity_pick_counts_for_model` — чистый Python по `feats`. Их
лечить ThreadPool’ом по cands **бесполезно**; выигрыш — кэш/не-engage (роль S)
и батч/reuse feats (роль C). Параллель — второй слой, после устранения ложного
пути и батчей.

`ThreadingHTTPServer` (`z20:6239`) параллелит **разные** HTTP-запросы. Внутри
одного `answer` почти всё строго последовательно; общий `diag`/`шаги` —
локальные замыкания запроса, но **не** thread-safe при вложенных потоках без
изоляции.

---

## Свежая атрибуция (зонд ≠ mol-par / mol-k6)

| Интервал зонда | Wall | Что в коде (порядок `z20:2228+`) | Параллель по cands? |
|---|---|---|---|
| prefer_sales | 0,8 с | `prefer_entity_for_sales` `z11:236` — 2–4 SQL батчем + `_measures_by_src` | Нет |
| prefer_catalog+rank | 9,5 с | `prefer_entity_for_rank` `z10:428` + `prefer_entity_for_catalog_count` `z11:759` (и/или соседние маркеры зонда) | Нет (уже `IN`) |
| **stock-блок** | **50,6 с** | `stock_question_engaged` + тело `z20:2232-2239` **или** `else→prefer_entity_for_stock→stock_canon_src` | **Нет** — стоимость в `stock_goods_pool` / catalogs / EXISTS, не в `for c in cands` |
| K6-apply | **1,3 с** | `K6R.apply_to_candidates` `entity_rank_v2:804` | Нет (батч; M1 «52 с» устарела) |
| Z7→«кандидаты собраны» | **25,3 с** | После маркера `K6 v2`: снова stock-тело `z20:2270-2286`; `entity_pick_counts_for_model` `z06:548` стоит **между** apply и маркером K6 и **не делает SQL** | Параллель counts — N/A; хвост = stock#2 / ложный engage |

Итог 88 с+: главные молекулы — S (ложный/тяжёлый stock-path ×1–2) и хвост
после K6; не «K6 features scan».

---

## Карта всех последовательных переборов

Колонки: **независим?** = элемент i не читает результат i−1 и не обязан писать
в общий `cands`/`diag` по порядку до конца пачки.

| # | Место | Цикл / пачка | N типично | Независим? | Пишет в общий state | Безопасная форма | Риск | Выигрыш (с) |
|---|---|---|---|---|---|---|---|---|
| **P1** | `z02:668-672` | `while` → `_one_intent` → `ds_chat` | 3–5 | **Да** (один `msgs`) | `samples` list; LEAD читает готовые | **ThreadPool** слотов 0..N−1; merge по индексу; cancel после LEAD | Tie-break порядка; orphan LLM; квота API | **−5…10** холод; 0 при INTENT_MEMO |
| **P2** | `z06:122-142` | groups без FTS → `resolve_values` | 0…G | Да между groups; **нет** внутри group (`break` на первом alt) | `per_group` / `diag._resolved` | ThreadPool **по groups**; внутри group — как сейчас | Порядок break→другой alt; L67 | −0…2 (редко) |
| **P3** | `z06:538-544` fallback meaning | 4 поверхности подряд | 4 | Да (входы разные) | `out` порядок fuse | ThreadPool 4× **или** уже `_fused_candidates` | Порядок fuse → голова cands | −0,5…1,5 |
| **P4** | `z12:445-448` + `z05:293` | `for w in intent_axis_words` → `entity_form_catalogs_for_kind` | 1–3 | Да между словами | `cats` set | ThreadPool слов **или** один SQL `OR`/`IN` stems | Нагрузка FTS×N | −1…N×SQL; на ложном stock — часть из 50 с |
| **P5** | stock filters S `z20:2232-39`, `2270-86` | `for c in cands` только Python-отсев; SQL — `stock_goods_pool` / `filter_balance_structural` IN | 77 cands / 1–3 SQL | Cands **зависимы от пула**, не друг от друга | `cands`, `diag.stock_*` | **Не** ThreadPool по cands. Кэш engagemеnt; батч holders; **не трогать** true-stock | Ложный skip / ложный keep | Параллель ≈0; S-фикс −50…−75 |
| **P6** | `entity_rank_v2:719-726` `expand_holders` | `for cat: psql(target_src=cat)` | |cats| | Да между cat | `out` порядок append | **Один SQL** `target_src IN (…)`; не пул | Порядок holders | −десятки×35 мс (на rid K6=1,3 с — мелочь) |
| **P7** | `entity_rank_v2:735-741` | 4 prefix stem_overlap | 4 | Да | `out` | UNION / один SQL **или** пул | Порядок expand | −0…1 |
| **P8** | **C** `z06:548-577` counts | `for src, raw in by.items()` | ≤|by| | Да, но **без I/O** | `out` dict | Не параллелить; reuse `answer_fit_v2_full` | — | **~0** (мс) |
| **P9** | `z20:2348-2362` not_for указатели | `for rt: psql(count…)` | единицы | Да | `указ` dict | **Один SQL** по списку rt (п.20) | False pointer → wrong drop | −0,1…0,5 |
| **P10** | `z09:330-365` `fork_scan_readings` | `for rd in readings: fork_scan` | 4–8 | **Да** (разные окна) | `cells`/`merged_rows` | **Предпочтительно multi-window SQL**; ThreadPool — серая зона п.20 | Contention/OOM; порядок cells/meta (замок 4d) | **−6…10** из ~12 |
| **P11** | второй `fork_detector_scan` исходы | повтор P10 | 1 | Зависит от совместимости пула | `diag.fork` | **Reuse** `_fork_early` (план 4a), не параллель | B8-01 | **−5…12** |
| **P12** | `z20:3720-3757` **арбитр×N** | `for c in arb_pool[:ARBITER_MAX]: answer(…, no_arbiter=True)` | ≤3 | **Да** между c | `cand_ans`/`cand_src`/`mute`/`cut`/`diag.arb_probe` | ThreadPool N≤3; **изолированный** sub-diag; merge по слоту `arb_pool` | N× SQL+LLM; гонки `cut.setdefault`; deadline; L67 если порядок сравнения сменится | wall ≈ max(sub) вместо sum: **−(N−1)×T_sub** когда арбитр жив; на early-clarify/меню — 0 |
| **P13** | wiki pick→verify | 2× `ds_chat` | 2 | **Нет** (verify от pick) | wiki diag | Не параллелить | — | 0 |
| **P14** | measure / axis rerank HTTP | разные роли | 0–3 | Часто да между ролями | plan/diag | ThreadPool HTTP только | rate-limit; порядок | −1…3 редко |

---

## Разбор обязательных узлов (S / C / arbiter / intent)

### S — «кандидаты в фильтрах» (`z20:2232-2239`, `2270-2286`, `z12`)

Что выглядит как цикл по кандидатам:

```875:882:ubuntu/serenedb/ask/z12_stock_balance.py
    for c in list(cands or []):
        if c and c.startswith("accumulationregister_") and c not in pool:
            dropped.append(c)
        else:
            out.append(c)
```

Это **чистый Python** после уже посчитанного `pool`. Дорогое:

1. Каждый вход в `stock_question_engaged` (`z12:416`) → `_kind_is_stock_scoped` →
   `_catalogs_for_axis_word` → `entity_form_catalogs_for_kind` (stem SQL по всем
   `catalog_%`, при пустоте — `meaning_candidates`) + `question_mentions_warehouse_axis`
   (ещё catalogs). На kind≈«товар/номенклатура» pred может стать True на
   **продажном** «полный отчет» (разбор роли S).
2. При True: `balance_capable_or_registers` → `stock_goods_pool` →
   `registers_for_kind_axes` (**P4** + **один** тяжёлый `EXISTS` по корпусу
   `z12:457-466`) + `_stock_registers_with_product_axis` (ещё SQL).
3. Post-K6 (**P5#2**): то же + `filter_balance_structural` — уже **батч**
   `IN (...)` (`z12:1283-1287`), не N запросов.
4. `prefer_entity_for_stock` / `stock_canon_src:1066` снова зовут engagemеnt;
   при False — мгновенный `None`.

**Параллель по 77 cands — запрещена как бессмысленная.**  
Допустимые формы внутри S (если engagemеnt остаётся True):

| Форма | Оценка |
|---|---|
| Кэш `(rid, q, intent-fp) → engaged` + не звать pred внутри filter_* | Обязательно (S); снимает ×3 word/SQL |
| ThreadPool по `intent_axis_words` (P4) | Слабый выигрыш; лучше один SQL |
| ThreadPool вокруг `EXISTS` / corpus count | **Нет** (MOL §5; п.20) |

Ожидание от параллели S: **~0 с**. Ожидание от S-плана (не engage + один вызов):
−50…−65 с — вне скоупа «параллель», но закрывает зонд.

### C — `entity_pick_counts_for_model` + до «кандидаты собраны»

```548:577:ubuntu/serenedb/ask/z06_entity_search.py
def entity_pick_counts_for_model(by, diag, intent=None, question=""):
    ...
    for src, raw in by.items():
        f = feats.get(src) or {}
        ...
    return out
```

- SQL **нет**; цикл по уже лежащим в `diag["answer_fit_v2_full"]` фичам.
- Ранний выход, если `want` не `count`/`""` и нет rank (`:560-561`).
- Маркер `шаг("K6 v2")` стоит **после** counts (`z20:2267-2269`); между
  `K6 v2` и `кандидаты собраны` в коде только **второй stock-блок**.

Следствие для P: атрибуция зонда «25,3 с = counts» скорее = **stock#2** (или
маркеры зонда шире функции). Параллель/батч-IN «counts по 77» **не к чему
применить** в этой функции. Если роль C найдёт другой счётчик с N×SQL —
форма: один `WHERE src_table IN (…)`, не ThreadPool.

### Арбитр ×N (`z20:3712+`, цикл `:3720`)

```3720:3730:ubuntu/serenedb/ask/z20_ask_main_http.py
        for c in arb_pool[:ARBITER_MAX]:
            if deadline_hit():
                raise AskDeadline("deadline")
            try:
                sub = answer(question, focus=c, measure_pick=measure_pick,
                             context=context, no_arbiter=True, prior=prior)
```

| Свойство | Факт |
|---|---|
| Независимость | Да: `focus=c`, `no_arbiter=True`, intent из memo внешнего |
| Общий state | `cut.setdefault` из `sub.partial`; `diag.arb_probe.append`; списки `cand_ans`/`cand_src` **по порядку пула** |
| Deadline | `deadline_hit()` — monotonic по rid (`z01:111`); читать из потоков ок; raise — только в координаторе |
| Сервер | Уже `ThreadingHTTPServer`: параллельные `/ask` уже делят движок |

**Безопасная форма:**

1. `executor.map` / futures по слотам `enumerate(arb_pool[:ARBITER_MAX])`.
2. Каждый поток: свой локальный результат `(i, sub|exc)`; **не** трогает
   внешний `diag`/`шаги`.
3. Главный поток: сортирует по `i`, наполняет `cand_ans`/`mute`/`cut` **в том
   же порядке**, что сейчас (сравнение атомов не зависит от wall-time).
4. `AskDeadline` из sub — проброс после join; частичные результаты не
   смешивать с «успел один — ответили».

| | |
|---|---|
| Выигрыш | Если 3× тяжёлых sub по ~15–40 с → wall ~max; на полном отчёте часто срабатывает **early entity-clarify** (`:3636-3710`) до цикла → **0**. Env `ASK_ARBITER_MAX=2` режет без пула |
| Риск | N concurrent `psql`+compose; пик рядом с тактом; гонка если забыть изолировать diag; смена порядка merge → другой winner (**L67**) |
| п.20 | Оркестрация готовых путей «база считает» — допустимее, чем пул вокруг сырого corpus-SQL; MOL §5 всё же: «ThreadPool arbiter на проде на этой неделе — нет». Для OPT: **полигон + замок**, прод после стоп-точки |

### Intent 3–5 сэмплов (`z02:668-672`)

Классика mol-par §а. Элементы независимы; LEAD — early-stop по уже готовым.

**Форма:** пул `min(SAMPLES, …)` слотов; по `as_completed` дописывать
`samples[i]`; при lead≥`INTENT_LEAD` — cancel остатка (HTTP уже ушёл);
`_merge_intents` с tie-break по **индексу слота**, не по времени прихода.

Выигрыш **−5…10 с** на холодном разборе; на rid с memo — 0.  
п.20: пул вокруг LLM — **вне** базы, ок.  
Не делать: `SAMPLES=1` (MOL §5 / stability).

---

## Что НЕ параллелить

| Шаг | Почему |
|---|---|
| True stock-path (остатки) после честного engage | Качество; указание «складской путь не трогать» (S) |
| Wiki pick→verify | Строгая зависимость |
| K6 `features_table` / corp aggregate | Уже один SQL; пул вреден (contention) |
| Цикл `for c in cands` в stock-фильтрах | Нет I/O на итерацию |
| `entity_pick_counts_for_model` | Нет I/O |
| `fork_scan` dated ‖ cat внутри одного reading | Уже последовательные два вызова на разных множествах; можно параллелить пару, выигрыш мал vs multi-window |
| Compose / gate после цифр | Нужен полный ответ |
| Глобальный LRU intent/реранк между запросами | MOL/M4 запрет; не путать с пулом внутри запроса |

---

## Грань п.20 и ThreadingHTTPServer

| Приём | Вердикт P |
|---|---|
| Батч-SQL (`IN`, multi-window, holders IN) | **Штатно, первым** |
| ThreadPool вокруг `ds_chat` / `rerank` | Ок (свой контур модели/сети) |
| ThreadPool arbiter×N `answer` | Условно ок как оркестрация; нагрузка ×N; не «считать в Python» |
| ThreadPool вокруг тяжёлых `psql`/fork_scan/EXISTS | **Серая / по MOL §5 — нет** на проде; сначала один SQL |
| Писать в общий `diag`/`шаги` из потоков | **Запрещено** без lock/изоляции: `шаг` — `list.append` + trace; два `/ask` уже разделены потоками сервера, вложенные потоки внутри одного Handler ломают TRACE/PROBE |

---

## Рекомендации (порядок внедрения параллели)

Согласовано с MOL §6 и ролями S/C: сначала убрать ложный stock и батчи, потом пулы.

| Приор. | Действие | Файл:ориентир | −сек | Условие приёмки |
|---|---|---|---|---|
| 0 | **Не** параллелить S-cands / C-counts | — | 0 | — |
| 1 | S: кэш engaged + быстрый intent-exit (роль S) | `z12:416`, `z20:2232/2270` | −50…−65 | Нескладской rid: stock-тело 0; складской — без регресса |
| 2 | C: если 25 с = stock#2 — закрывается п.1; иначе батч реального SQL | `z06:548`, `z20:2270` | −20…−24 | Маркер «собраны»−K6 ≤2 с на sales-list |
| 3 | Intent ThreadPool + LEAD | `z02:668-672` | −5…10 холод | Stability/L67 kind; memo не ломать |
| 4 | Fork readings: multi-window SQL (4d), не пул | `z09:319-365` | −6…10 | Замок порядка cells; L67 |
| 5 | Reuse fork scan (4a) | `z20` early/исходы | −5…12 | B8-01 в замок |
| 6 | Arbiter ThreadPool (полигон) | `z20:3720` | wall max vs sum | Порядок слотов = `arb_pool`; L67; пик conn |
| 7 | expand_holders / not_for → IN | `entity_rank_v2:719`, `z20:2348` | −0…1 | Эквивалент множества |

**Суммарный потолок от чистой параллели (без S/C-фиксов):** roughly
**−5…10 (intent) + −6…10 (fork SQL) + arbiter-when-hit**.  
До зонда 88→≤40 **не дотягивает** без S/C. Параллель — дополнение к
оптимизации существующего, не новая система.

---

## Краткая таблица «да/нет» для исполнителя

| Перебор | Параллелить? | Чем |
|---|---|---|
| Intent samples | **Да** | ThreadPool + LEAD, merge по слоту |
| Stock filter cands | **Нет** | Кэш/детект (S) |
| Counts-for-model | **Нет** | Уже O(|by|) RAM |
| expand_holders cats | Батч, не пул | `IN` |
| fork readings | Батч SQL; пул — запасной | 4d |
| Arbiter×N | **Да на полигоне** | ThreadPool + изоляция diag |
| Wiki / stock true / K6 corp | **Нет** | — |

---

*Конец OPT-P. Внедрение — по стоп-точке; этот файл только карта и границы.*
