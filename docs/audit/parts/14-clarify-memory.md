# 14. clarify-memory

## Зачем участок нужен

Участок `ubuntu/serenedb/serene_ask.py:6617-7360` содержит: (1) правило выбора величины по слову человека (`measure_choice` и спутники); (2) допись нумерованных пунктов уточнения в текст (`clarify_complete`); (3) сравнение ответов кандидатов (`answers_diverge` / `answers_src_conflict`); (4) процессное хранилище одноразовых билетов выбора и снимков clarify (`issue_decision` / `seal_clarify` / `consume_decision` и память снятых уровней); (5) проверки «что уже доказано билетом» для гашения защит и стопа 2 (`guards_skip_for_choice` / `stop2_active` / `hold_settled_entity`).

## Входы

| Функция | Аргументы / поля |
|---|---|
| `measure_choice` | `names`, `word`, `alias_by` (опц.) — `ubuntu/serenedb/serene_ask.py:6638` |
| `measure_captions` / `resolve_measure` | величины, `alias_by`, текст выбора; `diag` — `6694`, `6715` |
| `slot_measure_uncovered` | `word`, `selected`, `names`, `alias_by` — `6750` |
| `clarify_complete` | `txt`, `opts`, `question=""` — `6761` |
| `answers_diverge` | `figures` (список dict слотов) — `6815` |
| `answers_src_conflict` | `cands` с полями `kind`/`src`/`figures` — `6850` |
| `issue_decision` | `question`, `option`, `ambiguity`, `options_ver`, `user`, `parse`, `class_meta`, `batch_id` — `6988` |
| `seal_clarify` | `out` (dict с `kind`/`options`/…), `question`, `user`, `parse` — `7027` |
| `consume_decision` / `peek_decision` | `decision_id`, `question` (только consume), `user` — `7082`, `7112` |
| `lookup_clarify_batch` | `decision_id`, `question`, `user`, `err` — `7135` |
| `reissue_clarify` | `batch`, `err` — `7162` |
| `attach_memory_shadow` | `out`, `user`, `action`, `decision_id` — `7212` |
| `hold_settled_entity` | `focus`, `trusted`, `resolved`, `found_by`, `measure_pick`, `holder_srcs` — `7264` |
| `guards_skip_for_choice` / `stop2_active` | `focus`, `measure_pick`, `trusted`; у stop2 ещё `no_arbiter` — `7301`, `7316` |
| `determined_answer_rivals` | `picked`, `par`, `writer_pair`, `alias_leader`, `known_src` — `7329` |
| env (в участке) | `ASK_RAW_FOCUS_TRUST`, `ASK_DECISION_TTL_SEC` — `6871-6872` |
| глобалы процесса | `_DECISIONS`, `_CLARIFY_BATCHES`, `_RESOLVED_CHOICES`, lock — `6873-6877` |

## Порядок работы

1. **Выбор величины (оффлайн-правило):** `_alias_parts` → `_word_hits_text` / `split_ident` → `measure_choice` возвращает `(величина|None, альтернативы, как)` (`6638-6691`). `resolve_measure` сводит текст человека к имени поля (`6715-6747`). `slot_measure_uncovered` зовёт `measure_choice` и проверяет покрытие (`6750-6758`).
2. **Текст уточнения:** `clarify_complete` зовёт `format_clarify_options` (вне участка), дописывает отсутствующие нумерованные строки (`6761-6777`).
3. **Расхождение ответов:** `_slot_fp` строит отпечаток слотов (`6794-6812`); `answers_diverge` сравнивает `sum` (если есть) или отпечатки (`6815-6848`); `answers_src_conflict` — разные `src` при совпавшем отпечатке (`6850-6865`).
4. **Выпуск билета:** `seal_clarify` для `kind ∈ {clarify,figures,answer}` с непустым `options` (`7034-7038`): `ambiguity_of_options` → `options_version` → `ACM.class_meta_of` → на каждый option `issue_decision` → снимок в `_CLARIFY_BATCHES` (`7027-7079`). `issue_decision` кладёт ticket в `_DECISIONS` (`6988-7024`).
5. **Погашение:** `consume_decision` проверяет used/TTL/db/question_fp/user, ставит `used=True` (`7082-7109`). При успехе снаружи участка зовут `accumulate_resolution` (`6968-6985`) — запись в `_RESOLVED_CHOICES`.
6. **Повтор / ошибка:** `lookup_clarify_batch` → `reissue_clarify` (`7135-7180`); `choice_error_response` (`7183-7201`).
7. **Тень памяти:** `attach_memory_shadow` → `ACM.attach_choice_memory` (`7212-7223`).
8. **После билета:** `choice_proven` / `choice_levels_proven` / `measure_already_proven` / `entity_choice_locked` → `hold_settled_entity` выбирает src (`7226-7298`); `guards_skip_for_choice` → `stop2_active` (`7301-7326`); `determined_answer_rivals` собирает соперников (`7329-7364`).
9. **Чистка:** `_purge_decisions` по `expires_at` для трёх словарей (`6936-6951`); вызывается из peek/issue/consume/lookup/accumulate.

## Выходы

| Выход | Кто дальше |
|---|---|
| `(мера, alts, how)` из `measure_choice` | вызывающие (в т.ч. `slot_measure_uncovered`, гейт величины — по docstring `6639-6649`) |
| текст с дописанными options | `clarify_complete` → потребитель ответа clarify |
| `True`/`False` diverge/conflict | арбитраж кандидатов (вне участка) |
| `decision_id` / sealed `out["options"]` | клиент (кнопки/чип); `diag.decisions_sealed` и т.п. — `7075-7078` |
| `(ticket, None)` или `(None, error_code)` | `consume_decision` / `peek_decision` |
| batch-снимок / reissued out | `lookup_clarify_batch` / `reissue_clarify` |
| `kind=choice_error` dict | `choice_error_response` — docstring: клиенту не отдаётся (`7184`) |
| src settled/focus | `hold_settled_entity` |
| bool стоп2 / список rivals | `stop2_active` / `determined_answer_rivals` |
| `out` с `diag.memory` | `attach_memory_shadow` (ответ не меняет смыслом — `7213`) |

## Обращения наружу

| Место | Что | Назначение |
|---|---|---|
| `db_fingerprint` `6896` | SQL через `psql("SELECT lower(current_database())")` | отпечаток БД в билете; при пустом DSN / исключении — `''` (`6892-6900`) |
| `attach_memory_shadow` `7216-7219` | `ACM.attach_choice_memory(..., psql=psql, tables=TABLES, peek_decision=...)` | shadow-память в `diag`; SQL внутри ACM — вне участка |
| HTTP | нет | — |
| Вызов языковой модели | нет | — |

## Переключатели

| Имя | Место | По умолчанию |
|---|---|---|
| `ASK_RAW_FOCUS_TRUST` | `6871` → `RAW_FOCUS_TRUST` | `"0"` → False; True только если `"1"` |
| `ASK_DECISION_TTL_SEC` | `6872` → `DECISION_TTL_SEC` | `"3600"` (int); в билете TTL не ниже 60 с (`7018`, `7071`, `6983-6984`) |
| `ASK_CHOICE_MEMORY` | используется как `enabled=` в `7219` | чтение env в этом участке **нет** (имя глобала снаружи) |
| `RAW_FOCUS_TRUST` | `7311`, `7320` | аварийно гасит guards/стоп2 при сыром focus/measure_pick |

## Развилки

- `measure_choice`: пустые names/word → `'none'`; один name → `'single'`; exact → `'exact'`; alias 1/`base`/`ask`; substring 1/`base`/`ask`; иначе `'rerank'` (`6652-6691`).
- `resolve_measure`: точное имя / одна подпись / один алиас → имя; несколько → `None` (+ diag); иначе `None` + `measure_unknown` (`6717-6747`).
- `clarify_complete`: нет lines → вернуть txt; все строки есть → body без дописи; иначе дописать (`6769-6777`).
- `answers_diverge`: `<2` figures → False; ветка `sum` или отпечатки; пустой fp → True (`6821-6848`).
- `answers_src_conflict`: `<2` answer с src → False; diverge → False; иначе разные src → True (`6859-6865`).
- `seal_clarify`: не dict / kind не из набора / пустые options → out без изменений (`7032-7038`).
- `consume_decision`: коды `unknown`/`used`/`expired`/`mismatch`/`user_mismatch` (`7084-7105`); успех → ticket used (`7106-7109`).
- `peek_decision`: без проверки question_fp и used (`7112-7132`).
- `lookup_clarify_batch`: `err==user_mismatch` → None; иначе batch по ticket.batch_id или по question_fp+user (`7137-7159`).
- `accumulate_resolution`: пишет src всегда при наличии; measure/axis — только при `ambiguity` (`6977-6982`).
- `hold_settled_entity`: settled vs focus по measure proven / entity locked / holder_srcs / found_by (`7272-7298`).
- `stop2_active`: False если `no_arbiter` или guards_skip; иначе True (`7322-7326`).

## Чего здесь нет

- Постоянное (дисковое/БД) хранение билетов: только процессные dict; рестарт обнуляет (`6869-6870`).
- HTTP-клиент и вызов LLM.
- Сам Handler, который зовёт seal/consume (в участке только функции).
- Чтение env `ASK_CHOICE_MEMORY` (только передача глобала).
- Проверка `question_fp` в `peek_decision`.
- Автоматический вызов `accumulate_resolution` из `consume_decision` (отдельная функция).
- Выдача `choice_error` клиенту из этого участка.
- Реализация `format_clarify_options` и тела `ACM.attach_choice_memory` / `class_meta_of`.
