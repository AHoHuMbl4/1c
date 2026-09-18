# Линза-1 (волна C «один путь»): entity-поиск — карта мест смерти вопроса

Режим: только чтение. Источники: `z06_entity_search.py`, `z07_rrf_vectors.py`,
call-site’ы (grep), константы-потребители, SQL пула вики (куда уезжает `alias_top`).

Два целевых вопроса:
- Q1 «сколько у нас вообще клиентов сейчас» (эталон 361, справочник) — bm25-топ-3
- Q2 «Сколько движений в регистре реализации ТМЦ?» (эталон 80 173) — пробел vs склейка

---

## §1 Пайплайн z06 и z07

### 1.1 `z06_entity_search.py` — вход → шаги → выход

| Функция | Вход | Шаги | Выход | file:line |
|---|---|---|---|---|
| `_like_pattern(alt)` | слово/фраза | lower → экранирование `\ % _` → `%…%`; пустое → `None` | SQL-образец или `None` | z06:20–40 |
| `probe(groups)` | `groups` = список групп альтернатив (`intent.terms`) | на каждое слово: `ts_phrase` / optional `ts_phrase` slop / `ts_levenshtein` / `ts_like`; UNION ALL count; лучший kind на группу; при нуле → `resolve_values` → `_resolve_values_literal` → `_resolve_values_corpus` | `(exprs, diag)` | z06:43–145 |
| `matched_group_count(kinds)` | diag от `probe` | считает int-ключи | int | z06:148–158 |
| `with_refs(expr)` | ts-expr | `doc @@` OR `refs @@ (expr ^ REFS_BOOST)` | строка условия | z06:161–169 |
| `match_expr(exprs, preds)` | exprs + period preds | градиент `ts_compound(…, k)` k=N..1 по count | `(match_sql, best_k)` | z06:172–202 |
| `tables_of(match, preds)` | условие | `GROUP BY src_table` по INDEX/CORPUS | `{src: count}` | z06:205–221 |
| `keep_empty_period_opts(srcs, counted, preds)` | кандидаты + счёт | если есть live — оставить live; иначе при dated preds — все; иначе empty | list | z06:224–239 |
| `alias_hits(exprs, limit)` | exprs + LIMIT | `aliases @@ expr` на `ALIAS_INDEX`, `ORDER BY bm25 DESC LIMIT` | `[src_table…]` или `[]` | z06:242–273 |
| `card_hits(exprs, limit)` | exprs + LIMIT | OR по `CARD_FIELDS` на `CARD_INDEX`, bm25, LIMIT | `[src_table…]` или `[]` | z06:276–314 |
| `question_exprs(exprs, kind_text)` | exprs + kind | отдельный `probe([[kind_text]])`, склейка без дублей | list exprs | z06:317–335 |
| `meaning_candidates(…)` | exprs, kind, question, limit, exclude | `question_exprs` → `_fused_candidates`; fallback: alias+card+near×2 | list src без exclude | z06:338–378 |

### 1.2 `z07_rrf_vectors.py` — вход → шаги → выход

| Функция | Вход | Шаги | Выход | file:line |
|---|---|---|---|---|
| `_rrf_entity_branches` | exprs, kind, question, limit | 4 ветви SQL: alias bm25, card bm25, near(question), near(kind); каждая с `LIMIT limit` | list SQL | z07:48–79 |
| `_rrf_corpus_branch` | vec, limit | IVF kNN `LIMIT TOPK`, агрегат по src, `LIMIT limit` | SQL | z07:82–89 |
| `_fused_sql_rrf` | branches, limit | `SUM(1/(RRF_K+rank))`, `LIMIT limit*len(branches)` | `[src…]` | z07:92–96 |
| `_fused_python_rrf` | branches, limit | per-branch rank + sum; `[:cap]` | list или `None` | z07:100–116 |
| `_fused_candidates` | exprs, kind, question, limit | branches → SQL-RRF (+corpus IVF если флаг) / python fallback | list или `None` | z07:119–170 |
| `near_tables(text, limit)` | текст | emb kNN по CARD/TABLES, `LIMIT` | `[src…]` или `[]` | z07:173–211 |
| `rows_of(src, match, preds, limit, measure)` | источник | строки INDEX/CORPUS, NOT IsFolder, ORDER bm25/nums, LIMIT | rows | z07:214–246 |
| `refuse_text(question)` | вопрос | LLM отказ; цифры вырезаются `_norm_numbers` | строка/`""` | z07:262–284 |
| `rerank(query, docs)` | query+docs | HTTP rerank; fail → `[]` | order indices | z07:287–345 |
| `resolve_values(term)` | слово | kNN resolver (`RESOLVE_NEAR`) → `_shares_chars` → rerank → `RESOLVE_KEEP` | `[value…]` | z07:444–501 |
| `_resolve_values_literal` | term | strip non-alnum, LIKE, prefix≥3, keep≤RESOLVE_KEEP | list | z07:373–417 |
| `_resolve_values_corpus` | term | `ts_like` count на INDEX | `[pat]` или `[]` | z07:420–441 |

### 1.3 Потребители (call-site, grep; файлы не читались целиком)

**Выбор сущности (текущий «один путь») — НЕ через `meaning_candidates`:**

| Call | Где | Что делает с результатом |
|---|---|---|
| `wiki_primary_entity_cascade` | z20:3767–3785 | единственный путь выбора src; пусто → `no_data` |
| → `try_wiki_hybrid_entity_pick` | z21:1302–1304, 1334+ | пул → pick/verify → leader / clarify / None / no_data |
| → `wiki_hybrid_pool` | z21:1345 | SQL `wiki_card_hybrid.sql`; передаёт `alias_top=WIKI_ALIAS_TOP` (z21:306) |
| → `filter_pool_by_named_type` | z21:1348 | молча режет чужой platform_kind |

**z06 после выбора (фильтр строк, не выбор сущности):**

| Call | Где | Роль |
|---|---|---|
| `probe(intent.terms)` | z20:3921 | row-filter; unmatched terms → `no_data` z20:3927–3933 |
| `matched_group_count` | z20:3926 | условие отказа |
| `match_expr` | z20:3934 | SQL match |
| `tables_of` | z20:3938 | diag found |
| `rows_of` | z20:3946, 4061, 3303 | строки / probe окна |
| `keep_empty_period_opts` | z20:1084 | срез пустых по дате |
| `refuse_text` | z20:788+; z21:1327+ | текст отказа |

**z06 meaning-путь (обходной к вики, формы/группы):**

| Call | Где |
|---|---|
| `meaning_candidates` | z05:331, 368; z17:348 |
| `near_tables` / `_fused_candidates` | только из `meaning_candidates` (z06:366–374) |
| `resolve_values` | из `probe` (z06:112) |
| `rerank` | z07:499 (resolve); z10:157; z17:374 |

**Факт:** в текущем каскаде выбора сущности Q1/Q2 идут через `wiki_hybrid_pool` + `alias_idx` LIMIT `:alias_top`, а не через `alias_hits()` z06. Механизм bm25-топ-K тот же индекс/`bm25`, другой call-site.

---

## §2 Таблица «точек смерти»

| file:line | Механизм | Условие | Угроза |
|---|---|---|---|
| `wiki_card_hybrid.sql:142–148` + `z21:15` + `z21:306` | **срез bm25-топ-3** (`LIMIT :alias_top`, default 3) | `aliases @@ question` / `@@ question_raw`; всё ниже 4-го места по bm25 не входит в `struct_alias` | **Q1**: верный каталог клиентов может быть ≥4-м по bm25 и не попасть в alias-слагаемое пула |
| `wiki_card_hybrid.sql:273` + `z21:14` | срез пула `LIMIT :pick_limit` (default 8) | после UNION/filter остаётся >8 | Q1/Q2: кандидат есть в pool CTE, но обрезан финальным LIMIT |
| `wiki_card_hybrid.sql:218–246` | `axis_ok` / `filtered` выкидывают карточки | action_axis/class режут kNN без struct layer | Q2 (класс «движений в регистре»); для `action_class='none'` ось не режет (sql:229) |
| `wiki_card_hybrid.sql:183–196` `struct_named` | стемы raw-вопроса vs `replace(src_table,'_',' ')`+label, len≥4 | пробельная фраза «реализации ТМЦ» vs склейка `…реализациятмц` — совпадение только если `ts_lexize` даст общий стем | **Q2** |
| `wiki_card_hybrid.sql:144–146` | `aliases @@ :question` (целая строка вопроса, не glue-norm) | нет алиаса, совпадающего с токенами «реализации»/«ТМЦ» попарно со склейкой | **Q2** |
| `z21:197–215` `filter_pool_by_named_type` | молчаливый throw из пула | в вопросе назван platform_kind, карточка другого kind | Q2 если тип назван и карточка не того kind → пустой пул → no_data |
| `z21:1351–1362` | пустой пул → `no_data` или `None`+`wiki_empty_pool` | `wiki_hybrid_pool`/`filter` вернули `[]` | Q1/Q2 |
| `z21:1321–1330` / `z20:3776–3785` | `no_data` без меню | нет `picked` после каскада | Q1/Q2 |
| `z21:1389–1393` | verify/pick `outcome=none` → `None` → cascade no_data | модель/verify отвергли всех | Q1/Q2 (после среза пула) |
| `z06:267–270` `alias_hits` LIMIT | срез bm25 (limit=caller) | вызывается из meaning-path, не из wiki cascade | Q1 косвенно только если смысл-путь; **в wiki-пути не зовётся** |
| `z06:84` `probe` | `[], {}` | пустые groups | row-filter; не выбор сущности |
| `z06:3927–3933` (потребитель z20) | unmatched terms → no_data | `matched_groups < n_groups` | после выбора src; Q1/Q2 если terms не матчатся в корпусе |
| `z06:263,272` / `z06:302,313` | `[]` молча | нет exprs / RuntimeError (нет индекса) | meaning-path ослабевает, не меню |
| `z07:146,166,170` `_fused_candidates` | `None` → fallback склейка | нет ветвей / SQL fail | meaning-path |
| `z07:192,204,211` `near_tables` | `[]` | пустой text / нет emb / RuntimeError | meaning-path |
| `z07:382–383,423–424` resolve literal/corpus | `[]` если `len(core)<3` | короткое слово после strip | probe-фолбэк |
| `z07:496–498` | `_shares_chars` отбрасывает near | нет общих триграмм | probe-фолбэк (не Q1/Q2 entity) |
| `z06:35–37` | `_like_pattern` → `None` | пустое слово | вариант `part` не добавляется |
| `z06:224–239` `keep_empty_period_opts` | live-only срез | кто-то live по дате | периодные меню; «сейчас» у Q1 — зависит от preds |

**Где именно «топ-3» bm25 для Q1:**  
`WIKI_ALIAS_TOP` default **3** (`z21_wiki_choice.py:15`) → подстановка `:alias_top` (`z21:306`) → `LIMIT :alias_top` в `struct_alias` (`ubuntu/serenedb/wiki_card_hybrid.sql:147–148`).  
В z06 `alias_hits` тот же паттерн LIMIT, но **не** на пути wiki-выбора сущности.

---

## §3 Константы отсечения

| Имя | Значение (default) | file:line | Что режется |
|---|---|---|---|
| `WIKI_ALIAS_TOP` | **3** (`WIKI_ALIAS_TOP` env) | z21:15; sql:148 | bm25-топ по `alias_idx` в пул вики |
| `WIKI_PICK_N` / `:pick_limit` | **8** | z21:14; sql:273; z21:305 | финальный размер пула карточек |
| `WIKI_KNN_N` / `:knn_limit` | **15** | z21:9; sql:39,54 | kNN соседей на форму вопроса |
| `WIKI_PASSPORT_N` | **8** | z21:21; z21:595,656,700,1110,1177 | паспорта на verify; хвост без полного body |
| `WIKI_PASSPORT_BODY_MAX` | **1500** | z21:23; z21:605,702 | обрезка тела паспорта |
| `WIKI_SEP_GAP` | **0.04** | z21:24; z21:1214 | порог separable топ-2 kNN |
| `WIKI_EMBED_MAXLEN` | **20000** | z21:25; sql:9,23 | substr текста перед `ai_embed` |
| `WIKI_VERIFY_MAX_TOKENS` | **2048** | z21:22; z21:1189 | лимит ответа verify |
| `TOPK` | **40** (`ASK_TOPK`) | z01:59; z07:89; z20:4061 | строки корпуса / IVF inner limit |
| `ROWS_TO_MODEL` | **25** | z01:64 | (не z06/z07 напрямую) |
| `PICK_BUDGET` | **8000** chars | z01:40 | база для MEANING_TOP |
| `MEANING_TOP` | `ASK_MEANING_TOP` или `max(1, PICK_BUDGET//40//4)` = **50** | z08:135–136 | limit `meaning_candidates` / alias/card/near |
| `RRF_K` | **60** | z08:44; z07:94,112 | вес RRF |
| `ASK_SQL_RRF` | **0** (выкл) | z08:47; z07:147 | 5-я corpus-ветвь |
| `SCORER` | **bm25** | z01:153; z06:269; z07:59 | скорер alias/card |
| `REFS_BOOST` | **8.0** | z01:165; z06:169 | вес refs |
| `RESOLVE_NEAR` | **12** | z07:369; z07:474,485 | kNN резолвера |
| `RESOLVE_KEEP` | **3** | z07:370; z07:413,500 | сколько значений оставить |
| `ALIAS_INDEX` | `alias_idx` | z08:34 | индекс синонимов |
| `CARD_INDEX` | `entity_card_idx` | z08:39 | индекс карточки |
| `CARD_FIELDS` | label,aliases,about,quantities,attrs | z08:40 | поля card_hits |
| `STEM_DICT` | `search_dict_stem` | z01:855 | `ts_lexize` в hybrid SQL / меры |
| fuzzy distance | `min(2, len(alt)//4)` | z06:74–75 | порог `ts_levenshtein` |
| like min | пустое → None | z06:36–37 | нет part-варианта |
| literal core | `len(core)<3` → [] | z07:381–382 | resolve literal |
| stem filter hybrid | `length(x) >= 3` / `>= 4` (named) | sql:57,74,190–195 | стоп коротких токенов после lexize |
| `_fused_*` cap | `limit * len(branches)` | z07:96,115–116 | потолок слияния RRF |

Порога веса/скора (min bm25 / min distance) в z06/z07 **не найдено** — только LIMIT и RRF rank.

---

## §4 Нормализация имён

### 4.1 Что есть сейчас

| Функция | Где | Что делает | Участие в поиске entity |
|---|---|---|---|
| `_homonym_norm(s)` | **z21:831–833** | `"".join(str(s).lower().split())` — lower + **удаление пробелов** | **Нет** в построении tsquery/bm25; только homonym keys паспортов (z21:849–855, 1041) |
| `disambiguate_labels` norm | z20:982 | та же: lower + без пробелов | подписи меню, не поиск |
| `_like_pattern` | z06:35–40 | lower + escape + `%…%` | `ts_like` в `probe` (корпус/значения), **не** wiki pool |
| `_resolve_values_literal` / `_resolve_values_corpus` | z07:380,422 | `re.sub(r"[^0-9a-zа-яё]", "", lower)` — **склейка** букв | только фолбэк `probe` |
| `_shares_chars` / `_ngrams` | z08:9–26; z07:504–508 | триграммы после strip non-alnum | гарда резолвера |
| `_norm_ye` | z21:148 | (не читалось тело; имя есть) | не найдено в z06/z07 |
| `ts_lexize(STEM_DICT, …)` | hybrid sql:57+; z21:1528 | стемы, filter len≥3/4 | **да**, `struct_named` / axis / measure |
| `ts_phrase` / analyzer | z06:47–48 | регистр через анализатор | probe |
| `ts_like` part | z06:51–53 | **без** анализатора; слово lower вручную | «склеенные» имена в **корпусе**, не в wiki alias LIMIT |

### 4.2 Q2 «реализации ТМЦ» vs «РеализацияТМЦ»

- Единой норм-функции «пробелы/CamelCase → один ключ» на входе **поиска пула** **не найдено**.
- `_homonym_norm` дала бы `реализациитмц` vs stem `реализациятмц` — **разные** строки (и/я); даже при подключении к поиску тождества нет без стеммера.
- Wiki: `aliases @@ :'question'` / `@@ :'question_raw'` — сырая строка вопроса (`wiki_card_hybrid.sql:144–146`); glue-norm нет.
- Wiki: `struct_named` сравнивает стемы raw-вопроса со стемами `replace(src_table,'_',' ')` + label (`sql:189–195`); пробельная фраза vs однотокенная склейка — риск разъезда на уровне `ts_lexize`.
- z06 `ts_like('%реализации тмц%')` не матчит подстроку без пробела `реализациятмц` (пробел в образце обязателен).

### 4.3 Точка входа для единой норм-функции

Измеримые кандидаты (где сейчас нормализуют по-разному):

1. **До SQL пула:** `_wiki_hybrid_vars` (`z21:281–308`) — поля `question` / `question_raw` перед подстановкой.
2. **Рядом с уже существующим API:** `_homonym_norm` (`z21:831`) — единственная явная «lower+без пробелов»; сейчас только post-pick homonym.
3. **В probe:** `_like_pattern` / strip в resolve (`z06:35`, `z07:380`) — параллельные strip-логики без единого имени.

---

## §5 Факты для дизайна LLM-резолвера: где полный пул ещё цел

| Точка | Полный ли пул | file:line | Комментарий |
|---|---|---|---|
| До `LIMIT :alias_top` внутри `struct_alias` | теоретически все hit `aliases @@ q` | sql:142–148 | **в Python не материализуется**; срез в SQL |
| CTE `pool` (UNION knn∪struct_*) | шире alias-top, но alias-ветвь уже урезана | sql:197–211 | полный union **после** alias LIMIT 3 |
| После `filtered`, до `LIMIT :pick_limit` | ещё шире pick_limit, уже после axis/class | sql:241–273 | ближайшая «полная» выдача SQL до среза 8 |
| `wiki_hybrid_pool` return | уже ≤ pick_limit | z21:323–362 | поздно: срезы alias_top + pick_limit + filter SQL уже были |
| После `filter_pool_by_named_type` | ещё уже | z21:1348 | доп. срез kind |
| `alias_hits` / `_rrf_entity_branches` | уже LIMIT на ветвь | z06:267–270; z07:55–65 | meaning-path; не wiki cascade |
| `_fused_sql_rrf` / python | уже `limit*branches` | z07:94–96,115–116 | после per-branch LIMIT |
| `meaning_candidates` output | после fuse + exclude | z06:365–378 | не путь выбора сущности |

**Вывод для резолвера (факт):**  
единственное место, где bm25-кандидаты по словарю ещё **не** срезаны до 3, — **внутри** запроса `struct_alias` **до** `LIMIT :alias_top` (`wiki_card_hybrid.sql:142–148`). Сейчас этот полный список **нигде в Python не доступен**.  
Чтобы отдать LLM-резолверу полный alias-пул вместо среза, нужна смена SQL/контракта (убрать или поднять LIMIT / вернуть неограниченный ordered set в отдельный CTE), либо отдельный запрос без `:alias_top` до вызова резолвера.  
После `wiki_hybrid_pool` полного alias-топа уже нет.

**Таблицы/индексы словаря, читаемые на путях entity:**

| Объект | Где |
|---|---|
| `alias_idx` / `search_entity_alias` | sql:143–149; z06:267–270; z07:57–59; z20:1010 |
| `search_wiki_entity_card` | sql:36+; z21:1341,1345 |
| `search_tables` | sql:65,98,188,213–216 |
| `search_measure_alias` | sql:162–171; z21:1526 |
| `search_refcols` | sql:84–90,232–238 |
| `entity_card_idx` / `search_entity_card` | z06:305–311; z07:60–65; CARD |
| `search_dict_stem` (`STEM_DICT`) | sql `ts_lexize`; z01:855 |
| `resolver_index` | z07:385+,476+ |
| корпус/`INDEX` | probe/match/rows_of |

Фильтр kind/рода в wiki SQL: `action_class` event/object/none + LIKE `catalog_%` / `document_%` / `accumulationregister_%` (`sql:241–256`); в z06 kind — отдельный `probe([[kind_text]])` в `question_exprs` (z06:329–335), без kind-filter на alias_hits.

---

## Не найдено

- Порог min-score / min-bm25 / min-distance на отсев кандидатов в z06/z07.
- `websearch_to_tsquery` / явный stopword-список в z06/z07 (стоп коротких — `length(x)>=3|4` после `ts_lexize` в hybrid SQL).
- Вызова `meaning_candidates` / `alias_hits` из `z20`/`z21` на пути выбора сущности (только wiki cascade).
- Норм-функции, склеивающей пробелы **на входе** `aliases @@` / `struct_named` (есть только `_homonym_norm` post-factum).
)
