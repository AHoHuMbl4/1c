# План: вопросный эмбеддинг через `ai_embed` (проход 1)

Дата: 2026-08-25. Код `ubuntu/serenedb/serene_ask.py` в этом проходе **не
применялся**. Артефакты: `work/ai_embed_native.patch`, этот план,
`ubuntu/serenedb/test_ai_embed_question.py` (лежит в дереве и внутри патча).

## 1. Доки SereneDB

| Тема | Раздел | Факт |
|---|---|---|
| Синтаксис | [sql/functions/ai#ai_embed](https://docs.serenedb.com/sql/functions/ai#ai_embed) | `ai_embed(text, model, secret_name) → FLOAT[]`; длина = размерность модели; `NULL` → `NULL`; для IVF — `::FLOAT[N]` |
| Провайдеры | [sql/functions/ai#providers](https://docs.serenedb.com/sql/functions/ai#providers) | `TYPE openai` = OpenAI-совместимый протокол; параметры `api_key`, `base_url`, `embeddings_path` |
| Секреты | [configuration/secrets_manager](https://docs.serenedb.com/configuration/secrets_manager) | `CREATE SECRET` / `CREATE PERSISTENT SECRET`; список — `duckdb_secrets()` (значения redact) |
| Таймаут HTTP | живой `duckdb_settings()` + [docs/EMBED_BULK_HOWTO.md](../docs/EMBED_BULK_HOWTO.md) | `http_timeout` (сек, на okna **30**); для чужих сессий — `SET GLOBAL http_timeout` |

Живая сборка okna через туннель `:17890`: **SereneDB 26.08.1** (не 26.07.3 из
условия задачи). Синтаксис `ai_embed` и секрет `TYPE openai` на инстансе работают.

## 2. Живой замер okna (`127.0.0.1:17890`, `serene_ro`)

### Секреты (имена; значения не читались)

| Имя | type | persistent | base_url (из redact-meta) | embeddings_path |
|---|---|---|---|---|
| `ask_embed_bench` | openai | false | `http://10.3.1.11:8000` | `/v1/embeddings` |
| `ask_embed_bench2` | openai | false | `http://10.3.1.11:8000` | `/v1/embeddings` |
| `ask_fmt_test` | openai | false | `http://10.3.1.11:8000` | `/v1/embeddings` |
| `ask_ro_test` | openai | false | `http://127.0.0.1:1` | `/v1/embeddings` |

Под вопросный эмбеддинг: **`ask_embed_bench`** (и `ask_embed_bench2` /
`ask_fmt_test`) — тот же vLLM `10.3.1.11:8000`, OpenAI-путь. `ask_ro_test` —
заглушка на мёртвый порт.

На okna env эмбеддера: `EMBED_MODEL=Qwen3-Embedding-4B`, `EMBED_DIM=1024`,
`EMBED_HOST=http://10.3.1.11:8000`, `EMBED_PATH=/v1/embeddings`,
`EMBED_API=texts`, `EMBED_QUERY_PATH=/embed`.

### Вызов

```sql
SELECT array_length(ai_embed('сколько продаж за январь',
       'Qwen3-Embedding-4B', 'ask_embed_bench'), 1);
-- → 1024
```

### Латентность (N=6, медиана; замер на хосте okna)

| Путь | Медиана | Примечание |
|---|---|---|
| HTTP `texts` `/embed` (текущий ask) | **31,1 мс** | `is_query=true`, dim=1024 |
| HTTP openai `/v1/embeddings` | **32,7 мс** | тот же формат, что у секрета |
| `ai_embed` (`EXPLAIN ANALYZE` Total Time) | **66,5 мс** | dim=1024, секрет `ask_embed_bench` |

Нативный путь дороже HTTP примерно на **+35 мс** на один вопрос (клиент движка +
SQL). Качество пути: оба бьют в тот же `10.3.1.11:8000`. Повторы внутри ответа
по-прежнему закрывает кэш `_EMB_ONE_CACHE`.

`serene_ro` на okna может создать TEMPORARY SECRET (проба с последующим DROP;
постоянных секретов не трогали).

## 3. Место в `serene_ask.py` (только чтение)

| Узел | Строки | Роль |
|---|---|---|
| Env | ~258–284 | `EMBED_URL` / `EMBED_API` / `EMBED_MODEL` / `EMBED_DIM` |
| `_embed_request` | ~613–626 | HTTP POST: `texts`+`is_query` или openai `/embeddings` |
| `embed_one` | ~642–698 | urllib → `list[float]`; кэш; retry; `RuntimeError` |
| `_vec` | ~7684–7685 | `embed_one` → SQL-литерал `'[…]'::FLOAT[EMBED_DIM]` |

Документы корпуса уже через `ai_embed` в такте (`embed_missing.sh` / `build.sh`).
Вопрос — единственный HTTP-исключение (TARGET п. 7).

## 4. Что в патче `work/ai_embed_native.patch`

1. **Флаг** `ASK_EMBED_NATIVE` (умолч. `"0"` → False).
2. **Env** `EMBED_SECRET` / `EMBED_SECRETS` (первое имя), `EMBED_PATH`.
3. При флаге 1: `_embed_one_native` — один SQL
   `SELECT to_json(ai_embed(text, model, secret)::FLOAT[dim])`.
4. Если секрета нет — `CREATE OR REPLACE TEMPORARY SECRET … TYPE openai` из
   `EMBED_HOST`+ключ+path (как такт); сбой CREATE/ai_embed → `RuntimeError`
   (тихого «без вектора» нет).
5. Размерность ≠ `EMBED_DIM` → `RuntimeError`.
6. Оффлайн-замок `ubuntu/serenedb/test_ai_embed_question.py`: флаг 0 = HTTP;
   флаг 1 = один SQL; нет секрета → ошибка; dim ≠ 1024 → ошибка.
   Прогон на копии после `git apply`: **PASS 14 FAIL 0**.

Патч **не применять** в этом проходе. Перед `git apply` в проходе 2: если
`test_ai_embed_question.py` уже лежит в дереве — убрать или применить с учётом
существующего файла.

## 5. Риски

| Риск | Разбор |
|---|---|
| +35 мс на вопрос | При 1–2 вызовах после кэша — доли секунды к ответу; при холодном кэше заметнее |
| TEMPORARY SECRET | После рестарта движка секреты из памяти пропадают; патч создаёт TEMPORARY из env при первом вызове |
| `texts` vs openai | Корпус и `ai_embed` идут openai-путём (документ); ask сейчас `texts`+`is_query`. Смысловое расхождение query/doc — отдельный риск качества, не латентности |
| RO DSN | На okna `serene_ro` CREATE TEMPORARY смог; на другой базе — проверить до выката |
| Бой `:8091` | Не трогать; выкат только на `:8092` |

## 6. Порядок прохода 2 (выкат на `:8092`)

1. `git apply work/ai_embed_native.patch` (на чистом дереве / без конфликта замка).
2. `python3 ubuntu/serenedb/test_ai_embed_question.py` → 0 FAIL.
3. На стейджинге: в env ask задать `ASK_EMBED_NATIVE=1`,
   `EMBED_SECRET=ask_embed` (или живое имя), `EMBED_HOST`/`EMBED_PATH`/`EMBED_MODEL`
   как на okna; **не** включать на `:8091`.
4. Рестарт только юнита стейджинга `:8092` (не бой).
5. Проба: один `/ask` + сверка `search_meta`/журнала, что векторный путь жив;
   AB_PROBE okna на `http://127.0.0.1:18092/ask`.
6. Сравнить латентность ДО/ПОСЛЕ на стейджинге; откат = `ASK_EMBED_NATIVE=0` +
   рестарт стейджинга (HTTP-путь на месте).

## 7. Граф

Наблюдение у `serene_ask.py` + сущность замка `ubuntu/serenedb/test_ai_embed_question.py`
в `memory_bank/mcp-memory.json` (этот коммит).
