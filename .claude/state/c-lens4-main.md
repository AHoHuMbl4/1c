# Линза-4 (волна C «один путь»): главный тракт z20 — исходы без меню/ответа + образец резолвера

Режим: только чтение. Дата среза: 18.09.2026. Источник: `ubuntu/serenedb/ask/z20_ask_main_http.py` + call-site'ы z21/z06/z04/z01/z07.

`kind_unsupported` в тракте **не найден** (grep по ask/*.py — ноль совпадений).

---

## §1 Карта исходов-отказов

| file:line | класс | условие входа | текст клиенту |
|---|---|---|---|
| `z20:787-789` | no_data | `_coverage_answer`: RuntimeError на `search_coverage` | `NO_DATA_TEXT` или `refuse_text(question)` |
| `z20:791-793` | no_data | `_coverage_answer`: `tot` пуст | то же |
| `z20:837-842` | figures (не число-проза) | coverage: gate/claims отвергли текст, числа есть | `text=""`, поле `figures{...}` |
| `z04:165-170` ← call `z20:3723-3728` | no_data | `calendar_axis_unavailable_block`: нужен day_basis, карта/флаг недоступны | `NO_DATA_TEXT` или `refuse_text` |
| `z21:1354-1359` | no_data | wiki пул пуст **и** `question_expects_accounting_data` = False (off-topic) | `refuse_text` или `NO_DATA_TEXT` |
| `z21:1325-1330` / `z20:3776-3785` | no_data | wiki: нет `picked` (пустой пул учётный / verify none / degraded→fallback / axis_reject / post_verify fail) | `NO_DATA_TEXT` или `refuse_text`; reason в diag: `wiki_empty_pool` / `wiki_pick` / `wiki_no_leader` |
| `z20:3927-3933` | no_data | `probe`/`matched_group_count`: есть terms, matched < n_groups | `NO_DATA_TEXT` или `refuse_text`; reason=`значения из вопроса не найдены в данных` |
| `z20:4047-4052` | no_data | group-aggregate пуст **и** `_zero_period_not_missing` = False | то же |
| `z20:4063-4068` | no_data | `rows_of` пуст **и** не empty_period/drop_assumed | то же |
| `z20:4092-4101` | no_data | `aggregate` вернул пусто **и** act ∉ {empty_period, drop_assumed} | то же |
| `z20:3628-3630` | no_data | `_onepath_compose_gate`: gate fail **и** `agg` отсутствует | то же |
| `z20:3622-3627` | figures | gate fail, но `agg` есть | `atom_terminal_gate_text` / TOTAL / refuse; `figures` |
| `z20:1227-1234` ← `build_period_empty_answer` `z20:1265+` | answer (честный 0) | нуль в названном периоде | «За … записей … нет» + «итог… 0.00» / «количество — 0» |
| `z20:1752-1766` | answer без числа (R6/degenerate) | `_measure_degenerate_not_kept_answer` | `мера «…» не ведётся`; `atoms=[]` |
| `z20:1772-1785` | answer без числа (R6) | `_measure_degenerate_check_error` | `не удалось проверить, ведётся ли мера; итог по ней не подтверждаю` |
| `z20:1799-1823` | answer с числом в тексте | `_measure_text_with_total_answer` (не меню) | `по «…» доступен итог за период = N, без ранжирования/группировки` |
| `z21:1013-1023` | answer без числа (R6) | `wiki_homonym_peer_fail_soft` | `не удалось проверить одноимённые источники; число без уточнения не подтверждаю` |
| `z20:4902-4913` | unavailable / HTTP 503 | `AskDeadline` в Handler | фиксированный RU: «Отвечаю дольше обычного…» |
| `z20:4924-4931` | unavailable / HTTP 503 | любое другое Exception в Handler | БД / модель / «Сервис временно недоступен…» |
| `z20:4643` | unavailable (журнал) | Exception внутри `answer_checked` до raise | `text=""`, `retry=True` (клиенту уходит Handler 503) |
| `z20:4755,4762,4791,4802` | 503 health | `/health` degraded | не пользовательский ask-ответ |
| `z01:277` + `z07:262-284` | refuse helper | `NO_DATA_TEXT=env ASK_NO_DATA_TEXT` (умолч. `""`); `refuse_text` = LLM одна фраза без цифр | язык вопроса; при сбое LLM — `""` |

### Группы классов

1. **no_data** — отказ «данных нет / не отвечу» (часто при непустом корпусе).
2. **figures** — числа структурой без прозы / после gate reject.
3. **answer без числового атома** — R6 / «мера не ведётся» / homonym peer fail.
4. **answer честный 0** — period_empty (не отказ).
5. **unavailable/503** — дедлайн и системные сбои.
6. **clarify** — меню (не в этой таблице отказов; см. §4).

`kind_unsupported`: **не найдено**.

---

## §2 Карта ступеней тракта (`answer` z20:3662+)

Последовательность call-site'ов; при пустом результате — исход.

| # | ступень | call-site file:line | что зовётся | при пустом / провале |
|---|---|---|---|---|
| 1 | intent | `z20:3689` | `parse_intent` | lost→`cut.intent_lost` (`3731-3732`), не отказ сам по себе |
| 2 | readings | `z20:3701-3705` | `period_readings` + expand calendar/currency | пустой список → меню окна не строится |
| 3 | calendar block | `z20:3723-3728` | `calendar_axis_unavailable_block` (`z04:153`) | **no_data** |
| 4 | deadline | `z20:3695-3696`, `3743-3744` | `deadline_hit` → `AskDeadline` | **503 unavailable** |
| 5 | entity ticket | `z20:3749-3761` | `entity_choice_locked` / `hold_settled_entity` | билет даёт `picked`; иначе wiki |
| 6 | **wiki entity** | `z20:3767-3785` | `wiki_primary_entity_cascade` → `try_wiki_hybrid_entity_pick` (`z21:1290`, `1334`) | clarify / answer(R6) / **no_data** / `picked` |
| 6a | wiki pool | `z21:1345` | `wiki_hybrid_pool` (`z21:323`): kNN `WIKI_KNN_N=15` → pick `WIKI_PICK_N=8`, alias_top=`WIKI_ALIAS_TOP=3` | `[]` → empty_pool path |
| 6b | type filter | `z21:1348` | `filter_pool_by_named_type` (`z21:197`) | может обнулить непустой kNN-пул → no_data |
| 6c | pick/verify | `z21:1363-1388` | `wiki_pick_from_cards` / `wiki_verify_candidates` | none→None→no_data; clarify→меню; degraded→fallback→no_data |
| 6d | homonym gate | `z21:1403-1407` | `wiki_leader_db_homonym_gate` | меню entity / R6 answer / leader |
| — | **z06 entity bm25** | | | **на главном пути `answer` не зовётся** для выбора сущности. z06 `probe`/`tables_of` — после меню (шаг 7). z07 RRF — зона векторов/resolve_values, не wiki-лидер |
| 7 | coverage early | `z20:3788-3790` | `_coverage_answer` | answer / figures / no_data |
| 8 | window menu | `z20:3798-3805` | `_readings_to_opts` + `readings_menu` | clarify; `<2` → None, sole reading |
| 9 | measure settle | `z20:3842-3851` | `_settle_measure` (`1510`) + `_measure_menu_opts` + `readings_menu` | меню measure; 0 мер → measure=None, идём дальше; **без** `finalize_clarify_menu`/дайджестов на этом call-site |
| 10 | axis settle | `z20:3859-3887` | `_settle_axis` + `readings_menu` / kind-axis | clarify axis |
| 11 | stock-net entity menu | `z20:3895-3904` | `stock_net_register_menu_opts` + `readings_menu` kind=entity | clarify |
| 12 | deadline | `z20:3917-3918` | | AskDeadline |
| 13 | **term probe (z06)** | `z20:3921-3933` | `probe` (`z06:43`) + `matched_group_count` (`z06:148`) | **no_data** при unmatched groups |
| 14 | tables_of | `z20:3938` | `tables_of` (`z06:205`) | пустой by — diag.found=0, не сразу отказ |
| 15 | SQL aggregate | `z20:4014-4103` | totals/rows/aggregate_* | no_data или zero-agg / period_empty |
| 16 | degenerate consume | `z20:3965-4011` | ticket measure_verdict | not_kept / text_with_total / R6 |
| 17 | compose+gate | `z20:4154` | `_onepath_compose_gate` (`3402`) | answer / figures / no_data / period_empty / measure guard menu |
| 17a | measure guard | `z20:3440` | `_measure_degenerate_guard` (`3091`) | clarify via `finalize_clarify_menu` / R6 texts / sole replace |
| 18 | deadline pre-compose | `z20:4151-4152` | | AskDeadline |

### Пустые результаты ступеней (кратко)

- **wiki_hybrid_pool=[]**: учётный → `wiki_empty_pool` → no_data; не-учётный → no_data reason `wiki_none_empty`.
- **wiki verify all-no / pick choice=0**: outcome none → cascade no_data при непустом исходном пуле карточек.
- **readings_menu / clarify_opts `<2`**: `None` (`1409-1410`, `370-371`) — трактат идёт дальше как sole/без меню.
- **measure_alts пуст + need sum**: `_settle_measure` вернёт `(None,[])` — SQL без меры (count-path) или later no_data.
- **probe unmatched**: no_data при живой сущности (src уже выбран).

---

## §3 `llm_option_highlight` — механика (образец C1)

| факт | file:line |
|---|---|
| Определение | `z20:2875-2955` |
| Вызов | только из `finalize_clarify_menu` `z20:2976` (после digests + `kind_prior_sort`) |
| Модель | `_ds_chat_body` → `DS_MODEL` (`z01:213`, env `DEEPSEEK_MODEL`, умолч. `deepseek-v4-pro`); endpoint `DS_BASE`+`/v1/chat/completions` (`z01:204`, `z20:2930`) |
| Auth | `DS_KEY` = `DEEPSEEK_API_KEY` (`z01:205`, header `z20:2932`) |
| Бюджет wait | `min(0.8, remaining)` сек (`z20:2885-2886`); опц. `timeout_sec` ужимает; `urlopen(..., timeout=wait)` `2934` |
| Fail при deadline | `2881-2884`, `2925-2928` → `diag["llm_pick"]=None`, return None |
| Вход | вопрос + строки `"N. label (hint)"` только для opts с непустым `label`; meta-src переписывается `human_table_label` (`2897-2909`) |
| Промт | system: `Return one index digit.`; user: `Q: …\nOptions:\n…\nReply with one index 1..K.` (`2914-2920`) |
| Выход | индекс в `opts` (0-based) или None; на успехе `★` **append** в конец `hint` (`2949-2952`); `diag["llm_pick"]=pick` (`2953-2954`) |
| Fail-soft | любой Exception → pick=None (`2942-2943`); меню не блокируется (обёртка `finalize` `2982-2992`) |
| Журнал llm_pick | копируется в `diag["menu"]["llm_pick"]` (`2977-2980`); колонка JSON `measure_degenerate.menu.llm_pick` через `_journal_measure_degenerate` (`4324-4344`) |
| Не меняет порядок opts | только помечает ★; порядок до — `kind_prior_sort` |

---

## §4 Меню и точки сборки

| компонент | file:line | сигнатура / поведение |
|---|---|---|
| `clarify_opts_response` | `z20:360-384` | `(question, opts, diag, cut, t0, …)` → `kind=clarify` или **None** если `len(clean)<2` |
| `readings_menu` | `z20:1402-1415` | `(question, kind, items, diag, cut, t0, reason="")` → clarify; **None при `<2`** |
| `_readings_to_opts` | `z20:1443-1464` | window options (period ticket) |
| `_measure_menu_opts` | `z20:1494-1507` | measure → `{src,measure,label,…}` |
| `_measure_menu_build` | `z20:2997+` | live∪dead + annotations для degenerate-меню |
| `finalize_clarify_menu` | `z20:2958-2993` | digests → kind_prior → llm_option_highlight → `readings_menu` |
| entity-меню | `z21:944-1005` `wiki_entity_clarify_menu` → `finalize_clarify_menu(..., kind="entity")` | reason `wiki_separability` / `wiki_homonym_db` |
| measure-меню (до SQL) | `z20:3845-3851` | **только** `readings_menu` — **без** digests/★ |
| measure-меню (guard) | `z20:3226-3249` | `finalize_clarify_menu` + digests |
| axis / window / stock | `z20:3800`, `3864`, `3882`, `3899` | `readings_menu` без finalize |
| дайджест-канал | `attach_option_digests` `z20:2703+`; hint `_digest_hint_text` `2164+`; константы `_DIGEST_*` `2103-2106` | только через finalize при kind∈{measure,entity} и `len>=2` |
| kind-prior | `kind_prior_sort` `z20:2838-2872` | boost `accumulationregister_` при money∧period |
| выход наружу | Handler `z20:4880-4881` `seal_clarify` при `options`; HTTP 200 body kind=clarify | |

---

## §5 Журнал и дедлайн

### Журнал `ask_journal`

| факт | file:line |
|---|---|
| Точка записи | `_ask_journal_write` `z20:4440+`; зов из `answer_checked.finally` `4650-4651` |
| Исход | колонка `outcome` = `out["kind"]` (`4447-4509`): answer / clarify / no_data / figures / unavailable / (choice_error в тестах) |
| `choice_error` | упоминается в журнале (`4457-4460`, `4579`); **в текущем `z14_clarify_memory.py` производство kind=choice_error не найдено** |
| `measure_degenerate` | JSON `_journal_measure_degenerate` `4282-4346`: меню-блок (options+llm_pick+digests) и/или блок guard `{src,measure,live_measures,form}` |
| `decision_id` | колонка при ticket_used (`4484-4486`, `4499`) |
| intent_json | `_journal_intent` — kind/terms/measure/want (`4404` area) |
| clarify_options | slim options (`4349-4371`) |
| q_text | отдельно `ask_journal_text` (`4540`) |
| **«Незнакомое слово»** | **отдельного поля/исхода нет**. Ближайшее: `diag.parse.lost` / `cut.intent_lost` (`3731-3732`, intent `z02:569`); `unmatched_terms` в diag (`3928`); wiki `wiki_none` / `wiki_empty_pool`. Корм словарной линии в journal **не выделен** — писать некуда отдельной колонкой без миграции |

### Дедлайн

| факт | file:line |
|---|---|
| Константа | `ASK_DEADLINE_SEC` env, умолч. 88 (`z01:19-21`) |
| Старт часов | `_rid_enter` → `_REQ_T0[rid]` (`z01:96-100`) в `answer_checked` |
| `deadline_hit` | `z01:109-115` |
| Жёсткие raise в answer | `z20:3695`, `3743`, `3917`, `4151` → AskDeadline |
| Soft под дедлайном | digests / llm_option_highlight / measure_degenerate_verdict / compare batches — abort куска, не raise |
| Клиент | Handler `4902-4913` HTTP 503 kind=unavailable |

Ступени под жёстким дедлайном: после intent, до wiki, до SQL, до compose. Wiki/LLM/SQL сами могут съесть бюджет → следующий checkpoint raise.

---

## §6 Вывод: смерть при НЕпустом пуле кандидатов → кандидаты в LLM-резолвер «где что»

Точки, где вопрос уходит в **no_data / R6-answer без меню**, хотя кандидаты/данные могли быть живы:

1. **`wiki_hybrid_pool` молчаливый top-N** — `z21:9-15,300-306,323`: kNN 15 / pick 8 / alias_top 3; верная карточка за срезом → пустой/чужой пул → no_data (`z21:1321-1330`, `z20:3776-3785`).
2. **`filter_pool_by_named_type` обнуляет пул** — `z21:197-215,1348-1362`: до фильтра pool_before>0, после 0 → no_data.
3. **Wiki pick/verify «none» при len(cards)≥1** — `z21:1267-1268`, `1151-1157`, `1389-1393`: все no / choice=0 → cascade no_data.
4. **Wiki degraded/fallback** — `z21:1370-1372,1387-1388,1312-1313`: модель/parse fail → `wiki_pick=fallback` → no_data без меню по пулу.
5. **axis_reject / post_verify fail** — `z21:1136-1138`, `1401-1402`: лидер отвергнут → none → no_data.
6. **Homonym peer R6** — `z21:1008-1023,1104`: амбиг пиры есть, меню не собралось (`opts<2`) → answer без числа (не clarify).
7. **Unmatched terms после выбранного src** — `z20:3927-3933` + `z06:43-145`: сущность уже есть, слово-фильтр не резолвится → no_data.
8. **SQL empty без period_given** — `z20:4047-4052`, `4063-4068`, `4098-4101`: src выбран, rows/agg пусты, act=`no_data`.
9. **Gate reject без agg** — `z20:3628-3630` (редкий путь).
10. **Calendar axis unavailable** — `z20:3723-3728` / `z04:153-170`: вопрос с day_basis при выключенной карте → no_data.
11. **Measure settle без меню при need+0 имён** — `_settle_measure` `1556-1562` вернёт `(None,[])`; дальше SQL/no_data (не LLM-меню мер). До-SQL measure-меню **не** проходит через `finalize`/резолвер (`3845-3851`).

Не кандидаты в резолвер (уже «после выбора» / честные):

- period_empty answer (`1227+`) — честный 0;
- unavailable/503 — бюджет/сбой;
- figures после gate при живом agg — альтернативный ответ, не пустой пул;
- clarify-меню — контракт выполнен.

**Вывод для C1:** единый LLM-резолвер «где что» по образцу `llm_option_highlight` (`≤800 мс`, fail-soft, индекс/«нет») логично ставить **один раз до entity/measure меню**, на входе с полным (не top-N-молчаливым) пулом wiki+словарь+описания; закрывает строки 1–5 и 7 прежде всего. Точки 6, 8–10 — соседние ловушки того же единого тракта (не «до механизмов»).
