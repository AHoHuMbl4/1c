# Ф6.1 — фактура: гибридный RRF в SQL на SereneDB 26.08.1

Снято 23.08 на боевой okna (`gpu-erw:2202`, `psql :7890`, SereneDB **26.08.1**).
Код `serene_ask.py` не менялся. База: только `SELECT` + TEMP в сессии.
Вопросы: 20 строк из `ubuntu/serenedb/ab-gold-okna.tsv` (`ask_journal_text` на
бою ещё нет). Векторы вопросов моделью не считались — прокси `emb` из корпуса.

## 1. Что говорят доки (синтаксис)

Отдельного оператора «hybrid» / «RSF» **нет**. Штатный путь — SQL-паттерн RRF.

| Раздел | URL | Суть |
|---|---|---|
| Hybrid Search › Score fusion | https://docs.serenedb.com/sql/indexes/inverted/hybrid-search#score-fusion | BM25-ветка + векторная, `ROW_NUMBER()`, `SUM(1.0/(60+rank))` |
| Cookbook › Reciprocal Rank Fusion | https://docs.serenedb.com/cookbook/search/reciprocal-rank-fusion | тот же каркас; `RANK()`, `k=60` по умолчанию статьи/ES |
| Cookbook › Semantic and Hybrid Search | https://docs.serenedb.com/cookbook/search/hybrid-search#fuse-both-with-reciprocal-rank-fusion | BM25 `ORDER BY s DESC`, вектор `ORDER BY dist` ASC |
| Ranking › Combining ranked queries | https://docs.serenedb.com/sql/indexes/inverted/ranking#combining-ranked-queries | отсылает к Hybrid + RRF |

Каркас из доков (Hybrid Search, score fusion):

```sql
WITH fused AS (
  SELECT id, ROW_NUMBER() OVER (ORDER BY s DESC) AS rank FROM (
    SELECT id, BM25(catalog_idx.tableoid) AS s
    FROM catalog_idx WHERE name @@ ts_phrase('red')
    ORDER BY s DESC LIMIT 100
  ) lex
  UNION ALL
  SELECT id, ROW_NUMBER() OVER (ORDER BY dist) AS rank FROM (
    SELECT id, emb <-> [1.0,0.0,0.0]::FLOAT[3] AS dist
    FROM catalog_idx ORDER BY dist LIMIT 100
  ) vec
)
SELECT id FROM fused
GROUP BY id
ORDER BY SUM(1.0 / (60 + rank)) DESC, id
LIMIT 3;
```

`serene_ask._fused_candidates` уже повторяет cookbook (`RANK()`, `RRF_K=60`,
`SUM(1.0/(k+rank))`), но по **поверхностям сущностей** (alias / card / emb меток),
не по строкам корпуса.

## 2. Статус на живой 26.08.1

Индексы на `search_corpus`: `search_idx` (текст) + `corpus_ivf_idx` (`metric='ip'`),
отдельно — не один inverted с `emb`, как в учебном примере доков. Это **не
блокирует** паттерн: ветки читают разные индексы и сливаются `UNION ALL`.

| Паттерн | Статус | Замер |
|---|---|---|
| BM25 `FROM search_idx … bm25(search_idx.tableoid)` | ✅ | мс–десятки мс |
| kNN `FROM corpus_ivf_idx ORDER BY emb <#> q` (без `WHERE emb IS NOT NULL`) | ✅ | ~1,7 с top-10 (smoke); ~1,7–2,4 с top-50 в серии |
| RRF oneshot BM25+IVF, `k=60`, `ROW_NUMBER` или `RANK` | ✅ | smoke ~**1673–1687** мс |
| Filtered ANN `FROM search_idx WHERE doc @@ … ORDER BY emb <#>` | ✅ | ~277 мс (пример `клиент`) |
| `ORDER BY emb` через `search_idx` (lookup таблицы) | ✅ | ~2,3 с top-3 |
| `doc @@ …` на базовой `search_corpus` (не индекс) | ❌ | дословно: `TSQUERY expression evaluated outside an \`@@\` match against an inverted-indexed column.` |
| Отдельный оператор hybrid/RSF | нет в доках и на сборке | — |

Метрика IVF = `ip` → оператор расстояния **`<#>`** (не `<=>`; иначе тихий seq scan —
см. Ф5 / `VECTOR_DECISION`).

## 3. Эквивалентность python-RRF vs SQL-RRF (20 вопросов)

Формула python (`serene_ask.py`, `RRF_K=60`):

`SUM(1.0/(60 + RANK()))` по `UNION ALL` веток, затем `ORDER BY rrf DESC`.

Сравнение на корпусе (ключ `src_table|row_key`, top-10, окно ветки 50):

| Пара | Множество (доля пересечения) | Порядок (доля совпадения позиции) |
|---|---|---|
| py `RANK` на TEMP-ветках vs docs `ROW_NUMBER` на тех же ветках | **1.000** (min 1.0) | **1.000** |
| py `RANK` на TEMP vs oneshot SQL `RANK` (живой BM25+IVF) | **0.995** (min 0.9) | **0.995** |

Единственный частичный разъезд: qid 17 (`продаж`) — **9/10** множества/порядка
(tie-break / пересчёт ветки oneshot vs зафиксированные TEMP). Остальные 19/20 —
полное совпадение top-10.

Пометки:

- Вектор вопроса — **прокси** из корпуса (строка с лексическим попаданием, иначе
  fallback любой `emb`). Не эквивалент боевому `ai_embed` вопроса.
- Лексическая ветка пуста у **16/20** вопросов (`продали`, `наторговали`,
  `клиентов`… не бьют `search_idx` без стемминга/синонимов) → слияние часто
  vector-only; формула RRF при этом всё равно совпадает.
- Источник текстов: gold TSV, не журнал.

## 4. Что блокирует / не блокирует перенос в путь ответа (Ф6.1)

**Не блокирует синтаксис:** штатный RRF в SQL на 26.08.1 работает; формула
тождественна нынешнему python-RRF (`k=60`, `RANK`/`ROW_NUMBER` на наших данных
неразличимы при детерминированном tie-break).

**Остаётся для Ф6.1 (код/приёмка, не синтаксис):**

1. Реальный emb вопроса (модель), не прокси.
2. Корпусная ANN как **четвёртая поверхность кандидатов** (`src_table`), а не
   сырой top-k строк — склейка с alias/card/near_tables.
3. Бюджет латентности: ~1,7–2,4 с на гибрид корпуса поверх текущего пути.
4. Лексика разговорных глаголов по корпусу без стемминга/синонимов — пустая
   BM25-нога (старая проблема, не новая у RRF).
5. Не ставить `WHERE emb IS NOT NULL` на IVF-ветку (ловушка Ф5, ~1,4 с).

## 5. SSH-бюджет разведки

4 вызова на okna: (1) schema/version, (2) smoke hybrid, (3) тяжёлый прогон —
сервер оборвал соединение mid-file, (4) lean 20q — успех. CREATE/DROP только TEMP.
