# 07. rrf-vectors

Участок: `ubuntu/serenedb/serene_ask.py:3136–3730` (+ `_shares_chars`/`_ngrams` до `:3740`).

## Зачем участок нужен

Сливает кандидатов сущностей (`src_table`) из нескольких поверхностей поиска по RRF; отдельно отдаёт kNN по меткам/карточкам (`near_tables`), строки корпуса/индекса для показа (`rows_of`), отличительные термы (`signal_terms`), формулировки уточнения/отказа моделью, HTTP-реранк списка документов и резолв слова человека в значения `resolver_index` (вектор → гарда букв → реранк).

## Входы

| Функция | Аргументы |
|---|---|
| `_fused_candidates` | `exprs`, `kind_text`, `question`, `limit`, `diag=None` |
| `_rrf_entity_branches` | `exprs`, `kind_text`, `question`, `limit` |
| `_rrf_corpus_branch` | `vec`, `limit` |
| `_fused_sql_rrf` / `_fused_python_rrf` | `branches`, `limit` |
| `near_tables` | `text`, `limit` |
| `rows_of` | `src_table`, `match`, `preds`, `limit`, `measure=None` |
| `signal_terms` | `src_table`, `match`, `top` |
| `clarify_text` | `question`, `opts` (элементы с ключами `label`, `distinct_by`) |
| `refuse_text` | `question` |
| `rerank` | `query`, `docs` |
| `_resolver_psql` | `sql` |
| `_resolve_values_literal` / `_resolve_values_corpus` / `resolve_values` | `term` |
| `_corpus_ivf_ready` / `_resolver_ivf_ready` | нет |

Имена модуля, читаемые здесь (задания вне среза): `ASK_SQL_RRF`, `ASK_RESOLVER_IVF`, `RRF_K`, `CORPUS_IVF_IDX`, `RESOLVER_IVF_IDX`, `TOPK`, `SCORER`/`SCORERS`, `ALIAS_INDEX`, `CARD_INDEX`, `CARD_FIELDS`, `CARD`/`TABLES`/`CORPUS`/`INDEX`, `RERANK_*`, `RESOLVER_DSN`/`RESOLVER_PW`, `EMBED_UA`. В срезе заданы: `RESOLVE_NEAR` (`ASK_RESOLVE_NEAR`, умолч. `"12"`, `:3586`), `RESOLVE_KEEP` (`ASK_RESOLVE_KEEP`, умолч. `"3"`, `:3587`).

## Порядок работы

1. `_corpus_ivf_ready` (`:3136`): кэш 60 с → `emb_ready(CORPUS)` → `psql` `duckdb_indexes()` по `CORPUS_IVF_IDX`.
2. `_resolver_ivf_ready` (`:3153`): то же через `_resolver_psql` и `RESOLVER_IVF_IDX` / таблица `"resolver_index"`.
3. `_rrf_entity_branches` (`:3175`): при непустых `exprs` — SQL-ветви alias (`aliases @@ expr`) и card (`CARD_FIELDS @@ expr`) со скорером `SCORERS[SCORER]`; затем до двух kNN-веток `emb <=> _vec(text)` по `CARD` или `TABLES` для `question` и `kind_text`.
4. `_fused_candidates` (`:3246`): собирает ветви; если пусто → `None`. Если `ASK_SQL_RRF` и IVF корпуса готов и `_vec(question)` ок — добавляет `_rrf_corpus_branch` (`emb <#>` по `CORPUS_IVF_IDX`, топ `TOPK`, агрегат `count` по `src_table`) и зовёт `_fused_sql_rrf`; при `RuntimeError` — снова entity-ветви и `_fused_python_rrf`. Иначе — `_fused_sql_rrf` без corpus; ошибка → `None`.
5. `_fused_sql_rrf` (`:3219`): один `psql` `UNION ALL` + `SUM(1.0/(RRF_K+rank))`, лимит `limit * len(branches)` → список `src_table`.
6. `_fused_python_rrf` (`:3227`): каждая ветвь отдельным `psql`, скоры в dict, сортировка; пусто → `None`.
7. `near_tables` (`:3300`): пустой `text`/`src` → `[]`; иначе `ORDER BY emb <=> _vec(text)`.
8. `rows_of` (`:3341`): `WHERE` = `match`+`preds`+`src_table`+не-папка; источник `INDEX` если `match` иначе `CORPUS`; подсветка или `doc`; сортировка bm25 / `nums[measure]` / `row_key`.
9. `signal_terms` (`:3408`): SQL significant-terms по `refs` в `INDEX`.
10. `clarify_text` / `refuse_text` (`:3454`, `:3482`): `ds_chat` с `CLARIFY_SYS`/`REFUSE_SYS`; отказ дополнительно режет цифры через `_norm_numbers`.
11. `rerank` (`:3507`): без `query`/`docs`/`RERANK_KEY` → `[]`; POST на `RERANK_URL` (тело по `RERANK_API`); успех → список индексов; сбой → `[]` + stderr.
12. `resolve_values` (`:3663`): нет `emb_ready("resolver_index")` или падение `_vec` → `[]`; IVF-путь или exact `emb <=>`; фильтр `_shares_chars`; `rerank` → до `RESOLVE_KEEP`.
13. `_resolve_values_literal` / `_resolve_values_corpus` (`:3590`, `:3637`): в срезе определены; из среза не вызываются (зов снаружи, ~`:2715–2720`).

## Выходы

| Что | Кому |
|---|---|
| список `src_table` / `None` от `_fused_candidates` | `candidate_tables` (`:3121`) |
| список от `near_tables` | fallback в `candidate_tables` (`:3128–3129`); SQL-аналог внутри RRF-веток |
| строки `rows_of` | путь ответа (`:13803`, `:14415` и др.) |
| термы `signal_terms` | сбор подсказки выбора сущности (`:8239`) |
| текст `clarify_text` / `refuse_text` | уточнение / отказ ответа |
| порядок `rerank` | `resolve_values`; также оси/сущности вне среза |
| значения `resolve_values` | сбор match/предикатов (~`:2715`) |
| `_resolver_psql` | IVF-ready, resolve_*, и др. вне среза |

## Обращения наружу

**SQL через `psql`:** IVF corpus ready (`:3144`); ветви/RRF (`:3221`, `:3232`); `near_tables` (`:3333`); `rows_of` (`:3369`); `signal_terms` (`:3423`); `_resolve_values_corpus` count (`:3652`).

**SQL через `_resolver_psql` (`psql`+`RESOLVER_DSN`):** IVF resolver ready (`:3166`); literal LIKE (`:3601`); IVF/`resolver_index` kNN (`:3690`, `:3695`).

**HTTP:** `rerank` → `urllib.request.urlopen` POST `RERANK_URL` timeout 30 (`:3535–3541`).

**Языковая модель:** `clarify_text` → `ds_chat` max_tokens=120 (`:3467`); `refuse_text` → `ds_chat` max_tokens=60 (`:3500`). `PICK_SYS` (`:3376`) в срезе только объявлен, вызовов нет.

**Эмбеддинг:** `_vec(...)` в ветвях RRF, `near_tables`, `resolve_values` (реализация `_vec` вне среза).

## Переключатели

| Имя | Где влияет в срезе | Умолч. (задание модуля) |
|---|---|---|
| `ASK_SQL_RRF` | `:3274` — 5-я corpus-ветвь + SQL-RRF | `'0'` → False (`:3762`) |
| `ASK_CORPUS_IVF_IDX` | имя индекса | `'corpus_ivf_idx'` (`:3763`) |
| `ASK_RESOLVER_IVF` | `:3689` IVF vs exact | `'0'` → False (`:3768`) |
| `ASK_RESOLVER_IVF_IDX` | имя индекса | `'resolver_ivf_idx'` (`:3769`) |
| `ASK_RRF_K` | формула RRF | `'60'` (`:3759`) |
| `ASK_TOPK` | окно ANN корпуса в ветви | `'40'` (`:113`) |
| `ASK_SCORER` | bm25/др. в lexical-ветвях | `'bm25'` (`:183`) |
| `ASK_ALIAS_INDEX` / `ASK_CARD_INDEX` | таблицы ветвей | `alias_idx` / `entity_card_idx` |
| `ASK_CARD_TABLE` | таблица `CARD` для kNN | `search_entity_card` (`:86`) |
| `ASK_RESOLVE_NEAR` / `ASK_RESOLVE_KEEP` | `:3586–3587`, лимиты резолвера | `12` / `3` |
| `RERANK_API` | формат тела/разбора (`dashscope`/`texts`/else) | из URL или `openai` (`:223`) |
| `RERANK_URL` / `RERANK_MODEL` / `RERANK_API_KEY` | HTTP реранка | см. `:218–276` |
| `RESOLVER_DSN` / `RESOLVER_PW` | `_resolver_psql`; пустой DSN → `[]` | `""` (`:70–71`) |

## Развилки

- Нет ветвей RRF → `_fused_candidates` = `None` (вызывающий склеивает поверхности сам, `:3122`).
- `ASK_SQL_RRF`+IVF+vec: SQL-RRF с corpus; падение SQL → python-RRF без corpus-ветки; падение python → `None`. Без флага/IVF: только SQL-RRF entity; падение → `None`.
- `near_tables` / lexical-ветки: `CARD` если `emb_ready(CARD)`, иначе `TABLES`, иначе пусто.
- `rows_of`: с `match` — индекс+highlight+bm25; без — корпус; с `measure` — сорт по числу.
- `rerank`: нет ключа → `[]` (порядок вызывающего не меняется); API-ветка выбирает JSON.
- `resolve_values`: IVF vs exact; пустой near / гарда `_shares_chars` → `[]`; нет порядка реранка → первые `RESOLVE_KEEP` из `keep`.
- `_resolve_values_literal`: `core` &lt; 3 символов → `[]`.
- `refuse_text`: пустой вопрос / исключение / цифры в тексте → `""`.

## Чего здесь нет

- Вызова `_resolve_values_literal` / `_resolve_values_corpus` из `resolve_values` (нет; цепочка снаружи).
- Использования `PICK_SYS` в срезе (нет).
- Порога векторной близости в `resolve_values` / `near_tables` (нет; отбор по LIMIT + реранк/гарда букв).
- Записи в БД (нет; только SELECT / `duckdb_indexes`).
- HTTP кроме реранкера; чат-модель кроме clarify/refuse.
- Сборки индексов IVF/alias/card (нет).
- Прямого ответа пользователю числом/именем (участок — кандидаты, строки, резолв, вспомогательные тексты).
