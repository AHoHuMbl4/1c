# T1-D1: круг 2 аудита плана — КОРРЕКТНОСТЬ (C1 → v2)

Дата: 2026-09-02. Контекст нулевой. Серверы не трогались.
Материал: `docs/audit/TAKT_SPEED_PLAN_2026-09-02.md` (v2); свои требования
`result-t1c1.md` §6; код `ubuntu/serenedb/{corpus_merge,corpus_build}.sql`, `build.sh`.
Файлы (кроме этого отчёта) не правились.

---

## 1. Правки круга 1 → внесена?

| # | Правка C1 §6 | Внесена | Как / замечание |
|---|---|---|---|
| 1 | Диспетчер unmatched: `DISTINCT tmp3_corpus ∖ rewrite_wave` (не `tmp3_merge_ents`); fail-safe wave; уникальность ключей | **да** | §1.1: диспетчер из `DISTINCT src_table FROM tmp3_corpus WHERE … NOT IN rewrite_wave`; `NOT IN wave` сохранён в теле PREPARE; M1 — уникальность `(src_table,row_key)` и assert списка. |
| 2 | Dup: `count(order) ≠ nrows` → mono, не V5 | **да** | §2.1(в): неполный order → прежний монолитный путь, НЕ V5. M2 повторяет. |
| 3 | Хвост вне `done_rows`; tail до finalize; resume без двойного tail | **да** (с дырой, см. §3) | §2.3: `done_rows` не меняется; `EXECUTE p_doc_tail` после порций до finalize; маркер `tmp3_pdoc_tail_done`; finalize без маркера → error. Жизненный цикл маркера при fresh/wipe — недоспека. |
| 4 | Fold: `stage_rows = nrows`, не подмена на `done_rows` | **да** | §2.4 дословно; `done_rows` остаётся в диспетчере `:2200-2207`. |
| 5 | Эталон realiz **74 785 / md5 71947efe…** с финального `tmp3_corpus`; emb не в multiset | **нет** | «emb не в multiset» — да (§3.4). Числа/обоснование — **нет**: v2 оставил **74 982 / 57ad85de…** и объяснил разрыв с 74 785 как «дрейф данных, не QUALIFY». Это противоречит коду и A2 (`result-t1a2.md` §4.6: 74 982→74 785 — fold/QUALIFY; `takt-baseline.txt`: `74785\|71947efe…`). «Монолитный стейдж» по-прежнему путает: монолит пишет в `tmp3_corpus` с QUALIFY (`:1576-1817`), не в `tmp3_pdoc_stage`. §3.5 требует multiset финального `search_corpus` == §3.4 (74 982) — после fold это ложный FAIL или ложный эталон. |
| 6 | M1/M2: assert списка, wave=0, неполный order→mono, resume tail, сверка после finalize | **да** | §1.4 / §2.5 покрывают все пункты C1-3.1/3.2. |

**Итог по своим шести:** 5 из 6 внесены верно; пункт 5 (эталон приёмки) — отклонён с неверным обоснованием.

---

## 2. Новые проверки (элементы v2 vs код)

### (а) `CREATE OR REPLACE TABLE … AS SELECT … WHERE false` для unmatched

**Вердикт: легален и даёт нужную схему.**

- Доки SereneDB: CTAS + `CREATE OR REPLACE` (`sql/statements/create_table` — CTAS / OR REPLACE / Copying the Schema).
- В дереве уже есть тот же приём: `embed_missing.sql:108` — `CREATE OR REPLACE TABLE … AS SELECT * FROM … WHERE false`.
- `SELECT c.src_table, c.row_key FROM search_corpus c WHERE false` наследует типы колонок корпуса — та же пара, что текущий CTAS `:162-163`. Потребители (`edited_delta`, `ent_guard`, …) совместимы.
- `CREATE OR REPLACE` на каждом прогоне закрывает C4-П5 (нет накопления INSERT в старую таблицу).
- Запасной канон доков — `FROM t WITH NO DATA` / `LIMIT 0`; `WHERE false` не хуже для пустого старта.

Условие: `search_corpus` существует к моменту merge — всегда так после/при наличии боевого корпуса; на совсем пустой базе merge и сейчас смотрит в него.

### (б) Маркер `tmp3_pdoc_tail_done` и порядок порции → tail → finalize

**Вердикт: идея совместима с диспетчером; спецификация неполная.**

Текущий каркас `:2168-2209`:

1. mono `p_doc` (вне chunks);
2. `\gexec` порций `p_doc_chunk` + progress (`:2179-2196`);
3. `\gexec` `p_doc_finalize` при `rid_hi >= nrows AND done_rows = nrows` (`:2198-2209`).

Вставка tail **между (2) и (3)** стыкуется: `done_rows` по ширинам порций `1..nrows` уже полон без хвоста (C1-2.3) — хвост не должен входить в эту сумму; план это соблюдает.

Resume `:1536-1538` (`on_` по возрасту `tmp3_run` + наличию progress): при `on_` stage/progress не сносятся (`:1561-1567`). Маркер «пропускать помеченные» нужен, иначе повторный `p_doc_tail` раздует stage — план это фиксирует; finalize без маркера при непустом tail — fail-closed, закрывает дыру C3-A.

**Не дописано (блокирует «исполнять как написано»):**

1. **Wipe маркера/хвоста на свежем такте** (`NOT on_`): stage/progress чистятся (`:1561-1567`), а `tmp3_pdoc_tail*` — обычные таблицы; без `DELETE`/`CREATE OR REPLACE` старый маркер → skip tail при пустом stage → finalize с неполным stage или ложный STOP. Симметрия с wipe stage обязательна.
2. **Атомарность tail→маркер:** обрыв после INSERT в stage до INSERT маркера → resume снова зовёт tail → размножение. Нужен критерий идемпотентности (например, не звать tail, если stage уже содержит строки хвоста / или DELETE stage-хвоста перед повторным EXECUTE).
3. Точка в `\gexec`-списке и поведение при `ON_ERROR_STOP` — одной фразой «после порций» мало; образец — отдельный `SELECT … \gexec` между `:2196` и `:2198`.

### (в) Гейт покрытия `count(order)+tail == nrows`

**Вердикт: выражаем на имеющихся таблицах — да; формулировка опасна для исполнителя.**

Имеется: `tmp3_pdoc_order`, `tmp3_pdoc_tail(tbl,keyvals DISTINCT)`, `tmp3_entity_rows.nrows`, `query_table(tbl)`.

Корректная форма плана («count(order после DELETE) + **count(строк витрины с keyvals ∈ tail)**») — не тавтология и ловит рассинхрон DELETE↔tail. Её нельзя заменить на `count(order)+count(tail)` при **DISTINCT** keyvals: для класса `"|"` (2 776 строк, 1 keyvals) сумма будет `nrows−2776+1`.

Дешёвый эквивалент без повторного UNPIVOT витрины: до DELETE посчитать строки order с keyvals из collision-множества; после — `count(order)+deleted_rows = nrows`. Оба варианта штатны; план должен запретить `count(DISTINCT tail)`.

### (г) Dry-run такт №0 (`psql -f corpus_build.sql`) vs юнит-такт

**Вердикт: при штатной последовательности «выкат → dry-run → юнит» SKIP/hash не ломаются; есть оговорки.**

`build.sh:253-286`: `SKIP_BUILD=1` только при совпадении `build_sql_hash` (из файлов), `corpus_built_ts > mart_changed_ts`, непустом корпусе и наличии `tmp3_*`. Dry-run:

- **не** пишет `corpus_built_ts` (это `:339-342` после merge);
- **не** пишет `build_sql_hash` (postcheck в конце юнита);
- **пишет** `tmp3_corpus`, `tmp3_run` (`:2376`), `search_pdoc_formula`, метки `pdoc_*` в `search_quality`.

После выката нового SQL hash в файлах ≠ note в БД → юнит `SKIP_BUILD=0` → полная пересборка снова. Dry-run — чистая проверка, результат стейджа юнит пересоберёт. `corpus_built_ts`/`mart` не сдвигаются dry-run'ом → ложного SKIP из‑за №0 нет.

Свежий `tmp3_run` после успешного dry-run → на следующем build `on_=false` (возраст < 6 ч не достаточен один: нужно ещё `progress > 0` **и** ts старше 6 ч) — при `on_=false` progress/stage чанков сносятся. Ок для успешного dry-run.

**Риск:** оборванный dry-run (до `:2376`) оставляет progress/order/частичный stage; следующий юнит может включить resume от полусборки пробного прогона. План обязан: при ошибке №0 — сброс `tmp3_pdoc_progress`/`stage`/`tail*` или запрет resume до чистого прогона.

Merge freshness (`corpus_merge.sql:30-43`) смотрит на `tmp3_run`: успешный dry-run делает стейдж «свежим» для ручного merge — это как раз сценарий C3 pre-merge; сам юнит всё равно пересоберёт при смене hash.

---

## 3. Новые дыры, которые внёс v2

1. **Эталон §3.4/3.5 (главная).** Ложное «не QUALIFY / дрейф» закрепляет 74 982 / чужой md5 как критерий финального корпуса. Исполнитель по тексту плана либо отклонит правильный fold-результат, либо ослабит QUALIFY. Канон в репо: `takt-baseline.txt` / activeContext — **74 785 / 71947efe…**. Число 74 982 оставить только контролем витрины (как в C1).
2. **Жизненный цикл `tmp3_pdoc_tail` / `_done`:** нет wipe на `NOT on_`, нет идемпотентности при обрыве между INSERT хвоста и маркером (§2б).
3. **Гейт покрытия:** легко реализовать как `count(tail)` при DISTINCT — план не ставит запрет явно (§2в).
4. **Двойная полная сборка** (№0 + такт №1) — не дефект корректности, но план не говорит, что md5 №0 снимать с **`tmp3_corpus` после finalize** (не с `tmp3_pdoc_stage` и не с count витрины). Термин «стейдж» в §3.4 в проекте = pre-merge `tmp3_corpus` (C3), а числа взяты как у витрины/до-QUALIFY — внутренняя противоречивость v2.

Прочие добавления v2 (гейт размера хвоста >½ nrows → mono + `search_quality`; memory_limit 0.55 от `current_setting`; бэкап emb; `векторов_умрёт=0`; контракт «такт №1 ≲1 ч / не минуты») с кодом совместимы и дыр корректности множеств не открывают.

---

## 4. Вердикт

**План готов к исполнению — НЕТ**

Пять из шести обязательных правок C1 внесены полно. Блокер — пункт 5 (эталон + ложное обоснование без QUALIFY) плюс недоспека маркера хвоста на fresh/resume-обрыве. После правки §3.4/3.5 на финальный `tmp3_corpus`/`search_corpus` с каноном **74 785 / 71947efe…** (или честный пересъём монолитного `tmp3_corpus` после QUALIFY), явного wipe/идемпотентности `tmp3_pdoc_tail*`, и запрета `count(DISTINCT tail)` в гейте покрытия — повторный круг D/C по этим трём пунктам достаточен; направление этапов 1–2 по-прежнему принимать.

*Конец T1-D1.*
