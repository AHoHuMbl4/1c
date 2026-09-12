# H1 — внедрение: лидер только при подтверждении темой (G2 + G3-Б4)

Дата: 12.09.2026. Режим: код + замки; **git/psql/полигон/прод не трогались**.

Опора: `docs/audit/onepath/G2-Проект.md`, `docs/audit/onepath/G3-Калибровка.md` (Б4).

---

## Вердикт

`wiki_leader_topic_gate` встроен в hybrid-каскад z21 **после** `wiki_leader_post_verify`.
Sole-yes лидер утверждается только по Б4; провал → пересчёт пула (repick / меню /
честный `none`), не молчаливое число. Промт `WIKI_VERIFY_SYS` не менялся.

---

## Правило Б4 — как реализовано

Функции: `wiki_passport_topic_confirm` → `wiki_leader_topic_gate`
(`ubuntu/serenedb/ask/z21_wiki_choice.py`).

1. **Пустой вопрос** (`not q.strip()`) → reject (`empty_question`).
2. **doesNotAnswer (А′)** — любой content-терм вопроса, который есть в
   `not_enough_for` и **нет** на положительной поверхности → reject (`nef`).
   Self-hit на positive не режет (валюты/организации).
3. **Named-exempt:** токен в «ёлочках»/кавычках совпал со stem `src_table` после
   `_` или с `name`/`label` → OK.
4. **Label-exempt:** нормализованный label явным куском входит в вопрос → OK.
5. Content-термы = токены вопроса минус стоп (сколько/записей/движений/регистр*/…
   + периодные при наличии `intent.period`).
6. **Domain-first:** если токен матчит корень из общего словаря словоформ
   (`склад прайс остат цен клиент постав сотруд валют орган`) — required =
   эти корни; иначе required = все content-термы.
7. Каждый required обязан найтись в положительном мешке:
   `name|label|aliases|best_used_for|wiki_body|description|measures|src_table|
   имена осей (левая часть до →)`. Цель FK оси **не** подтверждает тему.
8. Морфология: общий префикс ≥4 букв, хвост ≤3 (`складе`↔`склад`,
   `организаций`↔`организации`, `табелю`↔`табель`).
9. Нет substantive-термов (len≥3) → G2 fail-open `no_topic_stems` (нечего
   подтверждать). Были стоп-слова учёта, темы не осталось → B4 reject
   `empty_topic`.

**Пересчёт (G2) при провале лидера:** все паспорта пула через тот же confirm;
среди выживших — max score покрытия required; `|C|=1` → repick + снова
post_verify; `|C|≥2` → clarify-меню (`reason=wiki_topic`); `|C|=0` →
`wiki_none=topic_*` / честный no_data вверх по каскаду.

Диаг: `wiki_topic_stems`, `wiki_topic_kind`, `wiki_topic_score`,
`wiki_topic_reject`, `wiki_topic_repick`, `wiki_topic_clarify`, `wiki_nef_hit`.

Словарь словоформ — одна строка + `.split()` (не list/tuple-литерал маршрутизации).
Имён конкретных сущностей/баз в правиле нет.

---

## Что где (файл:строки)

| место | строки | роль |
|---|---|---|
| `ubuntu/serenedb/wiki_passport.sql` | 15–16 | `aliases`, `best_used_for` в паспортный SELECT |
| `ask/z21_wiki_choice.py` `wiki_passport_enrich` | 654–684 | кладёт aliases/best_used_for на карточку |
| `wiki_verify_candidates` | 973 | `resolved["passports"] = full` для гейта |
| `try_wiki_hybrid_entity_pick` | 1183–1209 | post_verify → topic_gate → repick/меню/none |
| `_TOPIC_DOMAIN_ROOTS` / stop | 1284–1295 | общий словарь словоформ + стоп |
| `_wiki_topic_required_terms` | 1358–1369 | domain-first / content |
| `wiki_passport_topic_confirm` | 1481–1512 | Б4 + nef |
| `wiki_leader_topic_gate` | 1515–1574 | утверждение / пересчёт |
| `_wiki_topic_clarify_menu` | 1577–1597 | меню при ≥2 выживших |
| `wiki_leader_post_verify` | 1600+ | без изменения семантики; порядок до гейта |
| `test_wiki_topic_gate.py` | новый | оффлайн Б4/G3/пересчёт |
| `test_one_path.py` | проверка «ж» | символ + вызов в hybrid после post_verify |

Промты (`WIKI_VERIFY_SYS`) не трогались.

---

## Замки

| замок | итог |
|---|---|
| `test_wiki_topic_gate.py` | **26/0** |
| `test_one_path.py` (вкл. «ж») | **81/0** |
| `test_wiki_homonym_menu.py` | **10/0** |
| `test_zone_names_resolvable.py` | **96/0** |
| `test_wiki_captions_builder.py` | **24/0** |
| `test_k4_meta_names.py` | **13/0** |
| `test_wiki_leader_not_overridden.py` | **9/0** |
| `test_wiki_card_hybrid.py` | **67/0** |
| `test_measure_menu_not_silent.py` | **12/0** |
| `test_compose.py` | **91/0** |
| `test_gate.py` | **56/0** |
| `test_intent.py` | **162/0** |
| `test_period_empty.py` | **30/0** |
| `test_wiki_candidate_verify.py` | **64/0** (после fail-open на stub `"q"`) |
| `test_no_domain_wordlists.py` | **ok** (новых 0) |

`py_compile` ask/z21 + замки — OK. `load_all` — `wiki_leader_topic_gate` виден.

### Grep-негатив

В теле правила (от `def wiki_leader_topic_gate`) нет
`accumulationregister_реализац*` / `catalog_номенклат*` / привязок к okna.
Общий словарь словоформ (`склад`/`прайс`/…) — допустим по H1.

### Окруженческое

Интеграционные моки `test_wiki_candidate_verify` с вопросом `"q"` (нет
substantive-термов) проходят через G2 fail-open `no_topic_stems`; это не
обход Б4 на размытых учётных вопросах («сколько всего записей?» →
`empty_topic`).

---

## Вне скоупа H1 (оркестратор)

- L67 / i2 на окне (склад → не число по продажам; прайс → 2389 или меню с
  ценовым носителем).
- Выкат `/opt`, flip, git commit/push.
- Опциональное описательное усиление `WIKI_VERIFY_SYS` (вариант (в) — не правило).

---

## Критерий приёмки красной (из G2/G3) — статус кода

| | код |
|---|---|
| Оба wrong ловятся общим механизмом | да (замки G3-кейсы) |
| 0 cut match на калибровочных соседях | да (валюты/организации/поставщики) |
| Нет литералов имён сущностей в правиле | да |
| Пересчёт, не голый demote | да (repick/clarify/none) |
