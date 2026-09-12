# S2-b — Одноимённые прочтения → меню (проект правки z21)

Дата: 12.09.2026. Режим: **read-only** (код/история), один отчёт. Код не менялся.
Чужие `S2-*` не читались. Опора: `z21_wiki_choice.py`, `z20_ask_main_http.py`
(`mk_opts` / `disambiguate_labels` / `_KIND_WORD`), замки `test_wiki_candidate_verify.py`,
`test_verify_threshold_menu.py`; контекст лотереи — комментарий z20:849–854 и
W2-A2 §S25 (silent-ветка wiki-каскада).

---

## 1. Вердикт

Минимальная правка — **одна точка**: после того как `wiki_outcome_from_verify`
готов утвердить `outcome=leader` (ровно один `yes`, остальные `no`), добавить
кодовый запрет: если в том же списке паспортов verify есть **≥1 живой сосед** с
тем же человекочитаемым ключом имени и **другим** OData-видом платформы —
вернуть `clarify` с этими кандидатами, а не лидера.

Меню, подписи с «(документ)» / «(регистр накопления)» / «(справочник)» и путь
`mk_opts` → `wiki_menu_captions` **уже есть** — чинить надо только silent-лидера
при одноимённости, не строитель меню.

---

## 2. Где сейчас утверждается лидер

### 2.1 Правило verify (единственный «уверенный» лидер)

Файл: `ubuntu/serenedb/ask/z21_wiki_choice.py`

| Узел | Строки | Что делает |
|---|---:|---|
| `wiki_outcome_from_verify` | 819–868 | Код: `leader` / `clarify` / `none` по вердиктам |
| **Утверждение лидера** | **843–851** | `len(yes)==1` ∧ все остальные `no` ∧ нет `unsure` → `leader` |
| Tie → clarify | 855–868 | ≥2 неотвергнутых (`yes`/`unsure`) → уже меню-кандидат |
| `wiki_verify_candidates` | 871–905 | Паспорта → модель → зовёт `wiki_outcome_from_verify` |
| `try_wiki_hybrid_entity_pick` | 1066–1121 | Verify перекрывает pick; clarify → `mk_opts`; leader → `picked` |

Фрагмент условия лидера (канон В4 / 4-А):

```843:851:ubuntu/serenedb/ask/z21_wiki_choice.py
    if (len(yes_i) == 1
            and len(no_i) == len(passports) - 1
            and not unsure_i):
        leader = passports[yes_i[0] - 1].get("src_table")
        if not wiki_validate_leader_axes(leader, intent):
            diag["wiki_verify"] = "axis_reject"
            return {"outcome": "none", "reason": "axis_reject", "diag": diag}
        diag["wiki_verify"] = leader
        return {"outcome": "leader", "leader": leader, "diag": diag}
```

Именно здесь модель может сказать `yes` то документу, то регистру — оба живы в
пуле, человеческие имена совпадают → **лотерея** (числа 75 705 vs 79 705).

### 2.2 Путь меню при tie (уже правильный — не трогать)

```1097:1116:ubuntu/serenedb/ask/z21_wiki_choice.py
    if pick.get("outcome") == "clarify":
        tied = [c["src_table"] for c in (pick.get("candidates") or [])]
        ...
        opts = mk_opts(tied, lab_by, {}, by or {}, match=match or "", preds=preds or [])
        if len(opts) >= 2:
            _pmap = wiki_captions_map_from_cards(pick.get("candidates") or [])
            opts = wiki_menu_captions(opts, passports_by_src=_pmap)
            return {"partial": cut or None, "kind": "clarify", ...}
```

### 2.3 Различитель вида записи (уже готов — переиспользовать)

В `z20_ask_main_http.py`:

- `_KIND_WORD` / `kind_word` (860–923) — перевод OData-префикса:
  `document` → «документ», `accumulationregister` → «регистр накопления», …
- `label_with_kind` (926–937) — «Реализация ТМЦ (документ)»
- `disambiguate_labels` (968–985) — вид дописывается, когда метка совпала
  **внутри списка** или в `ambiguous_labels()` базы
- `mk_opts` (1059–1087) зовёт `disambiguate_labels` для всех веток clarify

Комментарий z20:849–854 уже фиксирует дефект одноимённых «Реализация ТМЦ»
(документ vs регистр) и запрет отдавать наружу сырой `src_table`.

---

## 3. Что считать «двумя живыми неразличимыми прочтениями»

Универсально (без имён конкретной базы):

### 3.1 Ключ человекочитаемого имени

Та же нормализация, что у `disambiguate_labels`:

```text
norm(s) = "".join(str(s).lower().split())
```

Источник имени паспорта (по приоритету):

1. `passport["name"]` из wiki-карточки / гибридного пула (уже в пуле);
2. если пусто — человеческий хвост после OData-префикса
   (`human_table_label(src)` / stem `src.split("_", 1)[1]` через тот же
   `human_table_label`) — это **платформенное** имя объекта метаданных, не
   доменный хардкод.

### 3.2 Вид платформы

Только OData-голова `src_table` (как `_card_odata_kind` в z21:191–194):

```text
kind(src) = src.split("_", 1)[0].lower()   # document | accumulationregister | …
```

Слова для человека — уже `kind_word` / `_KIND_WORD` (не выдумывать вторую таблицу).

### 3.3 «Близкие паспорта» (второй ключ, тоже без привязки к базе)

Если `name` у двух карточек чуть разъехались текстом, но это **один и тот же
объект метаданных под разными видами**, ловить по **stem** после префикса:

```text
stem(src) = norm(src.split("_", 1)[1])   # при наличии "_"
```

Два ключа группировки (OR внутри пары):

| Сигнал | Условие пары | Зачем |
|---|---|---|
| A. Имя | `norm(name_i) == norm(name_j)` и оба непусты | явное совпадение вики-имён |
| B. Stem | `stem(src_i) == stem(src_j)` и оба непусты | «близкие паспорта» / одноимённый объект метаданных |

И **обязательно**: `kind(src_i) != kind(src_j)`.

Одинаковый kind + одинаковое имя (два разных документа с одной подписью) —
**вне этого эпизода** (другой класс; при необходимости отдельный тикет). Здесь
цель владельца — document vs register (и аналоги разных родов платформы).

### 3.4 «Живые»

Члены **того же списка `passports`**, который уже ушёл в verify
(`wiki_passport_enrich` top-`WIKI_PASSPORT_N`). Не «все таблицы базы», не
short-tail «Other pool names only».

Вердикт модели (`yes`/`no`) **не вычёркивает** соседа из группы: при
лотерее как раз один получает `yes`, другой `no`. Если смотреть только на
`yes`/`unsure`, баг останется.

### 3.5 Предикат одной функцией (эскиз)

Новая чистая функция рядом с `wiki_outcome_from_verify`
(например `wiki_homonym_kind_peers(passports, focus_src)`):

```python
def wiki_homonym_kind_peers(passports, focus_src):
    """Соседи focus с тем же name/stem и другим OData-kind. ≥2 → конфликт."""
    pool = [p for p in (passports or []) if p and p.get("src_table")]
    focus = next((p for p in pool if p["src_table"] == focus_src), None)
    if not focus or len(pool) < 2:
        return []
    fk = _homonym_keys(focus)          # frozenset name_key and/or stem_key
    fkind = _card_odata_kind(focus)
    peers = [focus]
    for p in pool:
        if p["src_table"] == focus_src:
            continue
        if _card_odata_kind(p) == fkind:
            continue
        if fk & _homonym_keys(p):      # пересечение ключей имени/stem
            peers.append(p)
    return peers if len(peers) >= 2 else []
```

`_homonym_keys(p)` → `frozenset` из непустых `norm(name)` и `stem(src)`.

---

## 4. Эскиз вставки (минимальный diff)

**Место:** только ветка лидера в `wiki_outcome_from_verify`, сразу после
успешного `wiki_validate_leader_axes`, **вместо** голого `return leader`.

```python
# … после axis_ok, leader = passports[yes_i[0]-1]["src_table"] …
peers = wiki_homonym_kind_peers(passports, leader)
if peers:
    diag["wiki_verify"] = "clarify"
    diag["wiki_homonym_tie"] = [p.get("src_table") for p in peers]
    diag["wiki_homonym_blocked_leader"] = leader   # след лотереи verify
    return {
        "outcome": "clarify",
        "candidates": peers,
        "diag": diag,
    }
diag["wiki_verify"] = leader
return {"outcome": "leader", "leader": leader, "diag": diag}
```

### Что НЕ делать

- Не трогать порог В4 (`ровно один yes` + остальные `no`) для **различимых** имён.
- Не дублировать проверку во втором месте (`try_wiki_hybrid` 1117+) — verify и
  так финальный перекрыватель pick (1076–1081); одна точка = один замок.
- Не хардкодить `реализациятмц` / okna / числа 75705/79705.
- Не менять `filter_pool_by_named_type` (1049–1051): если человек уже сказал
  «документ»/«регистр», пул сужен — peers пуст, лидер остаётся. Это дополнение,
  не замена.
- Не писать новые тексты для модели: различитель в подписи меню кодом
  (`label_with_kind`), не промтом.

### Порядок условий (контракт владельца)

```text
verify дал ровно одного yes (все остальные no)?
  нет  → как сейчас (clarify / none)          # «не развёл уверенно»
  да   → есть homonym-peers другого kind?
           да  → clarify (меню)               # «имена совпадают»
           нет → leader                       # одиночный / различимый
```

То есть: **неуверенный verify ИЛИ одноимённость** → меню; уверенный verify
**и** различимые имена → лидер.

---

## 5. Пример: «Сколько записей в реализациятмц»

| Шаг | Сейчас (лотерея) | После S2-b |
|---|---|---|
| Пул wiki | `document_…`, `accumulationregister_…` (тип в вопросе не назван) | то же |
| Verify | иногда yes→doc / no→reg, иногда наоборот | то же (модель может врать) |
| Исход кода | `leader` молча → SQL → **75 705 или 79 705** | `clarify`, candidates = оба |
| Ответ человеку | одно число | меню двух прочтений |
| Подписи | — | через `mk_opts`→`disambiguate_labels`: **«… (документ)»** и **«… (регистр накопления)»**; затем `wiki_menu_captions` сохраняет kind-хвост (`wiki_human_menu_caption` 450–453) |

После выбора человеком — обычный focus/второй заход (уже в тракте). Заплатки
«предпочесть регистр» запрещены контрактом эпизода.

Контроль: вопрос «записей **в документе** реализациятмц» →
`named_platform_kinds` режет регистр → peers нет → одиночный лидер OK.

---

## 6. Риски и как не сломать одиночных лидеров

| Риск | Почему низкий / митигация |
|---|---|
| Лишние clarify на различимых сущностях | Срабатывает только при совпадении name **или** stem **и** разном kind |
| Два справочника с похожими именами, один kind | Предикат требует `kind_i != kind_j` → не трогает |
| Один кандидат в пуле | `len(pool) < 2` / peers=[] → лидер как сейчас |
| Axis/measure уже отличают в паспорте (`distinct`) | Модель это видит, но человеку одноимённость всё равно неразличима без kind в подписи — меню по решению владельца правильнее лотереи |
| Регрессия замков «one yes → leader» | Карточки `catalog_a`/`catalog_b` с **разными** name — peers пуст; тесты остаются зелёными |
| Меню из одного пункта | Существующий `if len(opts) >= 2` (1107) — если mk_opts схлопнет, уйдём в отсутствие clarify-return; peers строить так, чтобы src разные → opts≥2 |
| short-tail вне verify | Сосед только в «Other pool names» не в паспортах — не в peers; на практике лотерея = оба в top-N |

---

## 7. Какие замки добавить

Существующие:

- `test_verify_threshold_menu.py` — порог yes/unsure/missing (не одноимённость).
- `test_wiki_candidate_verify.py` — «one yes → leader» на **разных** именах.

**Новые** (предпочтительно один файл `test_wiki_homonym_menu.py` рядом, либо
секция в `test_wiki_candidate_verify.py`):

| # | Кейс | Ожидание |
|---|---|---|
| 1 | Два паспорта: одно `name`, kinds `document` / `accumulationregister`; verdicts yes/no | `outcome=clarify`, `len(candidates)==2`, в diag `wiki_homonym_tie` |
| 2 | Те же src, **разные** `name` («Альфа»/«Бета»); yes/no | `outcome=leader` (регрессия В4) |
| 3 | Одинаковый stem в `src_table`, пустые/разъехавшиеся name, разные kinds; yes/no | `clarify` (ветка «близкие паспорта») |
| 4 | Одинаковое name, **одинаковый** kind (`catalog`×2); yes/no | `leader` (вне скоупа S2-b) |
| 5 | Подписи меню: после `mk_opts`+`disambiguate_labels` (или интеграционный вызов пути clarify) оба label содержат хвосты `kind_word` | нет двух голых одинаковых строк без «(…)» |
| 6 | (опционально) `named_type` в вопросе сузил пул до 1 kind | peers=[] даже при одинаковом stem с «призраком» вне пула — лидер |

В `test_one_path` **новый символ-выбиратель не появляется** (правка внутри
`wiki_outcome_from_verify`); чёрный список (г) не расширять именем. После
внедрения — полный прогон `test_one_path` + `test_wiki_candidate_verify` +
`test_verify_threshold_menu` + новый замок; живой L67-вопрос «записей в
реализациятмц» → `kind=clarify`, 2 option с kind-хвостами (замер после кода,
не в этом отчёте).

---

## 8. Объём внедрения (оценка)

| Что | Оценка |
|---|---|
| `wiki_homonym_kind_peers` + helpers ключей | ~25–40 строк в `z21_wiki_choice.py` |
| Вставка в ветку лидера (843–851) | ~10 строк |
| Замок(и) | ~80–120 строк теста |
| z20 / mk_opts / captions | **0** (переиспользование) |

Документы после кода (не этот отчёт): `CHANGELOG`, строка в `activeContext`
(эпизод S2-b закрыт), при сдвиге контракта — пометки в `HOW_IT_WORKS` про
wiki-clarify при одноимённых видах.

---

## 9. Связь с остальным S2 (не делать в этом диффе)

| Тема | Связь |
|---|---|
| S2-чистка мёртвых символов (~2.2k) | Ортогонально; не трогать живые 149/149 |
| Silent `measure_choice` / `_pick_kind_axis_col` / `stock_net_register_pair` | Тот же **класс** дефекта («>1 → меню»), другие файлы; не смешивать с z21-homonym |
| «Заплатка предпочтения регистра» | Запрещена; это меню |

---

## 10. Чеклист исполнителя (когда разрешат код)

1. Добавить `wiki_homonym_*` в `z21_wiki_choice.py`.
2. Вставить блок peers в `wiki_outcome_from_verify` перед return leader.
3. Замок №1–5 зелёный без сети/БД (моки паспортов).
4. Не коммитить чужой индекс (pathspec).
5. Замер: вопрос-пример → clarify с двумя kind-подписями; контрольный
   «в документе …» → по-прежнему один лидер.
