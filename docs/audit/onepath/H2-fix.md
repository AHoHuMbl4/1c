# H2 — доработка тема-гейта по красной паре (HR1+HR2)

Дата: 12.09.2026. Режим: код + замки; **git / psql / прод не трогались**.

Опора: `docs/audit/onepath/{HR1-red,HR2-red,G3-Калибровка,H1-impl}.md`,
`ask/z21_wiki_choice.py`, `test_wiki_topic_gate.py`.

---

## Вердикт

Все пять дыр красных закрыты кодом. Новых выбирателей нет. Имён конкретных
сущностей/баз в правиле нет. Замки зелёные (ниже).

---

## 1. Строгий domain-confirm (главная, обе красные)

**Было:** `_wiki_topic_positive_bag` брал `best_used_for` и `wiki_body` —
случайное «…со склада…» у документа Реализации давало `topic_ok:domain`.

**Стало:** мешок только `name|label`, `aliases`, имена осей (левая часть до
`→`), labels мер (до `:`). `wiki_body` / `best_used_for` / сырые колонки мер /
цели FK — вне подтверждения.

| место | строки |
|---|---|
| `_wiki_topic_positive_bag` | `z21_wiki_choice.py:1455–1470` |

Замок: `best_used_for`/`wiki_body` с «склад» → REJECT; alias «прайс» → OK.

---

## 2. Verify-меню через topic-гейт (HR1 №1)

**Было:** `outcome=clarify` → сразу `readings_menu(reason=wiki_separability)`
без фильтра темы → «Реализация» в меню на «склад».

**Стало:** кандидаты через `_wiki_topic_filter_passports` (тот же
`wiki_passport_topic_confirm`):

- ≥2 выживших → меню (как раньше);
- 1 → лидер по обычному пути (`post_verify` + gate);
- 0 → пересчёт `wiki_leader_topic_gate` по полному пулу / none.

| место | строки |
|---|---|
| `try_wiki_hybrid_entity_pick` clarify-ветка | `1165–1205` |
| `_wiki_topic_filter_passports` | `1649–1658` |

---

## 3. Compare-маркеры не content-термы (HR1 №3)

**Было:** content-AND резал «сравни продажи этого и прошлого…» на служебных
токенах.

**Стало:** `_wiki_topic_is_compare_service_token` опирается на детекторы z05
(`_yoy_compare_marker`, `sales_compare_intent`) и те же pair-mark фразы;
токены сравни*/против/versus/этого/прошл*/период в compare-форме не входят
в required.

| место | строки |
|---|---|
| `_wiki_topic_compare_shaped` | `1335–1356` |
| `_wiki_topic_is_compare_service_token` | `1359–1392` |
| `_wiki_topic_is_stop` / `_wiki_topic_content_terms` | `1395–1422` |

Замок: required без `сравни`/`этого`/`прошлого`; alias «продажи» → OK.

---

## 4. Homonym после topic_repick (HR1 №4)

**Было:** после repick сразу leader без повторного
`wiki_homonym_kind_peers`.

**Стало:** хвост `_wiki_apply_topic_gate_result`: при `new_leader != leader`
снова peers → clarify-меню (`wiki_topic`), иначе leader.

| место | строки |
|---|---|
| `_wiki_apply_topic_gate_result` | `1661–1696` |
| вызов из hybrid (leader + clarify→0) | `1203–1215` |

---

## 5. G3-калибровка

После фикса:

| кейс | итог |
|---|---|
| match named/label/валюты/организации/поставщики | OK (замок) |
| wrong склад → продажи | REJECT |
| wrong прайс → номенклатура | REJECT + repick на aliases «прайс» |
| «операций в системе» | REJECT |
| FK оси не подтверждает «склад» | REJECT |
| прайс: `Цены…` с alias «прайс» → лидер | OK (`topic_ok` / repick) |

SELECT живого паспорта «Цены Номенклатуры» в этой сессии не снимался
(git/psql запрещены заданием); опора — G1/G3 факты + оффлайн-фикстура
aliases=`прайс-лист, прайс`.

---

## Замки

| замок | итог |
|---|---|
| `test_wiki_topic_gate.py` | **38/0** (+12 H2) |
| `test_one_path.py` (вкл. «ж») | **81/0** |
| `test_wiki_homonym_menu.py` | **10/0** |
| тракт E2-final (+ period_empty, no_domain, verify, captions, gate, compose, intent, hybrid, …) | **зелёные** |
| `py_compile` z21 + замок | OK |
| `load_all` (`wiki_leader_topic_gate`, filter, apply) | OK |
| grep: имена сущностей в правиле | NONE |

`test_one_path` «ж»: инвариант порядка уточнён под H2 — на хвосте лидера
`max(topic_gate) ≥ min(post_verify)`; clarify→0 может звать gate раньше.

---

## Вне скоупа

Git commit/push, выкат `/opt`, L67/curl :8092 — оркестратор / владелец.
