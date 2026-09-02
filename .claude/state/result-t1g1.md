# G1: фикс-дифф X3 — снятие блокеров R3/R4

Аудитор: красная команда G1. Контекст нулевой. Серверы не трогались.
Правки — только этот отчёт. Материал: `corpus_build.sql` / `corpus_merge.sql`
(незакоммиченный дифф), `result-t1r{1,2,3,4}.md`, замки M1/M2, MCP
`serenedb-docs` (Multi-Statement Transactions).

---

## 1. BUG-1 (fresh-wipe tail) — снят?

**ДА.**

Порядок операторов в файле (пройден):

| Шаг | file:line | Поведение |
|---|---|---|
| pre-decide | `:1539` | `DELETE FROM tmp3_pdoc_tail WHERE tbl IN (order)` — сброс перед пересчётом |
| decide INSERT | `:1585-1593` | план V5-хвоста |
| DELETE order | `:1595-1599` | коллизии вычеркнуты из порций |
| fresh-wipe | `:1667-1670` | **только** `tmp3_pdoc_tail_done` при `NOT on_`; комментарий «артефакт плана» |
| диспетчер | `:2539-2546` | `EXECUTE…; INSERT done` по живому `tmp3_pdoc_tail` |

- **Fresh (`on_=false`):** хвост после INSERT **не** стирается wipe'ом → доживает до диспетчера. Замок: `test_fresh_battle_order_bug1` (decide → wipe runtime-only → chunk+tail+finalize; `fresh-wipe не снёс план хвоста`).
- **Resume (`on_=true`):** ветка wipe `_done` не срабатывает → маркер доживает → диспетчер скипает по `NOT EXISTS (tail_done)`. Замок: `test_resume_and_fresh` + повтор в `test_battle_tail_multistmt`.
- **Старый хвост (прошлый такт, сущность не пересобирается):** ложного диспатча **нет**.
  - `tmp3_pdoc_chunks` — `CREATE OR REPLACE` (`:1477`): только текущие сущности.
  - Guard диспетчера: `EXISTS(chunks)` ∧ `NOT EXISTS(tmp3_corpus)` ∧ `NOT EXISTS(done)`.
  - Сущность вне текущего chunks → `EXISTS(chunks)` ложно → `\gexec` пуст.
  - Сущность в текущем order → `:1539` сносит старый план до INSERT.
  - Mono → `:1576` сносит tail.
  - Уже в `tmp3_corpus` → `NOT EXISTS(corpus)` ложно.
  - Orphan-строки в `tmp3_pdoc_tail` без chunks возможны после обрыва, но **не диспатчатся** (см. §5).

---

## 2. BUG-2 (BEGIN внутри multi-statement) — снят?

**ДА.**

- Боевая строка `:2539-2541`: два statement через `;`, **без** `BEGIN`/`COMMIT`.
- **Доки** (`Sql › Statements › Transaction Management › Multi-Statement Transactions`,
  https://docs.serenedb.com/sql/statements/transactions#multi-statement-transactions):
  «When multiple SQL statements are submitted together (e.g., separated by
  semicolons), they are executed within a single **implicit** transaction. If any
  statement fails, all preceding statements in the batch are rolled back.»
- Замок M2 **исполняет именно её:** `test_battle_tail_multistmt` — тот же
  `SELECT 'EXECUTE p_doc_tail('||…||'); INSERT … done …' … \gexec` с теми же
  тремя guard'ами, что в файле; оффлайн-греп запрещает
  `BEGIN TRANSACTION; EXECUTE p_doc_tail(`.
- Оговорка (не блокер): негатив «обрыв после EXECUTE → stage без done» в замке
  **не** смоделирован отдельно — атомарность держится на доке + форме посылки.
  Вспомогательный `_run_chunk_tail_finalize` по-прежнему шлёт EXECUTE/INSERT
  раздельными строками UNION — это не боевой путь; боевой закрыт отдельным тестом.

---

## 3. R1-D2: `error` на неизвестный суффикс vs `'50.0 GiB'`

**Не ломает штатный формат. Пустой суффикс = байты — ДА (намеренно).**

`corpus_merge.sql:20-29`:

- `unit_l = lower(trim(regexp_replace(s, '^[0-9.]+\s*', '')))` → для
  `'50.0 GiB'` → `'gib'` ∈ whitelist → `n * 1024³`, наружу `'… GiB'`.
- `NOT IN ('', 'b', 'kb', …)` → `error('…неизвестная единица…')` — ловит `%` и
  мусор (закрытие D2).
- `ELSE` / пустой `unit_l` / `'b'` → байты + суффикс `'B'` (комментарий в SQL).

Замок M1: текстовый needle на `error` + живая формула на `current_setting`.

---

## 4. R2-D1: v8c согласованность / хвосты `v8b`

**ДА, согласованы.**

- Комментарий `:1432` и литерал формулы `:1438` — оба `'v8c'`.
- Греп исполняемого контура `ubuntu/serenedb/**/*.{sql,py}`: литералов `'v8b'`
  **нет** (тестовые decide-файлы и замок тоже на `v8c`).
- Остатки `'v8b'` — только история/стейт/промты (`.claude/state/*`, старые
  result-*), на рантайм не влияют.
- Эффект бампа: formula mismatch → wipe progress/stage/tail/_done (`:1448-1464`)
  до `on_` — mid-resume через выкат со старым v8b сбрасывается.

---

## 5. Новые дыры фикса?

**НЕТ блокеров.** Зафиксированные остатки (не введённые wipe-фиксом как
регрессия корректности):

| # | Суть | Блокер? |
|---|---|---|
| A | R4 **BUG-3** жив: pre-decide `:1539` чистит `tail`, не `tail_done`. На resume при потерянном stage + живом done — хвост скипается, `tail_gate`/stage_gate ломают сущность. На fresh `_done` теперь сбрасывается → самолечение на свежем такте. | нет (medium, был до X3) |
| B | Orphan `tmp3_pdoc_tail` для сущности вне текущего `chunks` после обрыва — мёртвые строки, диспатч закрыт guard'ом. | нет |
| C | R3 **P2** (`keyvals IN` vs NULL) — не тронут фиксом. | нет (латент) |
| D | Замок не эмулирует fail mid-batch для отката multi-statement. | нет (дока + форма) |

Нового пути «хвост уничтожен до диспетчера» / «BEGIN внутри неявной txn» /
«`80%`→байты» / «formula id не бампнут» — **нет**.

---

## Итог по пунктам

| Вопрос | Ответ |
|---|---|
| 1. BUG-1 снят? | **ДА** |
| 2. BUG-2 снят? (дока + замок на боевую строку) | **ДА** |
| 3. R1-D2: `'50.0 GiB'` цел; `''`=`B`? | **ДА** / **ДА** |
| 4. R2-D1: v8c согласован; исполняемых `v8b` нет? | **ДА** |
| 5. Новые дыры-блокеры фикса? | **НЕТ** |

**Фикс принять — ДА**
