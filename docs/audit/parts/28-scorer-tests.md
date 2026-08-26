# 28. scorer-tests

## Зачем участок нужен
`ab_scorer.py` прогоняет набор вопросов через HTTP `/ask`, считает эталон SQL-ом в SereneDB и ставит OK/FAIL по режимам `digits`/`kind`/`clarify`/`name`. `ab-gold-okna.tsv` — золотой набор okna (v2). `test_ab_scorer_*.py` и `test_ab_calendar_axis_set.py` — оффлайн-замки функций скорера без `/ask` и psql. Остальные `test_*.py` (77 файлов) — оффлайн-замки модулей ask/report/corpus; живое сравнение ответа бота с эталоном среди них делает только `ab_scorer` (и отдельно `test_e2e.py` для `serene_report.run_report`, не `/ask`).

## Входы
- **CLI:** `python3 ab_scorer.py` (`ab_scorer.py:10`, `:764-765`).
- **TSV-строка:** `вопрос<TAB>SQL|игла<TAB>режим` или legacy `вопрос<TAB>SQL` / `вопрос<TAB>MODE=kind` (`:134-181`, `ab-gold-okna.tsv:2-5`).
- **Тело POST /ask:** `{"question", "user", опц. "decision_id", "rid"}` (`:231-236`).
- **Ответ /ask (поля скоринга):** `kind`, `text`, `diag.claims|error`, `figures`, `totals`, `options[].label|text|focus|src|measure|grain|distinct_by|decision_id` (`:255-285`, `:326-349`, `:506-519`).
- **Env / файлы env:** см. «Переключатели»; DSN/токен/порт также из `/etc/1c-serene-ask*.env`, `/etc/1c-mcp-reports.env` (`:42-46`, `:72-82`).

## Порядок работы
1. Импорт: `resolve_gold_file` → `GOLD_FILE`; ветка okna/probe vs A/B → `DSN`, `URL`, `TOK`, `SCORERS`, `LIVE_CONTOUR` (`:51-123`).
2. `main`: `load_gold(GOLD_FILE)` (`:617-618`).
3. Для каждой строки: `row_want_spec` → эталон `truth(sql)` через psql, либо литерал-игла clarify; пустой эталон (не digits/kind/clarify-sentinel) → `blind` → выход без отметки (`:624-651`, `:184-203`).
4. По каждому scorer: если не live — `restart` (пишет `ASK_SCORER` в env-файл, `systemctl restart`, sleep 4) (`:548-553`, `:656-658`).
5. На вопрос: `ask_with_clarify_follow` (до 6 шагов; для digits/kind `branch_needle=None`) → `ask` POST (`:352-376`, `:663-689`).
6. Скоринг по `mode`: `score_digits` / `score_digits_probe` (PROBE=okna) / `score_kind` / `score_clarify` / `score_name` (`:698-713`).
7. Печать markdown-таблицы и провалов; выбор лучшего scorer по `(hits, -avg_sec)`; `write_mark` → exit 0/1 (`:726-765`).

## Выходы
- **stdout:** сводка контура, эталоны, `== scorer: верных N/M`, markdown `| question | mode | verdict | fact |`, итог по scorers (`:620-758`).
- **stderr:** строки `🔴 FAIL …`; при отказе отметки — текст про несставленную метку (`:722-724`, `:571-606`).
- **файлы-отметки** (при 0 сбоев и полном попадании / smoke без errs): `.claude/.probe-okna-last-run` | `.golden-okna-last-run` | `.golden-last-run` (`:556-614`).
- **код выхода:** `0` если `write_mark` вернул имя scorer, иначе `1` (`:764-765`).
- **потребители вне участка (по коду участка):** нет импортов; `PROBE_RECORD` → `probe_protocol.emit` (`:211-228`). `test_check_deploy_gate.py` проверяет разбор отчётов гейта (не зовёт ab_scorer).

## Обращения наружу
| Место | Что | Назначение |
|---|---|---|
| `truth` `:197` | `psql DSN -tA -c SQL` | эталон из корпуса |
| `ask` `:245` | HTTP POST `URL` JSON | ответ сервиса |
| `restart` `:552` | `systemctl restart UNIT` | смена `ASK_SCORER` |
| `mark_path` `:560-562` | `git rev-parse --show-toplevel` | корень для отметки |
| `env_value` `:72-82` | чтение `/etc/1c-*.env` | DSN, токен, порт, PGPASSWORD |
| `_probe_emit_ask` `:216` | `probe_protocol.emit` | запись пробы при `PROBE_RECORD` |
| LLM | нет | — |

Эталонные SQL в `ab-gold-okna.tsv:8-32` — `SELECT`/`WITH` по `search_corpus` (суммы продаж, топы, count, `SELECT 0` для kind/clarify).

## Переключатели
| Переменная | Умолч. | Чтение | Эффект |
|---|---|---|---|
| `AB_GOLD_FILE` | пусто | `:58-60` | явный путь TSV |
| `AB_CALENDAR_AXIS` | `""` | `:40`, `:61-63` | `1\|okna\|yes\|true` → `ab-calendar-axis-okna.tsv` |
| `AB_PROBE` | `""` | `:38`, `:66-68` | `okna` → `ab-probe-okna.tsv`, live, отметка probe |
| `AB_CONTOUR` | `""` | `:37`, `:66-68` | `okna` → `ab-gold-okna.tsv`, live |
| `AB_GOLD_MODE` | `""` | `:39`, `:117-119` | `smoke` → live, `SCORERS=["live"]`, `BASE` default `ut_test` |
| `AB_BASE` | `postgres` / `ut_test` при smoke | `:41` | dbname, env-файл, юнит |
| `AB_DSN` | см. ветки `:96-107` | DSN psql |
| `ASK_URL` | okna: `http://127.0.0.1:8091`; иначе порт из env или live off | `:98-114` |
| `ASK_TOKEN` | из `/etc/…` | `:100`, `:120-123` | Bearer |
| `AB_ASK_USER` | `gold-v2` | `:47` | поле `user` |
| `AB_ASK_TIMEOUT` | `600` | `:243` | сек urlopen |
| `AB_SCORERS` | `bm25,bm25_b0,tfidf,lm_jm,lm_dirichlet,dfi` | `:115-116` | только не-live |
| `AB_MARK_DIR` / `CLAUDE_PROJECT_DIR` | git root | `:557` | каталог отметки |
| `PROBE_RECORD` / `PROBE_CODE_PATH` | пусто / `/opt/…/serene_ask.py` | `:214-220` | emit пробы |
| `PGPASSWORD` | из mcp-env | `:85-90` | для psql |

## Развилки
- Выбор TSV: `AB_GOLD_FILE` > calendar axis > probe/contour okna > `ab-gold.tsv` (`:51-69`).
- Live vs A/B: `PROBE/CONTOUR=okna` или `ASK_URL` или smoke → без restart, один `live` (`:94-119`, `:655`).
- `mode`: digits (PROBE=okna требует `kind∈{answer,figures}`); kind — ожидание из SQL+want+текст вопроса; clarify — `kind=clarify` + игла в options; name — имена и числа в финальном `outf` (`:698-713`, `:379-399`, `:437-545`).
- clarify follow-up только если `branch_needle` и найден option (`:365-375`); digits/kind иглу не передают (`:678-680`).
- `kind_expected_for_kind_mode`: zero+«почему|сбой|ошибк|баг» → `diagnostic_zero` (answer|no_data); zero+периодный SQL → `figures`; иначе zero → `no_data`; ненуль → `answer` (`:379-399`).
- `no_data` с группированным/дробным числом в text (после снятия «N мин/сек») → FAIL (`:411-434`, `:469-471`).
- Отметка не пишется при errs / неполных hits (smoke: только errs) или нет `.claude` (`:571-607`).

## Чего здесь нет
- Вызова языковой модели для оценки ответа.
- Сравнения семантики/прозы; только цифры, `kind`, подстроки options/имён.
- Порога «достаточно верных %» кроме 100% hits (или 0 errs в smoke) для отметки.
- Запуска `ab_scorer` из `test_ab_scorer_*.py` (только чистые функции + `load_gold`).
- Среди прочих `test_*.py` — единого раннера качества `/ask`; `test_e2e.py` меряет `serene_report`, не этот scorer.
- В `ab-gold-okna.tsv` режимов кроме digits/kind/clarify/name; строк данных: 25 (`test_ab_scorer_v2_modes.py:46`).
