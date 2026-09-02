# R3: дифф X1+X2 — потеря строк/векторов

Аудитор: красная команда R3. Материал: `git diff ubuntu/serenedb/` (не
закоммичен) + контракт §0.3–0.4 / приёмка §3.3–3.5 плана
`docs/audit/TAKT_SPEED_PLAN_2026-09-02.md`. Серверы не трогались. Файлы кода не
правились.

## Найденные пути потери

### P1. Fresh-wipe сносит только что собранный V5-хвост (критично)

- **Триггер:** чистый прогон (`on_ = false`: нет `tmp3_pdoc_progress` или
  `tmp3_run` старше 6 ч). Типичный такт №0 / первый заход юнита №1 после
  успешного finalize предыдущей сущности (progress уже счищен).
- **Механика:**
  1. `corpus_build.sql:1585-1593` — `INSERT INTO tmp3_pdoc_tail` коллизионные
     keyvals;
  2. `1595-1599` — `DELETE` этих строк из `tmp3_pdoc_order`
     (`IS NOT DISTINCT FROM`);
  3. `1667-1669` — при `NOT on_` снова `DELETE FROM tmp3_pdoc_tail` для всех
     tbl из `tmp3_pdoc_chunks`.
- Жизненный цикл скопирован с progress/stage, но **хвост — вход диспетчера
  (как order/chunks), а не накопитель исполнения**. chunks/order на fresh не
  сносятся после заполнения; tail — сносится. Диспетчер
  `:2542-2548` читает пустой `tmp3_pdoc_tail` → `p_doc_tail` не зовётся.
- **Следствие:** в stage попадают только уникальные keyvals из порций;
  коллизионные строки (уже вычеркнутые из order) **не собираются**.
- **file:line:** `ubuntu/serenedb/corpus_build.sql:1585-1593` → `:1667-1669` →
  `:2542-2548` → stage_gate `:2407-2414`.
- **Ловится ли:** coverage-гейт (`:1601-1612`) — **нет** (считается до wipe).
  `tail_gate` (`:2415-2420`) — **нет** (при пустом tail условие
  «хвост есть ∧ маркера нет» ложно). `stage_gate` (`stage_rows <> nrows`) —
  **да**, error на finalize. До клиента молча не уходит, но **V5 на свежем
  такте неработоспособен**; сущность падает в `build_failed` / роняет такт.
- **Повтор в одном юните (№0→№1):** post-finalize `:2569-2572` чистит
  tail/_done; следующий `corpus_build` снова INSERT→wipe. То же.

### P2. `kv.keyvals IN (SELECT …)` не матчит SQL NULL (латентно)

- **Триггер:** в `tmp3_pdoc_tail` / `tmp3_pdoc_order` оказывается `keyvals IS NULL`
  (коллизия «пустых» ключей). Коллизии считаются через
  `IS NOT DISTINCT FROM` (`:1561`, `:1598`), а отбор строк в
  `p_doc_chunk` / `p_doc_tail` — через `IN` (`:1983-1986`, `:2213-2216`).
- В SQL `NULL IN (…)` / `NULL IN (SELECT NULL)` → UNKNOWN → строка не берётся.
  Order-DELETE по `IS NOT DISTINCT FROM` при этом уже убрал такие строки из
  порций.
- **file:line:** `corpus_build.sql:2213-2216` (tail); зеркало chunk `:1983-1986`.
- **Ловится ли:** coverage — нет (арифметика до исполнения); stage_gate — **да**.
- **Практика после `UNPIVOT INCLUDE NULLS` + `∅`:** полный NULL-keyvals маловероятен
  (string_agg с непустыми сегментами). Но план §2.5/M2 явно требует NULL/«∅»;
  фильтр `IN` с этой спецификацией **расходится**. Замок M2 обязан поймать
  фикстурой NULL keyvals — в диффе замка нет.

### P3. Двойная вставка (tail + порция) — не найдена

- Порции читают только остаток `tmp3_pdoc_order` (уники); хвост — только
  `tmp3_pdoc_tail` (коллизии после HAVING count>1). Пересечения keyvals нет
  по построению.
- Resume: порция↔хвост — атомарный
  `BEGIN; p_doc_tail; INSERT done; COMMIT` (`:2542-2543`) закрывает окно
  «stage есть, маркера нет». Хвост↔finalize — `tail_gate`. Маркер↔finalize —
  повтор finalize идемпотентен по `NOT EXISTS corpus`.
- **Ловится ли:** заложено в диспетчер/гейты. Отдельно: атомарность зависит от
  Multi-Statement Transactions движка (план ссылается на доки) — в этом диффе
  не верифицировалось на живом инстансе (серверы вне мандата).

### P4. DELETE order по tail + уникальный `keyvals=NULL`

- DELETE (`:1595-1599`) только при членстве в `tmp3_pdoc_tail`. Уникальный NULL
  (count=1) в tail не попадает → **не удаляется**. Ложных потерь уникальных
  NULL-ключей этим DELETE нет.

### P5. Coverage-гейт обходит wipe и mono-соседей

- Гейт (`:1601-1612`) только для `NOT oversize` ∧ не mono, сразу после DELETE
  order. После него wipe P1 опустошает tail без повторной проверки.
- Сущность без коллизий / mono / oversize — гейт не смотрит (и не должен:
  mono уходит в `p_doc`, безколлизионные — полный order).
- «collision посчитан, потом order ещё порезали» — второго DELETE order в диффе
  нет. Риск не в дорезании order, а в **уничтожении хвоста** (P1).

### P6. Вектора / content_hash / row_key / merge xfer

- **build:** `p_doc_tail` — зеркало тела chunk; `keyed` / `pieces` / `doc` /
  finalize `sha1` / `corpus_content_hash(doc)` / суффикс `#N` — те же формулы,
  что у chunk. Селектор keyvals в row_key/doc не входит (§2.6).
- **merge diff:** только `SET memory_limit` (0.55× current_setting) + нарезка
  `p_merge_unmatched` по сущности + перенос `edited_delta` после unmatched.
  `tmp3_merge_vec_budget` / `emb_xfer` / DELETE search_corpus / MERGE emb —
  **не в диффе**.
- Пути потери векторов этим диффом **не открыты**. Критерии §3.5 (дыры на
  живых ключах бэкапа) от V5-бага P1 страдают косвенно: сущность не попадёт в
  корректный `tmp3_corpus` → merge/эмбед не доедут штатно (стоп раньше).

### P7. Lifecycle tail/_done после успеха → повторный build

- Post-finalize `:2569-2572` чистит tail/_done при наличии corpus — корректно.
- Formula-смена / pre-collision DELETE `:1539` — корректно как сброс перед
  пересчётом.
- Сломан только fresh-wipe **после** пересчёта (P1). При `on_=true` (докатка)
  wipe не срабатывает — хвост жив; первый заход после чистого успеха — нет.

### P8. Mono при «живых» chunks — не найдена

- Неполный order / oversize → каскад DELETE chunks/formula/entity/order/tail
  (`:1575-1581`). Mono и живые chunks одновременно не остаются.

## Векторный контур (итог по линзе)

| Участок | Тронут диффом? | Риск потери emb |
|---|---|---|
| content_hash / row_key (keyed/pieces/doc) | нет (хвост = копия) | нет |
| vec_budget / xfer / DELETE corpus | нет | нет |
| unmatched split | да (эквивалент по предикату) | нет (не emb-путь) |

## Итог

| Вопрос | Ответ |
|---|---|
| **Потерь нет** | **НЕТ** |
| **Дифф принять** | **НЕТ** |

Блокер: **P1** — на каждом свежем такте V5-хвост уничтожается до диспетчера;
коллизионные строки не попадают в stage. Гейт покрытия и `tail_gate` это не
ловят; `stage_gate` роняет finalize (п.13 как молчаливая дырка в прод-корпус
не проходит, но контракт §0.3/§2.1–2.3 и приёмка §3.4 неисполнимы).

Минимальная правка (вне мандата R3, только адрес): **убрать**
`DELETE FROM tmp3_pdoc_tail` / `_done` на ветке `NOT on_` (`:1667-1672`), либо
перенести INSERT хвоста **после** fresh-wipe; оставить сброс на formula
(`:1457-1463`), pre-collision (`:1539`), mono (`:1576-1577`) и post-finalize
(`:2569-2572`). Дополнительно: заменить `IN` в `p_doc_tail`/`p_doc_chunk` на
`EXISTS (… IS NOT DISTINCT FROM …)` под M2/NULL.
