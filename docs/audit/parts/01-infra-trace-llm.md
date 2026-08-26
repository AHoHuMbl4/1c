# 01. infra-trace-llm

## Зачем участок нужен
Участок `ubuntu/serenedb/serene_ask.py:126-807` — инфраструктура одного ответа: request-id и TRACE в stderr, вызов `psql` с CSV-разбором, эмбеддинг вопроса (HTTP или `ai_embed`), чат с LLM (`ds_chat*`), арбитр выбора готового ответа, накопление токенов в diag. Плюс модульные константы скорера/реранкера/текстов отказа (объявление env; функций реранка и поиска здесь нет).

## Входы
- **rid:** `_rid_enter(rid=None)` / `_rid_norm` — строка или пусто → hex (`secrets.token_hex`, `:126-145`).
- **TRACE / `_rid_ctx`:** объявлены выше участка (`:117`, `:123`); `_trace_write` пишет, если `TRACE` истинно (`:148-152`).
- **psql(sql):** строка SQL; `DSN`=`SERENEDB_DSN_RO`, опц. `PGPASSWORD` (`:327-361`; DSN/PGPASSWORD — `:63-64`).
- **ds_chat(messages, temperature=0, max_tokens=900):** список сообщений chat (`:591-592`).
- **arbitrate(question, answers, context=""):** вопрос, список готовых текстов, опц. контекст (`:615-641`).
- **embed_one(text) / _embed_one_native(text):** текст вопроса (`:744-806`, `:707-741`).
- **emb_ready(table):** имя таблицы для ключа `emb_model_<table>` (`:424-442`).
- Env модуля: см. «Переключатели».

## Порядок работы
1. При загрузке модуля: чтение env → константы (`:175-323`, `:664-670`); `csv.field_size_limit(50*1024*1024)` (`:234`).
2. Rid: `_rid_enter` → `_rid_norm` → при пустом/пустом после очистки `_new_rid` → `_rid_ctx.set` (`:126-145`).
3. След: `_trace_write(layer, step, ms, status)` → stderr `TRACE <rid> <layer> <step> <ms> <status>` (`:148-152`).
4. `psql`: `subprocess.run(["psql", DSN, "-tA", "--csv", "-v", "ON_ERROR_STOP=1", "-f", "-"], input=sql)` → `csv.reader` → список строк; ненулевой код/`OSError` → `RuntimeError` (`:349-361`).
5. `embed_model_live`: кэш 300 с; иначе GET `EMBED_HEALTH_URL`, JSON.`model` == `EMBED_MODEL` (`:391-421`).
6. `emb_ready(table)`: кэш 60 с; если не `embed_model_live` → False; иначе `psql` `SELECT note FROM search_quality WHERE k = 'emb_model_'+table` и сравнение с `EMBED_MODEL` (`:424-442`).
7. Токены: `_token_acc_start` создаёт `_TokenAcc`; `_ds_chat_content` при наличии `usage` зовёт `_token_acc_record` → `acc.add` + `_trace_write("model","TOKENS",…)` (`:523-567`); `_diag_pack` кладёт `tokens` в копию diag (`:544-550`).
8. LLM: `_ds_chat_body` → `ds_chat_post` POST `{DS_BASE}/v1/chat/completions` → `_ds_chat_content` → `content` или None (`:569-592`).
9. `arbitrate`: при `len(answers)<2` → `0` или `None`; иначе `ds_chat` (max_tokens=8), разбор цифр → индекс `n-1` или `None` (`:615-641`).
10. Эмбед: `embed_one` смотрит `_EMB_ONE_CACHE`; если `ASK_EMBED_NATIVE` → `_embed_one_native` (`_ensure_embed_secret` + `SELECT to_json(ai_embed(...))` с ретраями); иначе HTTP `_embed_request(..., as_query=True)` с ретраями, разбор `embeddings[0]` или `data[0].embedding` (`:673-806`).

## Выходы
| Функция | Возврат | Потребитель в участке |
|---|---|---|
| `_rid_enter` / `_rid_get` | str rid | `_trace_write` |
| `_trace_write` | None (stderr) | `_token_acc_record` |
| `psql` | `list[list[str]]` | `emb_ready`, `_ensure_embed_secret`, `_embed_one_native` |
| `lit` | SQL-литерал | те же SQL |
| `embed_model_live` / `emb_ready` | bool | `emb_ready` ← live |
| `ds_chat` / `ds_chat_post` | content / JSON | `arbitrate` ← `ds_chat` |
| `arbitrate` | int индекс / None / 0 | нет внутри участка |
| `embed_one` | `list[float]` | нет внутри участка |
| `_diag_pack` | dict | нет внутри участка |
| `_fmt*` / `_gate_bad_preview` | str | нет внутри участка |

Потребители ниже `:809` в этом диапазоне не видны.

## Обращения наружу
| Место | Что | Назначение |
|---|---|---|
| `:355-356` | `psql` subprocess | любой SQL вызывающего |
| `:435` | `SELECT note FROM search_quality…` | сверка модели эмбеддинга таблицы |
| `:684-685` | `SELECT 1 FROM duckdb_secrets()…` | есть ли секрет эмбеддера |
| `:695-700` | `CREATE OR REPLACE TEMPORARY SECRET…` | секрет OpenAI-совместимого эмбеддера |
| `:712-718` | `SELECT to_json(ai_embed(…)::FLOAT[dim])` | вектор вопроса в БД |
| `:409-412` | HTTP GET `EMBED_HEALTH_URL` | живая модель эмбеддера |
| `:581-588` | HTTP POST `{DS_BASE}/v1/chat/completions` | чат LLM |
| `:789-791` | HTTP POST эмбеддера (`EMBED_URL`+path) | вектор вопроса по HTTP |
| `:631-632` | `ds_chat` из `arbitrate` | выбор номера ответа |

## Переключатели
| Имя | Чтение | Умолчание |
|---|---|---|
| `ASK_SCORER` | `:183` | `"bm25"` |
| `ASK_REFS_BOOST` | `:195` | `"8.0"` |
| `ASK_ORDER_BY_MEANING` | `:202` | вкл. (выкл: `0`/`false`/`no`) |
| `RERANK_URL` / `ALIBABA_RERANK_URL` | `:218-220` | dashscope URL |
| `RERANK_MODEL` / `ALIBABA_RERANK_MODEL` | `:221-222` | `"qwen3-rerank"` |
| `RERANK_API` | `:223-224` | `"dashscope"` если URL содержит dashscope, иначе `"openai"` |
| `ASK_RERANK_TOP` | `:228` | `60` |
| `DEEPSEEK_BASE` | `:236` | `https://api.deepseek.com` |
| `DEEPSEEK_API_KEY` | `:237` | `""` |
| `DEEPSEEK_MODEL` | `:245` | `"deepseek-v4-pro"` |
| `DEEPSEEK_THINKING` | `:246` | `"disabled"` |
| `ASK_THINKING_OFF_BODY` | `:249` | выкл.; вкл: `1`/`true`/`yes` |
| `EMBED_BASE_URL` / `ALIBABA_EMBED_URL` | `:258-259` | `""` |
| `EMBED_API` | `:265` | `"openai"` |
| `EMBED_QUERY_PATH` | `:266` | `"/embed"` |
| `EMBED_UA` | `:269` | `"curl/8.5.0"` |
| `EMBED_HEALTH_URL` | `:271` | `EMBED_URL+"/health"` |
| `EMBED_API_KEY` / `ALIBABA_API_KEY` | `:272` | `""` |
| `EMBED_MODEL` | `:273` | `"text-embedding-v4"` |
| `RERANK_API_KEY` | `:276` | = `EMBED_KEY` |
| `EMBED_DIM` | `:284`, `:307` | `1024` |
| `EMBED_SECRET` / `EMBED_SECRETS` | `:289` | имя `"ask_embed"` |
| `EMBED_PATH` | `:296` | `"/v1/embeddings"` |
| `ASK_EMBED_NATIVE` | `:297` | `"0"` → False |
| `ASK_NO_DATA_TEXT` / `ASK_TOTAL_TEXT` | `:317-318` | `""` |
| `ASK_STALE_TEXT` | `:321-323` | рус. шаблон с `%d` |
| `EMBED_HOST` | `:369` | иначе `EMBED_URL` |
| `ASK_EMB_CACHE` | `:664` | `256` |
| `ASK_EMB_RETRY` | `:668` | `2` |
| `ASK_EMB_RETRY_PAUSE` | `:669` | `0.4` |
| `ASK_EMB_TIMEOUT` | `:670` | `60` |
| `ASK_TRACE` / `SERENEDB_DSN_RO` / `PGPASSWORD` | выше `:117`, `:63-64` | TRACE вкл.; DSN обязателен в `psql` |

`_reload_embed_native_env` (`:302-308`) перечитывает native-embed env и сбрасывает `_EMBED_SECRET_READY`.

## Развилки
- `_rid_norm`: пустой/пустой после `isalnum` → новый rid (`:130-135`).
- `_trace_write`: при `not TRACE` — no-op (`:149-150`).
- `psql`: нет DSN → `RuntimeError`; код≠0 / OSError → `RuntimeError` (`:329-360`).
- `embed_model_live` / `emb_ready`: кэш hit; live False → все таблицы False; SQL-сбой → False (`:401-441`).
- `_ds_chat_body`: поле `thinking` если `DS_THINKING`; `chat_template_kwargs` если `ASK_THINKING_OFF_BODY` (`:572-576`).
- `_ds_chat_content`: нет dict/choices/message → None; иначе `content` (`:553-566`).
- `arbitrate`: `<2` ответов → `0`/`None`; исключение/`нет цифр`/`0`/`n>len` → None; иначе `n-1` (`:617-641`).
- `_embed_request`: `EMBED_API=="texts"` → `{texts,is_query,dim}` на `EMBED_QUERY_PATH`; иначе openai `/embeddings` (`:646-651`).
- `_ensure_embed_secret`: секрет уже есть → skip CREATE; нет host → ошибка (`:676-704`).
- `embed_one`: cache hit; `ASK_EMBED_NATIVE` → native; иначе HTTP; native/HTTP ретраи на timeout/connect/temporarily (native) или любом Exception кроме RuntimeError (HTTP); кэш ≥ MAX → `clear` (`:764-806`).
- `_TokenAcc.diag_dict`: `cache_hit`/`cache_miss` только если поля usage встречались (`:514-520`).

## Чего здесь нет
- Вызова реранкера по HTTP (есть только константы `RERANK_*`, `:218-228`, `:276`).
- Поиска по корпусу / BM25-SQL (есть только шаблоны `SCORERS`, `:175-183`).
- Разбора намерения, гейта ответа, HTTP-сервера `/ask`.
- Ретраев `ds_chat` / `ds_chat_post`.
- Использования `NO_DATA_TEXT` / `TOTAL_TEXT` / `STALE_TEXT` / `ORDER_BY_MEANING` / `SCORER` / `REFS_BOOST` / `RERANK_TOP` телом функций этого участка.
- Записи rid/токенов в ответ HTTP — только ContextVar, stderr TRACE и поле `tokens` в `_diag_pack`.
