# G3 — красный аудит замков после X3

Аудитор: красная команда G3. Контекст нулевой. Серверы не трогались.
Правки — только этот отчёт. Материал: `test_pdoc_tail_equivalence.py`,
`test_corpus_merge_unmatched_split.py`, `corpus_build.sql` / `corpus_merge.sql`
(текущее дерево), R3/R4 (`result-t1r3.md`, `result-t1r4.md`), промт X3.

Числа PASS 49/49 и 20/20 приняты как заявление материала; прогон замков
здесь не выполнялся (риск касания живого `:7890` через `resolve_dsn`).

---

## 1. Новые кейсы X3: живой движок vs греп

| Кейс | Где | На движке реально | Только текст | Обманчивый PASS? |
|---|---|---|---|---|
| **fresh-battle** (BUG-1) | `test_fresh_battle_order_bug1` | Фикстура → **зеркало** decide (`_build_order_and_decide`) → **зеркало** wipe (`_fresh_wipe_runtime_only`, `on_=false` зашит) → **зеркало** chunk/tail/finalize (`_run_chunk_tail_finalize`) → `stage==nrows`, multiset≡mono | Offline: needle `_done`+«артефакт плана» (не запрещает снова вставить `DELETE tmp3_pdoc_tail` на fresh) | **Да, относительно файла.** Доказывает семантику «wipe не трогает tail → хвост доезжает», но **не** что так записано/исполняется в `corpus_build.sql`. Регрессия buggy `DELETE tail` в файле при неизменном хелпере замка — PASS. |
| **боевая строка** (BUG-2) | `test_battle_tail_multistmt` | После decide-зеркала: порции; затем `\gexec` с **встроенной** копией `SELECT 'EXECUTE p_doc_tail…; INSERT …done…'` (форма как `:2540-2546`); stage↑, done=1; повтор по guard → 0 | `_battle_tail_dispatch_stmt`: только факт needle в файле + сборка через `repr(tbl)`; offline: нет `BEGIN TRANSACTION; EXECUTE p_doc_tail(` | **Частично.** Живой путь — настоящий multi-statement `\gexec`, не split. Но SELECT **скопирован в тест**, не вырезан из файла; `_battle_…_stmt` «≡ файлу» — слабый греп+конструктор. Offline ловит возврат BEGIN. |
| **«\|»-класс** | `test_pipe_keyvals_empty_strings` | Двухколоночный ключ `''\|''` → tail keyvals=`\|`, collision_rows=3, path=v5; chunk+tail+finalize; multiset≡mono | нет (кроме общего offline) | **Нет** (в пределах зеркала decide/run). Закрывает R2-D4 / дыру R4 про пустые строки. |
| **негатив coverage** | `test_coverage_gate_negative` | Decide-зеркало с вырезанным `DELETE order` по tail → `psql` падает; в stderr ищется `count(order)+collision_rows` | проверка, что шаблон DELETE нашёлся для replace | **Нет** по заявленному: гейт на движке реально `error`. Не доказывает «гейт после wipe» (P5) — wipe тут не участвует. |
| **unknown-unit** (R1-D2) | M1 `test_corpus_merge_unmatched_split.py` | Формула 0.55×`current_setting` на **известной** единице движка → строка `N GiB/…` | `t(…неизвестная единица…)` + `NOT IN ('', 'b', …)` по тексту `corpus_merge.sql`; тот же CASE **продублирован** в probe SQL теста | **Да, если считать «закрыт fail-closed».** Ветка `error(…неизвестная единица…)` **ни разу не исполняется**. Grep+дубль CASE ≠ живой негатив (`TB`/`%`/мусор). |

Прочее (не «новые X3», но фон): старый `test_resume_and_fresh` обновлён ожиданием «`_done`=0, tail жив» — wipe снова **изолированный SQL в тесте**, не из файла. Offline M2 по-прежнему грепает PREPARE/гейты/lifecycle-иголки.

---

## 2. Fresh-battle: файл целиком или выборочная пересборка?

**Выборочно.** Не `psql -f corpus_build.sql` и не вырезанный непрерывный блок decide→wipe→dispatch.

| Шаг боевого порядка файла | В fresh-battle |
|---|---|
| formula / entity / order (`\gexec` с LineNumber/Recorder, ~1432–1532) | Упрощённое зеркало: cfg + entity_rows + formula `v8c` + chunks + свой `_keyvals_expr_sql` |
| decide collision/mono/INSERT tail/DELETE order/coverage (~1539–1612) | `_build_order_and_decide` (Python-строка, **не** `BUILD.read` куска) |
| `tmp3_resume_pdoc` из progress/run (~1617–1619) | **Нет** — wipe сам делает `on_=false` |
| search_quality / formula persist / `DELETE corpus WHERE NOT on_` (~1621–1658) | **Нет** |
| wipe stage/progress/**только** `_done` (~1660–1670) | `_fresh_wipe_runtime_only` — копия смысла фикса, **не** текст файла |
| диспетчер порций с progress-guard (~2520–2537) | Упрощённый цикл всех chunks сущности |
| хвост **одной** multi-statement строкой (~2539–2546) | **`_run_chunk_tail_finalize`**: `EXECUTE` и `INSERT done` **двумя** строками `\gexec` (старый split; BUG-2 здесь не гоняется) |
| finalize + post-clean (~2548–2570) | `EXECUTE p_doc_finalize` + проверка multiset; post-clean хвоста не обязателен для PASS |

**Что всё ещё не покрыто боевым порядком файла в этом кейсе:**
1. Идентичность decide/wipe SQL файлу (дрейф зеркала ↔ файл).
2. Вычисление `on_` штатной формулой, а не хардкодом `false`.
3. Связка fresh-wipe **из файла** + хвост **боевой** multi-statement строкой в одном прогоне (сейчас BUG-1 и BUG-2 разведены по разным кейсам и разным SQL).
4. Guards диспетчера `NOT EXISTS(corpus)` / `EXISTS(chunks)` в том же сценарии, что wipe.
5. Offline **не** запрещает вернуть `DELETE FROM tmp3_pdoc_tail` на fresh рядом с комментарием «не стираем».

Итог по п.2: кейс валиден как **семантическая** регрессия «хвост переживает fresh-wipe», обманчив как **замок на файл**.

---

## 3. Не покрыто из R3 (P1–P8) / R4 (BUG-1..3)

| Сценарий | Статус после X3+замков | Приемлемо? |
|---|---|---|
| **P1 / BUG-1** fresh-wipe сносит tail | Фикс в файле есть (`:1667–1670` только `_done`). Замок — семантика на зеркале, не на тексте wipe файла | **Неприемлемо как единственный гейт выката** — регрессия в SQL может зеленеть. Приемлемо как smoke смысла фикса. |
| **P2** `keyvals IN (…)` vs SQL NULL | Фильтр chunk/tail всё ещё `IN` (`:1981`, `:2211`). V5-фикстура даёт `∅`, не NULL-keyvals. Живого кейса «NULL в tail → 0 строк / stage_gate» нет | **Приемлемо для выката X3** (латент; R3: после `∅` маловероятно). **Неприемлемо** объявлять P2 закрытым замком. |
| **P3** двойная вставка / атомарность | Баг не найден. BUG-2: live multi-stmt без BEGIN + offline anti-BEGIN | **Приемлемо.** Негатив «обрыв после EXECUTE» по-прежнему нет. |
| **P4** DELETE order + уникальный NULL | R3: не баг | **Приемлемо** (не чинить/не лочить). |
| **P5** coverage до wipe, wipe не перепроверяет | После снятия DELETE tail смысл P5 для wipe умер. Негатив гейта — другой дефект (сломанный DELETE order) | **Приемлемо.** |
| **P6** вектора / merge xfer | Вне диффа V5 | **Приемлемо** (не предмет X3). |
| **P7** lifecycle post-success → следующий build | Offline + куски resume; нет полного юнит№0→№1 из файла | **Приемлемо** при зелёном такте на окне; не замок. |
| **P8** mono при живых chunks | R3: не найдено | **Приемлемо.** |
| **BUG-2** BEGIN/COMMIT в `\gexec` | Фикс + live multi-stmt + offline | **Приемлемо** (с оговоркой: SELECT в тесте — копия). |
| **BUG-3** pre-decide чистит tail, не `tail_done` | Не фиксилось X3; замка «done=1 + stage пуст + on_=true + decide» нет | **Приемлемо как не-блокер выката** (R4: medium, узкий). **Неприемлемо** считать закрытым. |
| R4 «вся сущность в tail / order пуст» | Нет кейса | **Приемлемо** (R4: не блокер). |
| **R1-D2** unknown-unit fail-closed | В SQL есть; замок — grep + формула на штатной единице | **Неприемлемо** как доказательство fail-closed; **приемлемо** отложить живой негатив, если выкат не ждёт только D2. |

Короткий список «дыр, которые ещё значат»:

1. **BUG-1 замок не привязан к wipe из файла** — главный обман PASS.  
2. **P2 NULL/`IN`** — незакрыт замком (и кодом).  
3. **BUG-3** — незакрыт.  
4. **unknown-unit** — нет live `error`.  
5. **Один прогон decide(file)→wipe(file)→dispatch(file multi-stmt)** — отсутствует.

---

## Итог

Замки после X3 **лучше**, чем до: «\|», негатив coverage, live multi-stmt хвоста, семантика «tail переживает fresh» — реальные прогоны на движке (эфемер/DSN). Критичные дыры R4 «замки не ловят BUG-1/2» **частично** заткнуты по смыслу.

Но fresh-battle и unknown-unit дают PASS, которые **не доказывают** то, что читается в названии/закрытии находки (файл / fail-closed ветка). Для честного гейта выката диффа SQL этого мало.

**Замки достаточны для выката — НЕТ**
