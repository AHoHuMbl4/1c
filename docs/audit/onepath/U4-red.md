# U4: красная атака фикса утечки YAML-паспорта (дифф F1)

Срез: 12.09.2026. Код не менялся. Read-only: дифф F1 + `z21_wiki_choice.py` +
замки + локальные вызовы санитайзера (`python3` / stub-load как в
`test_wiki_captions_builder`). Полигон/psql/git не трогались. Опора на проект:
`docs/audit/onepath/U3-leak.md`.

---

## Вердикт (сразу)

**Живой путь полигона (сырой `wiki_body` → `label`/`wiki_caption`) закрыт и
замками подтверждён (22/0, 15/0).** Em-dash, CRLF, забор без закрытия, kind-хвост
при `name ⊆ existing` — держатся.

**Контракт санитайзера как «общее правило на любой label/hint» — дыряв.** Два
обхода с фактическим вызовом возвращают паспортные маркеры на экран; замки их
не ловят. `format_clarify_options` / числовой `gate` / `prompt_leak` pageType не
режут.

**К выкату:** можно как hotfix ровно той утечки, что ломала 5 вопросов
полигона; **не** как «санитайзер закрыт». Перед выкатом или сразу следом —
п. «Доделать» (минимум №1–2).

---

## 1. Обходы санитайзера

Функции: `wiki_strip_passport_yaml` / `wiki_caption_leaks` /
`wiki_human_menu_caption` / `wiki_human_menu_hint` /
`wiki_menu_captions` — `z21_wiki_choice.py:393–502`.

| # | Атака | Факт вызова | Вердикт |
|---|---|---|---|
| 1 | Паспорт **без** открывающего `---` | `strip` оставляет ключи; `cap("Foo", body)` → `"Foo"` (name спасает) | **держат**, если name человеческий |
| 2 | Забор **без** закрытия | `strip` → `""`; caption → name | **держат** |
| 3 | YAML **в середине** body | `strip` → префикс до забора; при пустом name/H1 — existing, если чист | **держат** на штатном пути; см. смысл §2 |
| 4 | `\r\n` | нормализуется; caption `"Реализация ТМЦ"` | **держат** |
| 5 | Пустой name + пустой H1 | → existing если чист; иначе `""` | см. **обход B** |
| 6 | Existing label **с паспортом** | `wiki_caption_leaks` отбрасывает; при name — name | **держат**, если name чист; иначе A/B |
| 7 | Em-dash «—» / `pre---post` | «—» не забор; `---` внутри слова не `^---\s*$` | **держат** (не ложное срабатывание) |
| 8 | Name = паспортный мусор | см. **обход A** | **ОБХОД** |

### Обход A — фоллбек после `leaks` снова кладёт грязный `name`

```451:452:ubuntu/serenedb/ask/z21_wiki_choice.py
    if wiki_caption_leaks(out):
        out = name or h1 or "вариант"
```

Порядок `name or h1` **повторяет** уже отвергнутый `base = name or h1`.
Чистый H1 после YAML игнорируется, если `name` сам паспортный:

```text
cap("pageType: entity", "---\npageType: entity\n---\n\n# Склад товаров\n")
→ 'pageType: entity'   # wiki_caption_leaks=True
```

То же: `canonicalId: x`, `id: entity.foo`, `aliases: foo`, одиночный `---`.

На штатных данных `name` = label таблицы (человеческий) — обход маловероятен,
но код **гарантирует утечку**, если name когда-либо = ключ паспорта.

### Обход B — пустой результат санитайзера **не затирает** грязный prev

```495:498:ubuntu/serenedb/ask/z21_wiki_choice.py
        text = wiki_human_menu_caption(name, body, existing_label=prev)
        if text:
            row["label"] = text
            row["wiki_caption"] = text
```

Комментарий («даже без паспорта — прогнать уже лежащий label») врёт факту:
когда caption честно возвращает `""` (грязный existing, пустые name/H1),
`if text:` пропускает запись → **прежний паспортный label остаётся**.

```text
menu([{"src":"x","label":"pageType: entity\ncanonicalId: x"}])
→ label всё ещё 'pageType: entity\ncanonicalId: x'

menu([{"src":"catalog_x","label":"---\npageType: entity\n…"}],
     passports_by_src={… name:"", body без H1 …})
→ label не заменён, leaks=True
```

### Мелкие дыры forbid-листа (`_CAPTION_FORBIDDEN`, :387–390)

| вход | `wiki_caption_leaks` | заметка |
|---|---|---|
| `title: Реализация` | False | ключа `title:` нет в списке |
| `pageType : entity` (пробел до `:`) | False | матч только `pagetype:` |
| `id: other` (без `entity.`) | False | ловится лишь `id: entity.` / `\nid:` |
| leading blank + `---` | strip берёт префикс до забора (=пусто) | existing fallback ок, если чист |

На живом `wiki_build` frontmatter всегда с `---` с строки 0 и человеческим
`title`/`name` — эти дыры **не** объясняют полигонные 5 утечек; это ослабление
контракта «любой мусор → не на экран».

### Hint

UUID вырезается (`"см. ещё"`); `pageType:` / backticks+src → `""`. Держит.
Остаток слова `uuid` после вырезания UUID — косметика, не паспорт.

---

## 2. Потеря смысла

| Вопрос | Факт |
|---|---|
| Все варианты одним именем без различителя? | При **одинаковом** passport `name` и existing вида `Name (документ)` / `Name (регистр…)` — kind **сохраняется** (`base.lower() in existing.lower()`). Замер: labels `['Реализация ТМЦ (регистр накопления)', 'Реализация ТМЦ (документ)', 'other']`. Если existing **не** содержит name (чужая подпись) — оба схлопываются в одно name → различитель теряется. |
| N→N и порядок? | Да: цикл `for opt in list(options)` без filter/sort (`:479–501`). Замок `N→N` / порядок зелёный. |
| Kind-хвост mk_opts? | Да **только если** existing чист и содержит name (`:446–448`). Иначе — чистое name/H1. |
| Prose body в меню? | Убран намеренно (U3): «карточки контрагентов…» → теперь `Справочник Альфа`. Смысл для человека: короче, без boilerplate; различители — kind, не prose. |
| Mid-YAML + пустой name | Existing чистый → сохраняется (`Alpha`/`Beta`). Пустой existing → пустой text → label не обновляется / пункт может выпасть в `format_clarify_options` (`if not label: continue`, z20:323–324) — риск **тихого N−1**, не утечки. |

---

## 3. Второй фронт (другие пути сырого паспорта)

| Путь | YAML на экран клиенту? | Разбор |
|---|---|---|
| Entity-меню (z21:1045, z13:798/848, legacy z20) | **нет** после F1 | все сходятся в `wiki_menu_captions` |
| `hint` / `opts_hints` ← `best_used_for` (z20:1005–1008) | после captions — `wiki_human_menu_hint` | UUID/ключи режутся; U3: UUID в alias сейчас 0 |
| `distinct_by` | не в строке меню | `clarify_choice_line` печатает только label+hint (z20:299–306) |
| `measure_captions` (z14:86) | нет YAML | alias / `split_ident` поля |
| `render_window_label` (z03:352) | нет | даты + form id |
| `_passport_axis_label` (z18:477) | нет YAML | `_table_label(target_src)` — человеческая метка таблицы |
| Coverage census (z20:793–795) | **не YAML**, но **meta `entity`=src_table** уходит в модель | модель может назвать `accumulationregister_…` клиенту; `gate`/`prompt_leak` ловят числа и куски OUR_PROMPTS, не pageType/src_table |
| Compose ROWS/GROUPS (z18:633+) | wiki-passport **не** кладётся | строки корпуса + агрегаты; `build_answer_passport` — ISO/метки, не wiki YAML |
| `wiki_format_passport_lines` (z21:619–645) | **сырой `wiki_body`[:400] в VERIFY/LLM** | не экран меню; модель видит YAML. В клиентский clarify после F1 не течёт. Пересказ паспорта в answer-тракте маловероятен (compose без wiki); отдельного гейта на `pageType` нет |
| `format_clarify_options` (z20:309–327) | вторичная защита **слепа** к pageType/`---` | только `label_has_meta_src` (OData-префиксы / `тип_хвост`) |

Итог второго фронта: **меню-утечка YAML закрыта в одной точке**; остаётся (а) verify→модель с сырым wiki, (б) coverage meta-имена, (в) отсутствие экранного гейта на паспортные ключи вне captions.

---

## 4. Замки — ловят ли регресс?

Прогон: `test_wiki_captions_builder.py` → **PASS 22 FAIL 0**;
`test_k4_meta_names.py` → **15 ok, 0 FAIL**.

**Что ловят (мысленно сломать санитайзер → краснеет):**

- вернуть склейку `name — body[:200]` / сырой body → краснеют
  `U3 YAML → нет pageType` / `нет забора ---` / `label == name`;
- card-ветка с description=YAML → `U3 card YAML`;
- hint `pageType:` → `U3 hint pageType → пусто`;
- k4 `screen_leaks` + прогон через `wiki_menu_captions` →
  `U3 wiki_menu_captions: экран без паспорта`.

**Что не ловят (слабые места):**

1. Обход A (грязный name + чистый H1) — нет кейса.
2. Обход B (`if text:` сохраняет грязный prev) — нет кейса.
3. `title:` / `pageType :` с пробелом / `id:` без `entity.` — нет.
4. k4 проверяет один «счастливый» passport+name; не assert’ит
   `not wiki_caption_leaks(label)` на произвольном existing.
5. Нет негатива «санитайзер обязан заменить label даже на `вариант`».

Вывод: замки **хорошо держат регресс ровно F1-бага полигона**; как контракт
«паспортные маркеры никогда не в label» — **слабые**.

---

## 5. Доделать (файл:строка)

1. **`z21_wiki_choice.py:451–452`** — при `wiki_caption_leaks(out)` не
   возвращать сырой `name`, если он сам течёт: сначала отбросить name/h1
   через `wiki_caption_leaks`, иначе `"вариант"`.
2. **`z21_wiki_choice.py:496–498`** — всегда писать санитизированный label
   (пустой → `"вариант"` или очищенный existing), не оставлять prev при
   `text == ""`.
3. **Замки** — негативы на A и B в `test_wiki_captions_builder.py`; в k4 —
   assert `screen_leaks` на options с грязным prev без name.
4. **Опционально (не блокер F1):** расширить `_CAPTION_FORBIDDEN` (`title:`,
   нормализация пробелов у ключей); вторичный фильтр pageType в
   `format_clarify_options` / экранном гейте; coverage — не отдавать сырой
   `entity` src_table в census без human label (отдельный эпизод).
5. **Не в этом фиксе:** чистить `wiki_pages.body` / card.description в SQL
   (emb-риск, U3 §7).

---

## 6. Итог одной строкой

F1 закрывает живую утечку меню и зелёный на замках/полигоне; красная атака
находит **два логических обхода** (грязный name в фоллбеке; пустой sanitize
не затирает prev) и слепой второй контур (`format_clarify` / coverage meta).
**Выкат hotfix — да; «санитайзер готов» — нет, пока №1–2 не закрыты.**
