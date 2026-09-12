# U3: утечка wiki-паспорта в подписи меню — ПРОЕКТ ФИКСА

Срез: 12.09.2026. Код не менялся. Чтение: `ubuntu/serenedb/ask/z21_wiki_choice.py`,
замки, SELECT на окне gpu-erw:7890.

---

## 1. Вердикт

Утечка **не в тракте «один путь»** и не в данных «случайно»: это штатная форма
`wiki_pages.body` (YAML-frontmatter) + построитель `wiki_menu_captions`, который
кладёт сырой `wiki_body`/`description` в `label`/`wiki_caption`.

**Одно место правки:** `ubuntu/serenedb/ask/z21_wiki_choice.py` функция
`wiki_menu_captions` (**:379–419**) + рядом единая санитарная функция (вызвать
только оттуда). Зовы снаружи (`z21:962`, `z13:798/848`, legacy `z20:3109/3137`)
**не трогать** — они уже сходятся в этот форматтер.

---

## 2. Корневая цепочка (замер + код)

### 2.1 Как лежит паспорт в базе (SELECT, окно)

`wiki_build.sql:48–76` собирает `wiki_pages.body` так:

```
---
pageType: entity
entityType: …
id: entity.<src_table>
canonicalId: <src_table>
title: <label>
…
---

# <label>
Record type in this 1C database. Platform entity set: `<src_table>`.
…
```

Живой SELECT (`accumulationregister_реализациятмц` / `document_реализациятмц`):

| факт | значение |
|---|---|
| страниц `wiki_pages` | 255 |
| начинают с `---\n` | **255/255** |
| содержат `pageType:` | **255/255** |
| `search_wiki_entity_card.description` | = тот же `w.body` (`wiki_card_build.sql:42`) |
| human после закрывающего `\n---\n` | `# Реализация ТМЦ` + англ. boilerplate с `` `src_table` `` |
| UUID в `search_entity_alias.best_used_for` | **0** сейчас (правило hint всё равно нужно) |

### 2.2 Где утекает на экран

```379:419:ubuntu/serenedb/ask/z21_wiki_choice.py
def wiki_menu_captions(options, passports_by_src=None, cards_by_src=None):
    ...
            body = (p.get("wiki_body") or p.get("description") or "").strip()
            if body:
                body = body[:200]
            if name and body and name not in body:
                text = "%s — %s" % (name, body)
            else:
                text = body or name
        ...
        if text:
            row["label"] = text
            row["wiki_caption"] = text
```

Оба ветвления дефектны на живых данных:

1. **`name in body[:200]`** (часто: `title: Реализация ТМЦ` попадает в 200) →
   `text = body` → подпись = сырой YAML начиная с `---`.
2. **`name not in body[:200]`** (обрезка до `title`) →
   `text = "Реализация ТМЦ — ---\npageType:…"` — ровно формат из полигона.

Дальше `clarify_say` / `clarify_choice_line` (`z20_ask_main_http.py:300–306`)
печатает `N. вопрос: <label> — <hint>` → утечка в `text` ответа.

`format_clarify_options` ловит только OData-префиксы/`src_table`-токены
(`label_has_meta_src`) — ключи `pageType`/`canonicalId` **не режет**.

### 2.3 Почему «легаси тоже»

Те же зовы `wiki_menu_captions` в legacy z20 и z13. Баг данных+форматтера,
не регрессия B5c.

---

## 3. Эскиз: одна санитарная функция + вызов

### 3.1 Куда вставить

Файл: `ubuntu/serenedb/ask/z21_wiki_choice.py`  
**Перед** `wiki_menu_captions` (сейчас :379), правка тела :396–418.

### 3.2 Эскиз

```python
import re

# YAML-забор: три ASCII-дефиса. Unicode em-dash «—» (U+2014) НЕ разделитель.
_YAML_FENCE = re.compile(r"(?m)^---\s*$")
_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_CAPTION_FORBIDDEN = (
    "pagetype:", "entitytype:", "canonicalid:",
    "\nid:", "id: entity.", "aliases:", "bestusedfor:", "notenoughfor:",
    "relationships:", "targetid:",
)

def wiki_strip_passport_yaml(text):
    """Тело wiki_pages / card.description → без YAML-frontmatter.

    Если текст начинается с забора --- … ---, берём хвост после закрывающего.
    Если забор встречается позже — берём префикс до первого забора
    (на случай «заголовок\\n---\\nmeta»). Em-dash «—» не режем.
    """
    t = (text or "").replace("\r\n", "\n")
    if not t.strip():
        return ""
    lines = t.split("\n")
    fence_idx = [i for i, ln in enumerate(lines) if _YAML_FENCE.match(ln)]
    if not fence_idx:
        return t.strip()
    if fence_idx[0] == 0 and len(fence_idx) >= 2:
        return "\n".join(lines[fence_idx[1] + 1:]).strip()
    if fence_idx[0] == 0:
        return ""  # только frontmatter, закрывающего нет
    return "\n".join(lines[:fence_idx[0]]).strip()

def wiki_caption_leaks(text):
    """True, если строка несёт паспортные ключи / YAML-забор / сырой src в backticks."""
    s = (text or "")
    if "---" in s and _YAML_FENCE.search(s):
        return True
    low = s.lower()
    if any(m in low for m in _CAPTION_FORBIDDEN):
        return True
    if "`" in s and looks_like_src_table(
            s.split("`")[1].strip() if s.count("`") >= 2 else ""):
        return True
    return False

def wiki_human_menu_caption(name, body, existing_label=""):
    """Единая санитарная подпись для ЛЮБОГО пункта меню из wiki-паспорта.

    Порядок: (1) name; (2) H1 после снятия YAML; (3) уже человеческий
    existing_label от mk_opts (с kind-различителем). Никогда pageType/id/…
    """
    name = (name or "").strip()
    existing = (existing_label or "").strip()
    human = wiki_strip_passport_yaml(body or "")
    h1 = ""
    for ln in human.splitlines():
        ln = ln.strip()
        if ln.startswith("#"):
            h1 = ln.lstrip("#").strip()
            break
    base = name or h1
    # сохранить «Реализация ТМЦ (регистр…)» от disambiguate_labels, если чисто
    if (existing and not wiki_caption_leaks(existing)
            and base and base.lower() in existing.lower()):
        out = existing
    else:
        out = base or (existing if not wiki_caption_leaks(existing) else "")
    if wiki_caption_leaks(out):
        out = name or h1 or "вариант"
    return out.strip()

def wiki_human_menu_hint(hint):
    """Hint без UUID и без паспортных ключей. Пусто — допустимо."""
    h = (hint or "").strip()
    if not h:
        return ""
    h = _UUID_RE.sub("", h)
    h = re.sub(r"\s{2,}", " ", h).strip(" ;,")
    if wiki_caption_leaks(h):
        return ""
    return h
```

### 3.3 Где вызвать (внутри `wiki_menu_captions`, единственная точка)

Заменить сборку `text` на:

```python
        name = ""
        body = ""
        p = passports_by_src.get(src) if src else None
        if isinstance(p, dict):
            name = (p.get("name") or "").strip()
            body = (p.get("wiki_body") or p.get("description") or "")
        else:
            c = cards_by_src.get(src) if src else None
            if isinstance(c, dict):
                name = (c.get("name") or "").strip()
                body = (c.get("description") or "")
        # даже без паспорта — прогнать уже лежащий label/hint (общее правило)
        prev = (row.get("label") or "").strip()
        text = wiki_human_menu_caption(name, body, existing_label=prev)
        if text:
            row["label"] = text
            row["wiki_caption"] = text
        if "hint" in row:
            row["hint"] = wiki_human_menu_hint(row.get("hint"))
```

**Не** склеивать `name — body[:200]`: после снятия YAML хвост всё ещё содержит
английский boilerplate с `` `accumulationregister_…` `` — это снова утечка
метаимени. Для меню достаточно человекочитаемого **имени** (и kind от mk_opts).

### 3.4 «Все меню» (сущность/мера/окно/ось)

| вид меню | источник подписи сейчас | риск YAML | правило U3 |
|---|---|---|---|
| сущность (wiki-clarify, fork C) | `wiki_menu_captions` | **да, живой** | фикс здесь |
| мера | `measure_captions` (z14) | нет (alias/поле) | при унификации `readings_menu` — тот же `wiki_human_menu_hint` / forbid-list на label; сейчас YAML не течёт |
| окно | `render_window_label` (z03) | нет (даты/id формы) | то же |
| ось | `_passport_axis_label` / fork human | target_src→label таблицы | forbid-list при общем построителе |

Контракт этапа: **одна санитарная функция**; зов сегодня — только из
`wiki_menu_captions` (все entity-меню уже через неё). Мера/окно/ось YAML не
несут; когда stage-2 соберёт `readings_menu`, тот же helper станет общим
post-filter без второй копии логики.

---

## 4. Замки обновить

### 4.1 `ubuntu/serenedb/test_wiki_captions_builder.py` (ядро)

Добавить негативы (оффлайн, без БД):

1. **passport YAML → label чист:** `wiki_body` = живой head (`---\npageType…`) →
   `label == "Реализация ТМЦ"`, в label/`wiki_caption` нет
   `pageType` / `entityType` / `canonicalId` / `id: entity.` / забора `---`.
2. **card.description = body:** тот же запрет на ветке `cards_by_src`.
3. **N→N / порядок** — оставить как есть.
4. **Em-dash «—» в легитимной подписи:** `name="А — Б"`, body без YAML →
   label сохраняет «—» (не режется как YAML).
5. **H1 после frontmatter:** body =
   `---\npageType: entity\n---\n\n# Склад товаров\n\nRecord type…` →
   label ∈ {`Склад товаров`, name}, без backticks/`src_table`.
6. **hint:** `hint` с UUID → пусто или без UUID; hint с `pageType:` → пусто.

Существующий кейс `wiki_body: "карточки контрагентов…"` (без YAML) — оставить
зелёным: либо label содержит эту фразу **только если** решим допускать
короткий human-body; при строгом «только name/H1» — поправить ожидание замка
на `name` (`Справочник Альфа`). **Рекомендация проекта:** для меню — name/H1;
короткий prose body не дописывать (иначе снова риск boilerplate). Тогда кейс
«карточки контрагентов» → ожидать name.

### 4.2 `ubuntu/serenedb/test_k4_meta_names.py`

1. Расширить `screen_leaks` маркерами:
   `pagetype:`, `entitytype:`, `canonicalid:`, `id: entity.`, строка-забор `---`.
2. Новый кейс: прогнать options через `wiki_menu_captions` с сырым passport →
   `screen_leaks` = False; `src` внутри option по-прежнему допустим.
3. Старые OData-кейсы не ломать.

### 4.3 Не обязательны, но полезны

- Смоук в `test_wiki_candidate_verify.py` (уже знает `wiki_menu_captions`):
  одна строка «caption без pageType».
- При stage-2 `test_one_path`: assert на clarify options.

---

## 5. Риски

| риск | разбор | митигация |
|---|---|---|
| Срезать легитимные длинные подписи с «—» | Em-dash U+2014 ≠ ASCII `---` | Резать **только** строку-забор `^---\s*$`, не `—` и не одиночный `-` |
| Склеивание `name — body` | Исторический ` — ` в форматтере — не YAML; путать нельзя | После фикса склейку с сырым body убрать; «—» в тексте name оставлять |
| Потеря kind-различителя | mk_opts уже пишет «X (регистр…)»; captions затирает | `existing_label`, если чист и содержит name — сохранить |
| Англ. хвост после YAML | `` Platform entity set: `src` `` | Не брать prose body в label; только name/H1 |
| Hint UUID | Сейчас 0 в alias, но контракт | `wiki_human_menu_hint` |
| Чинить `wiki_pages` / card.description | Меняет векторный `card_text` → сброс emb | **Не в U3.** Санитар на чтении в меню; пересборка вики — отдельный эпизод с 6a0 |
| Дублировать sanitize в z20/z13 | Нарушит «одно место» | Только внутри `wiki_menu_captions` |

---

## 6. Критерий проверки — те же 5 живых вопросов

Прогон на окне (ask :8092), вопросы из `/tmp/i2-onepath-b5c`:

1. вчера сколько продали  
2. позавчера продаж  
3. прошлый месяц *(как в прогоне)*  
4. этот месяц вышло  
5. записей в реализациятмц  

**PASS для каждого ответа с `kind=clarify` (и для answer, если в text есть меню):**

- в `text`, `options[].label`, `options[].wiki_caption`, `options[].hint`
  **нет** подстрок: `pageType`, `entityType`, `canonicalId`, `id: entity.`,
  строки `---`, UUID-шаблона;
- `label` — человекочитаемое имя (напр. «Реализация ТМЦ» / с kind-хвостом),
  без YAML;
- `options[].src` может оставаться служебным (внутреннее) — **не** дефект;
- число вариантов N и порядок не меняются относительно до-фикса (N→N);
- контрольные зелёные (склад/контрагенты/продажи за месяц) не краснеют.

**Доказательство:** JSON ответа + grep запрещённых маркеров по 5 файлам;
опционально diff label до/после на одном вопросе.

---

## 7. Граница работ (что не входит)

- Не менять `wiki_build.sql` / `wiki_card_build.sql` в этом шаге (emb-риск).
- Не править `clarify_say` / `format_clarify_options` как основной фикс
  (вторичная защита возможна позже, не вместо sanitizer).
- Не трогать зовы в z13/z20/legacy — только построитель.
- Код в этой задаче U3 **не писать** — только проект; исполнение = отдельная
  волна с замками и живым прогоном.

---

## 8. Итог одной строкой

**Править `z21_wiki_choice.py:379–419`:** добавить `wiki_human_menu_caption` /
`wiki_strip_passport_yaml` / `wiki_human_menu_hint` и вызывать их внутри
`wiki_menu_captions`; обновить `test_wiki_captions_builder` + `test_k4_meta_names`;
приёмка — 5 вопросов полигона без `pageType`/`---` в подписях.
`)