# F1: фикс утечки wiki-паспорта (исполнение U3)

Срез: 12.09.2026. Источник: `docs/audit/onepath/U3-leak.md`.  
Код зон кроме z21 не тронут. git / psql / полигон / прод — не трогались.

---

## 1. Дифф-выжимка `ubuntu/serenedb/ask/z21_wiki_choice.py`

### 1.1 Вставлено перед `wiki_menu_captions` (строки **379–466**)

По эскизу U3 §3.2:

| символ | строки | роль |
|---|---|---|
| `import re` | 379 | regex для забора/UUID |
| `_YAML_FENCE` | 382 | `(?m)^---\s*$` (ASCII; em-dash «—» не режет) |
| `_UUID_RE` | 383–385 | UUID в hint |
| `_CAPTION_FORBIDDEN` | 386–390 | `pagetype:` / `entitytype:` / `canonicalid:` / `id: entity.` / … |
| `wiki_strip_passport_yaml` | 393–411 | снять YAML-frontmatter |
| `wiki_caption_leaks` | 414–425 | детект паспортных ключей / забора / `` `src` `` |
| `wiki_human_menu_caption` | 428–453 | name → H1 → чистый `existing_label` |
| `wiki_human_menu_hint` | 456–465 | UUID off + forbid-list → пусто |

### 1.2 Заменено внутри `wiki_menu_captions` (строки **468–502**)

По эскизу U3 §3.3:

- убрана склейка `"%s — %s" % (name, body[:200])` и ветка `name in body`;
- подпись: `wiki_human_menu_caption(name, body, existing_label=prev)`;
- при наличии ключа `hint`: `wiki_human_menu_hint(row.get("hint"))`;
- зовы снаружи (`z21` clarify, `z13`, legacy `z20`) **не менялись**.

### 1.3 Отклонение от эскиза (вопрос)

**Docstring `wiki_human_menu_caption`:** в U3 §3.2 было
«Никогда pageType/id/…». Хук `check-prompt-rules` **deny** на эту фразу
(императив в docstring). Исполняемый код — дословно U3; в docstring вместо
императива: «Паспортные ключи отсекает `wiki_caption_leaks`» (правило
держится кодом санитайзера, не промтом).

**Вопрос оркестратору/владельцу:** вернуть дословный docstring U3 через люк
`check-prompt-rules`, или оставить формулировку без императива?

Остальных отклонений нет.

---

## 2. Замки

### 2.1 `test_wiki_captions_builder.py` (U3 §4.1)

- кейс «карточки контрагентов» → ожидает **name** (`Справочник Альфа`);
- негативы: passport YAML → чистый label; card YAML; em-dash «—»; H1 после
  frontmatter; hint UUID без UUID; hint `pageType:` → пусто;
- в оффлайн-loader добавлен stub `looks_like_src_table` (нужен
  `wiki_caption_leaks` при backticks; в рантайме символ из z20 через wire).

### 2.2 `test_k4_meta_names.py` (U3 §4.2)

- `screen_leaks`: маркеры `pagetype:`, `entitytype:`, `canonicalid:`,
  `id: entity.`, строка-забор `---`; также смотрит `wiki_caption`;
- кейс сырого паспорта через `wiki_menu_captions` → `screen_leaks=False`,
  `src` внутри option допустим; старые OData-кейсы целы.

---

## 3. Прогоны

| прогон | результат |
|---|---|
| `python3 -m py_compile …/z21_wiki_choice.py` | **0** |
| `timeout 120 python3 test_wiki_captions_builder.py` | **22/0** EXIT=0 |
| `timeout 120 python3 test_k4_meta_names.py` | **15/0** EXIT=0 |
| `test_one_path.py` | **41/0** EXIT=0 |
| `test_no_pre_wiki_reorders.py` | **39/0** EXIT=0 |
| `test_measure_hatch_luk.py` | **15/0** EXIT=0 |
| `test_measure_menu_not_silent.py` | **14/0** EXIT=0 |
| `test_zone_names_resolvable.py` | **109/0** EXIT=0 |

Живые 5 вопросов полигона — **не** в этой задаче (оркестратор).

---

## 4. Итог

U3 исполнен: санитар в одном месте (`wiki_menu_captions`), замки расширены,
регресс зелёный. Единственный вопрос — формулировка docstring vs
`check-prompt-rules` (§1.3).
