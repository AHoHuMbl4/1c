# G2: фикс-дифф X3 — вектора и порядок жизни хвоста

Аудитор: красная команда G2. Контекст нулевой. Серверы не трогались.
Правки — только этот отчёт. Материал: незакоммиченный `corpus_build.sql` /
`corpus_merge.sql`, `result-t1r3.md`, `result-t1r4.md` (BUG-3 — fail-closed край).

---

## 0. Уточнение предпосылки сценария

В промте: «без fresh-wipe маркёра». **Это неверно для X3.**

X3 снял только wipe **плана** (`tmp3_pdoc_tail`) на ветке `NOT on_`.
Wipe **маркёра** оставлен (`:1667-1670`):

```sql
-- Хвост — артефакт плана … на fresh не стираем …
DELETE FROM tmp3_pdoc_tail_done d
WHERE EXISTS (SELECT 1 FROM tmp3_pdoc_chunks c WHERE c.tbl = d.tbl)
  AND NOT (SELECT on_ FROM tmp3_resume_pdoc);
```

Сценарий «маркер выжил + stage свеж → skip tail → stage_rows≠nrows» требует
одновременно живого `_done` и пустого stage на **свежем** (`on_=false`) заходе.
На `on_=false` wipe `_done` как раз отрабатывает **до** диспетчера. Ниже — полный
разбор №0→№1.

---

## 1. Цикл «такт №0 (сухой) → юнит №1»

Сухой №0 = `psql -f corpus_build.sql` без merge (§3.4 плана). Finalize пишет в
`tmp3_corpus`, не в `search_corpus`.

### 1.1 Последовательность внутри успешного №0

| # | file:line | Что происходит с V5-сущностью |
|---|---|---|
| 1 | `:1539` | pre-decide: `DELETE` старого `tmp3_pdoc_tail` для tbl ∈ order |
| 2 | `:1585-1593` | INSERT плана хвоста |
| 3 | `:1617-1619` | `on_` = (tmp3_run старше 6ч) ∧ (progress>0). После чистого старта progress=0 → **on_=false** |
| 4 | `:1658` | `DELETE FROM tmp3_corpus` (весь стейдж сборки) |
| 5 | `:1660-1666` | wipe **stage** + **progress** (fresh) |
| 6 | `:1668-1670` | wipe **`_done`** (fresh); **tail-план не трогаем** |
| 7 | `:2520-2537` | порции → stage |
| 8 | `:2539-2546` | `EXECUTE p_doc_tail; INSERT _done` (multi-statement без BEGIN) |
| 9 | `:2548-2559` | `p_doc_finalize` → строки в **tmp3_corpus** |
| 10 | `:2561-2570` | post-finalize: stage/progress/**tail**/_**done** чистятся **WHERE EXISTS corpus** |
| 11 | `:2730` | `tmp3_run = now()` |

Итог №0 (успех): `tmp3_corpus` заполнен; для финализированных V5 —
`tail=∅`, `_done=∅`, `stage=∅`, `progress=∅`.

Промт верно угадывает: finalize №0 пишет в `tmp3_corpus` → post-finalize
(`:2567-2570`) **отработал** и снял и хвост, и маркер. Merge для этого не нужен.

### 1.2 Старт юнита №1 (снова corpus_build, затем merge)

| # | Что | Следствие для scare-сценария |
|---|---|---|
| 1 | decide `:1539` + INSERT `:1585` | новый план хвоста; старого уже нет |
| 2 | `on_` | progress=0 после №0 → **on_=false** всегда (даже при свежем tmp3_run) |
| 3 | `:1658` | `DELETE tmp3_corpus` — сносит продукт сухого №0 (ожидаемо: юнит пересобирает) |
| 4 | wipe stage/progress/`_done` | маркер, даже если бы выжил, **стёрт** |
| 5 | диспетчер | `_done` пуст → хвост **зовётся**; stage собирается с нуля включая коллизии |
| 6 | finalize + post-finalize | снова согласованная чистка |
| 7 | merge | читает новый `tmp3_corpus` |

### 1.3 Scare «маркер №0 + fresh stage №1»

Цепочка, которой боится промт:

1. маркер выжил из №0 → **ложно** после успешного finalize (шаг 10);
2. decide перезаписал tail, `_done` скипнул диспетчер → на №1 `_done` пуст
   (шаг 4 wipe) → skip **не** случается;
3. stage fresh без хвостовых строк → stage_gate → **не достигается**: хвост
   исполняется.

**Вывод: между успешным №0 и №1 хвост/маркёры согласованы. Дыры нет.**

### 1.4 Стал ли R4-BUG-3 «реальнее»?

**Нет.** BUG-3 = pre-decide сносит `tail`, но не `_done`, при **`on_=true`**
(resume), когда stage потерян иным путём. X3:

- не трогал `:1539` (по-прежнему только tail);
- **сохранил** fresh-wipe `_done` при `NOT on_`;
- путь №0→№1 идёт с `on_=false` → wipe маркера обязателен.

BUG-3 остаётся тем же fail-closed краем resume (stage_gate / tail_gate роняют
сущность), не новым прод-путём после снятия wipe плана.

### 1.5 Обрыв между finalize и post-finalize (край, не №0→№1)

Если скрипт умер после INSERT в corpus, но до `:2567-2570`:

- в corpus есть строки; stage/progress/tail/_done ещё живы;
- повтор с `on_=false` (типично, если progress>0, но tmp3_run свежий → первая
  конъюнкция ложна): wipe corpus+stage+progress+_done, полная пересборка — чисто;
- повтор с `on_=true`: диспетчер видит corpus → skip chunk/tail/finalize; post-finalize
  чистит leftovers по EXISTS corpus — чисто.

Молчаливой дыры нет.

---

## 2. Минимальный фикс

**Не нужен** по мандату G2 (дыра в порядке жизни хвоста №0→№1 не найдена).

BUG-3 по-прежнему допустим как fail-closed край (решение оркестратора); адрес
при желании — симметричный `DELETE FROM tmp3_pdoc_tail_done` рядом с `:1539`,
но это **не** блокер X3 и **не** следствие снятия wipe плана.

---

## 3. Вектора: фикс-дельта не открывает путей потери?

| Участок | В дельте X3? | Риск потери emb |
|---|---|---|
| content_hash / row_key / тело p_doc_tail | зеркало chunk; селектор keyvals не в hash (§2.6) | нет |
| fresh-wipe: не стирать plan | да | нет; наоборот закрывает R3-P1 (неполный stage → кривой corpus) |
| диспетчер без BEGIN | да | нет silent-loss: обрыв → rollback батча по доке Multi-Statement / либо stage_gate |
| formula `v8b`→`v8c` | да | сброс resume старого кода; hash строк не меняет |
| merge: unmatched split / edited_delta порядок | да (X1/X2, не emb-путь) | нет |
| merge: memory_limit fail-closed unknown unit | да (X3) | нет; штатные GiB/MiB… проходят |
| vec_budget / emb_xfer / DELETE search_corpus / MERGE emb | **не в диффе** | нет |

Критерии §3.5 (дырка = ключ бэкапа в финальном corpus с emb IS NULL) этим диффом
не ослабляются. Починка BUG-1 снижает риск неполного `tmp3_corpus` до merge.

---

## Итог

| Вопрос | Ответ |
|---|---|
| №0→№1: хвост/маркёры согласованы? | **ДА** |
| Scare «живой _done + fresh stage» после X3? | **Нет** (маркер на fresh по-прежнему стирается; после успеха №0 его уже нет) |
| BUG-3 стал реальнее? | **Нет** |
| Новые пути потери векторов? | **Нет** |
| **Фикс принять** | **ДА** |
