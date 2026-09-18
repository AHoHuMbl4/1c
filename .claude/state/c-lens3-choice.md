# Линза-3 (волна C «один путь»): выбор сущности/меры — карта мест смерти

Только факты из `z21_wiki_choice.py` и `z14_clarify_memory.py` (+ SQL-шаблон, который z21 читает). Мнений нет.

---

## §1 пайплайн z21 (пул → лидер → верификация → меню/leader)

### Константы отсечения (`z21_wiki_choice.py`)

| Константа | default | file:line | роль |
|---|---|---|---|
| `WIKI_KNN_N` | 15 | 9 | `knn_limit` в SQL пула |
| `WIKI_PICK_N` | 8 | 14 | `pick_limit` — финальный размер пула карточек |
| `WIKI_ALIAS_TOP` | 3 | 15 | `alias_top` — топ словаря bm25 в SQL |
| `WIKI_PASSPORT_N` | 8 | 21 | сколько паспортов уходит в verify / format |
| `WIKI_VERIFY_MAX_TOKENS` | 2048 | 22 | потолок ответа verify |
| `WIKI_PASSPORT_BODY_MAX` | 1500 | 23 | обрезка wiki body |
| `WIKI_SEP_GAP` | 0.04 | 24 | порог kNN-gap для «separable» |
| `WIKI_EMBED_MAXLEN` | 20000 | 25 | длина текста в `ai_embed` |

### Построение пула

1. **Вход:** `try_wiki_hybrid_entity_pick` → `wiki_hybrid_pool(question, intent)` (1345, 323–362).
2. **Переменные SQL** `_wiki_hybrid_vars` (281–308): `question` (= `search_form` или сырой), `question_raw`, `knn_limit=WIKI_KNN_N`, `pick_limit=WIKI_PICK_N`, `alias_top=WIKI_ALIAS_TOP`, `action_class`, `action_axis` (`wiki_axis_phrase`), `want_agg`, `stem_dict`, `measure`.
3. **Шаблон:** `ASK_ROOT / "wiki_card_hybrid.sql"` (31–35). Слагаемые UNION в SQL (файл вне зоны чтения целиком; имена CTE видны из комментариев/параметров z21):
   - kNN по `search_form` (`knn`, LIMIT `:knn_limit`);
   - kNN по сырому вопросу (`knn_raw`);
   - struct по оси/классу (`struct_catalog` / `struct_register` / `struct_move` / `struct_catalog_event`);
   - словарь alias bm25 (`struct_alias`, LIMIT `:alias_top`) — слово `bm25` в z21 **не найдено**, параметр `alias_top` есть (306);
   - носители меры (`struct_measure` по `intent.measure`);
   - именованные (`struct_named`);
   - финал: `LIMIT :pick_limit` (= `WIKI_PICK_N`).
4. **Пустой вопрос / нет embed secret / RuntimeError psql** → `[]` (325–326, 329–330, 339–340).
5. **После пула:** `filter_pool_by_named_type` (1348, 197–215) — режет чужой OData-kind, если в вопросе назван род платформы; пустой после фильтра → каскад no_data (коммент 201).
6. **Паспорта:** не в пуле; `wiki_passport_enrich` берёт `cards[:WIKI_PASSPORT_N]` (656–657), догружает wiki body; хвост `cards[WIKI_PASSPORT_N:]` без body (691–692). В verify в модель: только `full = enriched[:WIKI_PASSPORT_N]` (1177–1178); хвост — «Other pool names only» (717–721).

### Выбор лидера / verify

| ветка | file:line | поведение |
|---|---|---|
| `len(cards)==1` | 1363–1366 | сразу `wiki_verify_candidates` (без pick-LLM) |
| `len(cards)>1` | 1367–1386 | `wiki_pick_from_cards` → затем **всегда** `wiki_verify_candidates` на том же `cards`; при outcome verify ∈ {leader,clarify,none} **перезаписывает** `pick` (1377–1378) |
| pick `degraded` | 1370–1372, 1386–1388 | `wiki_pick=fallback`, **`return None`** |
| pick/verify `none` | 1389–1393 | `wiki_none=<reason>`, **`return None`** |
| `clarify` | 1394–1398 | `wiki_entity_clarify_menu` (меню) |
| `leader` | 1399–1408 | `wiki_leader_post_verify` → при False **`return None`**; иначе `wiki_leader_db_homonym_gate`; иначе `{picked:[leader]}` |

### `wiki_outcome_from_verify` (1107–1167) — сколько доходят до сравнения

- Сравниваются только `passports[:WIKI_PASSPORT_N]` (1110).
- **leader:** ровно 1× `yes`, все остальные `no`, 0× `unsure` (1132–1150); иначе при ≥1 неотвергнутом → clarify (1154–1167); 0 yes и 0 unsure → `none`/`verify_none` (1151–1153).
- Пропуск вердикта ≠ `no` — в лидера не пускает (коммент 1130–1131).
- Одноимённые peer другого kind при sole-yes → clarify, не silent leader (1139–1148).

### Провал верификации → кто обрабатывает `None`

| источник `None` / no_data | file:line | кто дальше |
|---|---|---|
| нет таблицы `search_wiki_entity_card` / RuntimeError | 1341–1344 | `return None` → `wiki_primary_entity_cascade` |
| пустой пул + `question_expects_accounting_data` | 1360–1362 | `return None` (+ `wiki_empty_pool`) |
| пустой пул + НЕ expects | 1352–1359 | сразу `{kind: no_data}` (не None) |
| pick/verify degraded / none / post_verify False / нет leader | 1370–1409 | `return None` |
| `wiki_primary_entity_cascade`: `_wiki is None` и нет `wiki_pick` | 1312–1313 | ставит `wiki_pick=fallback` |
| `wiki_primary_entity_cascade`: `not picked` | 1321–1330 | **`{kind: no_data}`** с `reason=wiki_pick\|wiki_empty_pool\|wiki_no_leader` |
| `_wiki.kind` ∈ {no_data, clarify, answer} | 1305–1306 | возвращает как есть (меню/ответ/отказ) |

Цитата каскада (1296–1298): «Если wiki вернула None без своего wiki_pick — в diag ставится wiki_pick=fallback … дальше честный no_data.»

### Меню сущности

- `wiki_entity_clarify_menu` (944–1005): `len(tied)<2` → `None` (962–963); `len(opts)<2` → `None` (997–998); иначе `finalize_clarify_menu` / readings_menu.
- Clarify из verify: reason `wiki_separability` (1395–1398).
- D2 db-гомоним: reason `wiki_homonym_db` (1098–1101).

---

## §2 пайплайн z14 (мера: хиты, single-шорткорт, proven, тикеты)

### `measure_choice(names, word, alias_by)` — 49–90

| условие | return | file:line |
|---|---|---|
| `not names` | `(None, [], 'none')` | 63–64 |
| `not wl` (пустое слово) | `(None, [], 'none')` | 65–66 |
| `len(names)==1` | `(names[0], [], 'single')` — **без проверки слова** | 67–68 |
| exact `n.lower()==wl` | `(exact[0], [], 'exact')` — молча 1 | 71–73 |
| alias: `len(covered)==1` | `(covered[0], [], 'alias')` — молча 1 | 77–78 |
| alias: `len(covered)>1` | `(None, covered, 'ask')` — меню | 79–81 |
| substring `wl in n.lower()`, >1 | `(None, same+rest, 'ask')` | 82–87 |
| substring ==1 | `(same[0], [], 'substring')` — молча 1 | 88–89 |
| иначе | `(None, [], 'rerank')` — **не меню, не отказ**; вызывающий | 90 |

### `_word_hits_text(wl, text)` — 35–39

- `t = text.strip().lower()`; отказ если `len(wl)<2` или `len(t)<2`.
- True если `wl == t` **или** `wl in t` **или** `t in wl` (exact/подстрока в обе стороны).
- Call-site в этом файле: только alias-ветка `measure_choice` (76).

### `resolve_measure` — 114–146

- пустой text → `None` (116–120);
- точное имя в `measures` → имя (121–122);
- caption / alias по `norm = lower+без пробелов` (125): ровно 1 → имя; >1 → `None` + `measure_ambiguous_pick` (128–143);
- не узнали → `None` + `measure_unknown` (144–146).

### Proven / тикеты

| символ | file:line | смысл |
|---|---|---|
| `DECISION_TTL_SEC` | 164 | TTL билетов (env `ASK_DECISION_TTL_SEC`, default 3600) |
| `_DECISIONS` / `issue_decision` / `consume_decision` | 166, 284–332, 390–417 | одноразовый `decision_id` |
| `choice_levels_proven` | 514–530 | уровни entity/measure/axis/period из `resolved`+`trusted` |
| `measure_already_proven` | 533–537 | True если `measure_pick` **или** `"measure" in choice_levels_proven` |
| `choice_proven(trusted, ambiguity)` | 505–511 | билет доказал выбор (опц. предмет) |
| `accumulate_resolution` | 262–281 | после consume пишет src/measure/axis/period |
| `hold_settled_entity` | 545–579 | при proven measure держит settled src (559–560) |

### Где мера берётся молча при неоднозначности (внутри z14)

- `len(names)==1` → `'single'` без слова (67–68) — единственность по данным, не по слову.
- `'exact'` / `'alias'`(1) / `'substring'`(1) — молчаливый выбор одного имени (71–89).
- `measure_already_proven` — не выбирает меру сам; сигнализирует вызывающему, что билет/`measure_pick` уже снял неоднозначность (533–537).

### Где вопрос «умирает», если мера не определилась

**В z14 ветки `{kind: no_data}` / отказа по мере не найдено.**  
Ближайшее: `resolve_measure` → `None` (неоднозначно/неизвестно); `measure_choice` → `'none'` / `'rerank'` / `'ask'`. Смерть вопроса при незакрытой мере — **вне** этих двух файлов (caller `_settle_measure` в z20: при `_need` и >1 имён → `(None, list(names))` меню; при `(None, [])` — дальше по тракту; это не цитата z14).

---

## §3 таблица «точек смерти» (пустота / None без меню и без ответа)

Механизм = ранний return пустоты/`None`/`no_data`/`answer` без числа, без `finalize_clarify_menu`.

### z21

| file:line | механизм | условие | чем грозит |
|---|---|---|---|
| 325–326 | `wiki_hybrid_pool` → `[]` | пустой `question` | пул пуст → ниже no_data/None |
| 329–330 | `[]` | RuntimeError `_ensure_embed_secret` | то же |
| 339–340 | `[]` | RuntimeError `psql` | то же |
| 410 | `wiki_strip_passport_yaml` → `""` | только frontmatter без закрытия | пустое тело паспорта (не смерть вопроса) |
| 485–486, 492–493 | `fork_labels_of` → `{}` | нет key/srcs или RuntimeError | подписи вилок пусты |
| 510–511, 517–518 | `fork_labels_covering` → `{}, None` | нет srcs / RuntimeError | то же |
| 596–597 | passport SQL → `""` | нет tables после среза `[:WIKI_PASSPORT_N]` | enrich без wiki body |
| 734–746 | `_wiki_row_to_verdict` → `None` | битый index/fit | вердикт отброшен |
| 808–809, 812–816… | parse verify → `[], failed` | пустой raw / битый JSON | → degraded/none |
| 886–887, 897–898 | `wiki_load_cards_by_src` → `{}` | нет srcs / RuntimeError | кандидаты гомонима без карточек |
| 925–926 | `wiki_db_homonym_peer_rows` → `[]` | пустой leader/label_norm | пиров нет |
| 962–963, 997–998 | `wiki_entity_clarify_menu` → `None` | `<2` tied/opts | clarify не собралось |
| 1008–1023 | `wiki_homonym_peer_fail_soft` | SQL-сбой peer-check | `{kind:answer}` текст без числа (не меню) |
| 1030–1031 | gate → `None` | пустой leader | = оставить leader (не смерть) |
| 1042–1043, 1058–1059, 1063–1064, 1077–1078 | gate → `None` | нет label_norm / n_peers≤1 / named-kind не даёт иных / нет peers_src | silent leader |
| 1036–1037, 1050–1051, 1067–1071, 1103–1104 | fail_soft / fail_soft | RuntimeError peer SQL / menu None | answer без числа |
| 1111–1112 | outcome `none` | empty_passports | verify none |
| 1136–1138 | outcome `none` | `axis_reject` на sole-yes | лидер отвергнут |
| 1151–1157 | outcome `none` | verify_none | все no / нет tie |
| 1174–1175 | verify → none | empty_pool | нет карточек |
| 1190–1192, 1196–1199 | outcome `degraded` | модель упала / parse failed | → cascade None→no_data |
| 1236–1237, 1267–1281 | pick → none | empty / choice0 / bad_index / bad_src / axis_reject | нет лидера |
| 1250–1252 | pick → degraded | ds_chat Exception | fallback |
| 1321–1330 | **no_data** | `not picked` после wiki | отказ при живых данных, если пул/verify/post_verify срезали |
| 1341–1344 | `None` | нет wiki-карточек / RE | fallback→no_data |
| 1352–1359 | **no_data** | empty pool ∧ ¬expects_accounting | отказ |
| 1360–1362 | `None` | empty pool ∧ expects | empty_pool→no_data в cascade |
| 1370–1372, 1386–1388 | `None` | degraded pick/verify | fallback→no_data |
| 1389–1393 | `None` | outcome none | wiki_none→no_data |
| 1401–1402 | `None` | `wiki_leader_post_verify` False | measure/axis not carried → no_data |
| 1409 | `None` | нет leader в pick | no_data |

### z14

| file:line | механизм | условие | чем грозит |
|---|---|---|---|
| 63–66 | `measure_choice` `'none'` | нет names / нет word | вызывающий без меры |
| 90 | `'rerank'` | слово не попало | вызывающий (не меню в z14) |
| 116–120, 130–133, 140–146 | `resolve_measure` → `None` | пусто / ambiguous / unknown | выбор человека не сведён |
| 394–395, 399–400 | `consume_decision` error | пустой/unknown id | билет не погашен |
| 401–406 | used / expired | повтор / TTL | ошибка клика |
| 407–413 | mismatch / user_mismatch | fp/db/user | то же |
| 424–434 | `peek_decision` None | unknown/expired/mismatch | нет билета |
| 445–446, 467 | `lookup_clarify_batch` None | user_mismatch / нет batch | reissue невозможен |
| 472–473 | `reissue_clarify` None | batch не dict | — |
| 505–508 | `choice_proven` False | нет trusted | уровень не снят |

---

## §4 `_homonym_norm` и прочая нормализация

### `_homonym_norm(s)` — z21:831–833

- Сигнатура: `(s) -> str`.
- Поведение: `"".join(str(s).lower().split())` — lower + удаление **всех** пробельных (склейка токенов). Коммент: «Та же нормализация, что у `disambiguate_labels`».
- **Не** трогает ё/е, дефисы, пунктуацию (кроме пробелов).

**Call-site'ы в z21:**

| line | контекст |
|---|---|
| 849 | `_homonym_keys`: норм `name` паспорта |
| 853 | `_homonym_keys`: норм stem `src.split("_",1)[1]` |
| 1041 | `wiki_leader_db_homonym_gate`: `label_norm = _homonym_norm(label)` перед count/peer SQL |

### Класс D2-гомонима (после успешного post_verify)

Поток в `try_wiki_hybrid_entity_pick` (1399–1408):

1. `wiki_leader_post_verify` True.
2. `wiki_leader_db_homonym_gate` (1026–1104):
   - label лидера из `TABLES`;
   - `label_norm = _homonym_norm(label)`;
   - count строк с тем же `regexp_replace(lower(label), '\s|\p{Z}', '', 'g')` (1047–1058) — SQL-эквивалент склейки пробелов;
   - если `n_peers > 1` и named-kind допускает иной kind → `wiki_db_homonym_peer_rows` (без LIMIT на сборе, 920–921);
   - меню через `wiki_entity_clarify_menu(..., reason="wiki_homonym_db")` с `skip_empty_filter` (980–983);
   - menu None → fail_soft answer (1102–1104).
3. Если gate вернул `None` (нет пиров) → silent `{picked:[leader]}` (1408).

**Параллельный in-pool гомоним (S2-b):** `wiki_homonym_kind_peers` (859–880) внутри `wiki_outcome_from_verify` при sole-yes — peers по `_homonym_keys` ∩ другой OData-kind → clarify до leader (1139–1148). Это **до** post_verify/db-gate.

### Прочая нормализация (оба файла)

| символ | file:line | что делает |
|---|---|---|
| `_norm_ye` | z21:148–149 | lower + `ё→е` (named platform types) |
| `question_fingerprint` | z14:172–175 | lower + collapse spaces → sha256[:32] |
| `resolve_measure` norm | z14:125 | `"".join(lower.split())` — как `_homonym_norm` |
| `_alias_parts` key | z14:27 | `casefold()` дедуп алиасов |
| `_word_hits_text` | z14:36 | `.lower()` + подстрока |

---

## §5 точки отдачи полного пула в резолвер (до среза / до лидера)

Где **целиком** доступен набор кандидатов с человеческими полями (name/description/axes/measures/label), ещё **до** LLM-лидера или до top-K паспортов.

### Сущности (z21)

| точка | file:line | что есть | срез уже? |
|---|---|---|---|
| результат `wiki_hybrid_pool` | 323–362, вызывается 1345 | список карточек: `src_table, name, description, axes, measures, covered, distance, parent, platform_kind` | да: SQL уже `LIMIT WIKI_PICK_N`; kNN внутри `WIKI_KNN_N` |
| сразу после `filter_pool_by_named_type` | 1348–1351 | тот же пул + `diag.wiki_pool` | named-type мог урезать; **до** pick/verify |
| `wiki_format_card_lines(cards)` | 365–376, зов 1240 | все карточки пула в текст модели pick | pick видит полный post-filter пул (≤PICK_N), не сырой kNN |
| `wiki_passport_enrich` вход `cards` | 651–693 | full cards; enrich только `[:PASSPORT_N]` | полный список ещё в `cards` аргументе **до** среза enrich |
| `wiki_verify_candidates` | 1170–1178 | `cards` целиком → enrich → в LLM только `[:PASSPORT_N]` + имена хвоста | **окно для резолвера «где что»:** аргумент `cards` до строки 1177 |
| clarify candidates | 1394–1398, 1098–1101 | подмножество tie/homonym peers с name | уже после выбора, не полный пул |
| `wiki_menu_captions` / `wiki_captions_map_from_cards` | 533–591 | N→N подписи из name/wiki_body | форматтер меню, не резолвер |

**Не найдено** в z21: API, отдающий пул **до** SQL `pick_limit` / до объединения CTE наружу в Python.

### Меры (z14)

| точка | file:line | что есть | срез уже? |
|---|---|---|---|
| аргумент `names` в `measure_choice` | 49–90 | полный список имён мер сущности от вызывающего | срез снаружи (`measures_of`); внутри z14 **не** режется |
| `alias_by` + `_alias_parts` | 9–32, 74–76 | человеческие алиасы по имени меры | полный словарь алиасов сущности |
| `measure_captions(measures, alias_by)` | 93–111 | `{measure: human_caption}` для **всех** переданных measures | полный набор подписей до выбора |
| `'ask'` ветки | 79–87 | `covered` или `same+rest` как alts | уже отфильтрованный hit-set, не все names (кроме дописывания rest при substring>1) |

**Не найдено** в z14: сбор списка мер из БД (это `measures_of` / снаружи).

---

## Итог для волны C (факты, не мнения)

1. Смерть сущности при живых данных чаще всего: `return None` из `try_wiki_hybrid_entity_pick` (verify none / degraded / post_verify measure|axis not carried / empty pool) → `wiki_primary_entity_cascade` 1321–1330 → `no_data`.
2. Молчаливый sole-leader после verify возможен; D2 db-gate и in-pool `wiki_homonym_kind_peers` — два разных барьера гомонима.
3. Мера: `'single'` без слова и exact/alias/substring(1) — молчаливые ветки; `'ask'` уже требует меню; смерть вопроса по мере в этих двух файлах **не найдена**.
)
