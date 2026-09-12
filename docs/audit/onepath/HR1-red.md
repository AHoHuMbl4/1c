# HR1-red — атака тема-гейта H1 (`wiki_leader_topic_gate`)

Дата: 12.09.2026. Режим: read-only + локальные замки + попытка curl
`:8092` / SELECT. Код / git / прод не менялись. Чужие HR-отчёты не читались.

Опора: `ubuntu/serenedb/ask/z21_wiki_choice.py`, `wiki_passport.sql`,
`test_wiki_topic_gate.py`, `docs/audit/onepath/{G1,G2,G3,H1-impl,E2-final}.md`.

---

## Вердикт

К выкату — нет. Замок Б4/пересчёта зелёный (26/0), калибровочные wrong на
чистом паспорте ловятся, но есть обход меню verify, утечка темы через
`wiki_body` с early-affirm ложного лидера и over-cut уверенных
content-вопросов (compare / «продажи» / оси). Живой `:8092` с этой среды
недоступен — вердикт по коду + оффлайн-матрице + фактам паспортов G1.

---

## 1. Уверенные ответы: класс × ветка × вердикт

Морфология (`_wiki_topic_stem_match` / `_wiki_topic_domain_root`):

| словоформа | domain root | stem↔«склад» |
|---|---|---|
| складе / складом / склады / складах / складской | `склад` | да |
| складирование | `склад` | да |
| наскладе (слитно) | нет | да (подстрока в токене текста) |

Падежи «складом/склады/на складе» корень `склад` ловят (не проспект).

| класс | ветка | вердикт |
|---|---|---|
| named «ёлочки»/кавычки | `named_exempt` → OK | пройдёт |
| label куском / `реализациятмц` без кавычек | `label_in_question` (пробелы схлопнуты) | пройдёт |
| aliases / best_used_for (прайс, поставщики, сотруд*) | `topic_ok:domain` | пройдёт при терме на positive |
| count «сколько всего записей?» | `empty_topic` | зарежется (ожидаемо) |
| пустой / `hi` (нет токенов ≥3) | `no_topic_stems` fail-open | пройдёт любого лидера |
| domain склад/прайс/остат/… | все required в bag | OK носитель / CUT чужой |
| compare «сравни продажи … месяца …» | content, все термы | CUT даже Реализации (`сравни`/`продажи`/`этого`/`прошлого` ∉ bag) |
| ось «продаж по контрагенту» | content AND | CUT: `контрагенту`≈ось OK, `продаж`≠`реализация` |
| мера «по сумме реализации» | content | пройдёт |
| «товарооборот» / «операций в системе» | content | CUT |

Находка over-cut: без domain-корня каждый content-терм обязателен.
Стоп периода (месяц и формы) снимается лишь при заполненном
`intent.period`; связки «сравни/этого/прошлого/продажи» остаются и режут
верного лидера. Ветки: `_wiki_topic_required_terms` 1358–1369 →
`wiki_passport_topic_confirm` 1509–1511.

Находка fail-open: вопрос без substantive-токенов → `no_topic_stems` →
sole-yes любого лидера проходит (1481–1507).

---

## 2. Пересчёт пула / меню / homonym

### 2.1 Как «Реализация ТМЦ» выживает на вопросе про склад

Два канала (код + оффлайн-прогон):

**A. Verify-clarify обходит гейт (источник меню с Реализацией).**

В `try_wiki_hybrid_entity_pick` при `outcome == "clarify"` сразу
`readings_menu(..., reason="wiki_separability")` — строки 1165–1182.
`wiki_leader_topic_gate` вызывается только при `outcome=leader` (1183+).
Меню `wiki_separability` с Реализацией + Местами Хранения темой
не фильтруется. Это объясняет «склад → меню с Реализация ТМЦ».

**B. `wiki_body` в positive bag + early-affirm.**

G3-Б4 мешок: `label|aliases|best_used_for|measures|оси|src_table`
(без wiki_body). H1 добавил `wiki_body|description`
(`_wiki_topic_positive_bag` 1386–1398).

Оффлайн: чистый паспорт продаж → `topic_miss:domain` → repick на
`catalog_местахранения`. Тот же лидер с `wiki_body="…со склада…"` →
`topic_ok:domain` и early return утверждает продажи, даже если в пуле
есть Места Хранения (строки 1537–1543: при ok лидера сразу return).

Ось `МестоХранения -> catalog_местахранения` сама тему «склад» не даёт
(левая часть без «склад»; FK цель отброшена — замок FK это ловит).
Wiki/measures/aliases/best_used_for со словом «склад» — дают.

По паспорту (факты G1 SELECT на окне; живой SELECT с этой LXC — пустой/
завис, см. §5): у `accumulationregister_реализациятмц` в nef нет
«склад/остат»; в alias-топе по «склад» её нет; носитель aliases «склады»
— `catalog_местахранения`. На чистых полях карточки гейт Реализацию режет;
выживание — через A или утечку текста wiki (B).

### 2.2 Циклы / двойное меню

В одном проходе hybrid: либо verify-меню, либо topic-меню, либо none/leader.
Цикла repick→verify нет. Двух меню в одном ответе нет; два разных
источника меню (`wiki_separability` vs `wiki_topic`) — разная семантика.

### 2.3 Homonym vs topic

Homonym (`wiki_homonym_kind_peers`) внутри `wiki_outcome_from_verify` до
гейта. После `topic_repick` повторного homonym-check нет (только
`wiki_leader_post_verify` мер/оси) — `z21:1190–1197`. Repick способен
вернуть одноимённого peer другого kind, которого homonym раньше увёл бы
в clarify.

---

## 3. Замки

| проба | итог |
|---|---|
| `test_wiki_topic_gate.py` | 26/0 |
| симуляция сломанного гейта (topic-confirm всегда True) | ≥7 asserts краснеют (G3 wrongs, сброс лидера, repick, topic_none, empty_topic, ops) — замок реагирует |
| `test_one_path.py` (вкл. «ж») | 81/0 |
| тракты E2-final (+ H1: period/domain) | зелёные почти все; timeout 120с: `test_k6_rank_v2.py`, `test_ab_calendar_axis_set.py` (живой DSN/тяжёлый импорт — не регресс Б4) |
| homonym / captions / candidate_verify / intent / compose / gate | OK (10/0, 24/0, 64/0, 162/0, 91, 56/0) |

Замок не покрывает: verify-clarify bypass; wiki_body leak; over-cut
compare; homonym после repick.

---

## 4. SQL паспортов

`wiki_passport.sql` 7–21: один SELECT, LEFT JOIN wiki/tables/alias,
IN-список src — N+1 нет (подстановка в `_wiki_substitute_passport_sql`
582–594, top≤`WIKI_PASSPORT_N`).

Порядковые индексы совпадают с `wiki_passport_enrich` 654–660:

| idx | SQL | enrich |
|---|---|---|
| r[0] | src_table | ключ |
| r[2] | wiki_body | wiki_body |
| r[5] | parent | parent |
| r[7] | not_enough_for | not_enough_for |
| r[8] | aliases | aliases |
| r[9] | best_used_for | best_used_for |

Параметры src_list / body_max подставляются строкой; psql-директива set
в шаблоне снимается перед исполнением. Замечание: enrich пишет
aliases/buf только если поле на карточке ещё пусто.

Живой ordinal-smoke на `:7890` с этой среды: соединения зависали / 0 строк —
индексы сверены чтением кода, не живым SELECT.

---

## 5. Живое (`:8092`)

| попытка | результат |
|---|---|
| `127.0.0.1:8092/health` | нет слушателя (000) |
| ssh `gpu-erw:2202` / egress на хост | RUNTIME_FLOOR (secret-read / egress) |
| SELECT паспортов okna на local `:7890` | timeout / пустой stdout |

Размытые + named curl с этой сессии не сняты. Опора на smoke постановки
(склад→меню Места Хранения, прайс→no_data) и оффлайн-атаку выше. Перед
выкатом — повтор curl на окне по V3-формату.

---

## 6. Кандидаты правок (файл:строка)

1. `z21_wiki_choice.py:1165–1182` — candidates clarify через тот же
   topic-confirm/пересчёт, что у гейта; Реализация на «склад» выпадает из
   меню до `readings_menu`.
2. `z21_wiki_choice.py:1386–1398` — positive bag без `wiki_body`/`description`
   (мешок G3); иначе wiki-only hit не early-affirm.
3. `z21_wiki_choice.py:1537–1543` — при ok лидера сравнить score с пулом;
   при равном max и ≥2 носителях → clarify вместо silent leader.
4. `z21_wiki_choice.py:1509–1511` + `1358–1369` — AND по content режет
   compare/«продажи»; связки и синонимы без domain — ложные CUT.
5. `z21_wiki_choice.py:1190–1197` — после `topic_repick` снова
   `wiki_homonym_kind_peers`.
6. `test_wiki_topic_gate.py` — кейсы: verify-bypass; wiki_body leak;
   compare на верном; homonym после repick.

---

## Итог одной строкой

Гейт ловит калибровочные wrong на чистом паспорте и закрыт замком 26/0, но
не закрывает меню verify, утверждает ложного лидера при «склад» в
wiki_body и режет уверенные compare/синонимы — к выкату сначала пункты 1–3,
плюс живой прогон `:8092`.
