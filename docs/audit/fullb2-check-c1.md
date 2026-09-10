# Контроль C1

Линза: сверка P1 → план v2 + Q6 по коду.
Дата: 10.09.2026. Режим: только чтение (код/БД не трогались).
Объект: `docs/audit/FULLB2_PLAN_2026-09-10.md` **v2**.
Список правок: `docs/audit/fullb2-plan-audit-p1.md`
(§«Правки дословно» + «Упущенное списком» 1–8 + Q2–Q5).
Живой код: `ubuntu/serenedb/corpus_merge.sql`.

**Краткий вердикт:** семантика B1/B2 из P1 в v2 внесена (механизм C выбран,
Q2–Q5 закрыты ссылкой на предикаты P1, ent_guard/die_unmatched/unmatched
в тексте B2). **Q6 = нет:** витринный orphan-путь детей вне стейджа **не
удаляет** — механизм C (§1.3) **нужен**. До показа владельцу по P1-части
осталось: (1) зафиксировать ответ Q6 → оставить C; (2) дописать оффлайн-
фикстуры partial без flip в B6/B7 по списку P1 (i)–(vi).

---

## 1. Сверка правок P1 → v2

### 1.1. Упущенное списком (1–8)

| # | Тема P1 | Где в v2 | Статус |
|---|---|---|---|
| 1 | Закрыть Q2–Q5 предикатами / вложить в B2 | §2.1–2.6 («Предикат — p1 §Q*», SQL — p1 §Q2); §8 открытым остался только Q6 | **внесена** (ссылкой на P1, не copy-paste SQL в тело плана) |
| 2 | Механизм parent gone → child cleanup | §1.3: выбран **C** (STOP) + отложен Q6 | **частично** (выбор C есть; Q6 открыт до этого круга) |
| 3 | Сузить ent_guard / гейт :637-653 | §2.5: «Тем же scope: ent_guard :343-361 и гейт … :637-653» | **внесена** |
| 4 | Сузить die_unmatched :954-960 | §2.4: partial → только ∈ gone_expand; unexpected ≡ unexplained | **внесена** |
| 5 | Empty∧partial → \|gone_expand\|>0 | §2.1: ∧ \|gone_expand(e)\| > 0 (анти-фальшивка) | **внесена** |
| 6 | Merge-STOP: tmp3_corpus → tmp3_build.mode | §1.4: гвард полноты mode до DELETE | **внесена** |
| 7 | Оффлайн-фикстуры partial в B6/B7 (без flip) | §6–7: замки/приёмка flip=0; явного списка (i)–(vi) нет | **частично** |
| 8 | При partial_rebuild=0 правки не меняют STOP-кардинальности | §3.7, §7.3 (STOP≡baseline+allowlist), §10.6 (partial-тела мертвы) | **частично** (эффект есть; фраза про план запроса/NULL mode не выписана) |

### 1.2. Правки дословно (8 блоков)

| Блок P1 | Где в v2 | Статус | Замечание |
|---|---|---|---|
| **B1.2** parent/child → A/B/C | §1.3 | **частично** | Выбран C; A/B отвергнуты с причиной; текст STOP близок к P1-(C); висит Q6 |
| **B1 п.5** mode-гвард | §1.4 | **внесена** | Семантика дословная; SQL CASE WHEN EXISTS — не copy-paste, смысл тот же |
| **B2.1** Q3 + \|gone_expand\|>0 | §2.1 | **внесена** | «Предикат — p1 §Q3» |
| **B2.2** die_unmatched + Q4 row-level | §2.2–2.4 | **внесена** | key_deleted_delta только full; die_unexplained UNION; die_unmatched partial∈G |
| **B2.3** Q5 + ent_guard 0.1% | §2.5 | **внесена** | wave=full; 10% = unmatched∪G; ent_guard тем же scope |
| **B2.4** Q2 expect | §2.6 | **внесена** | формула + снапшот; «SQL — p1 §Q2» |
| **B2 п.6** unmatched full/partial | §2.2 | **внесена** | full=:226-333; partial∈G; запрет ломать shrink/repost |
| **B6/B7** фикстуры (i)–(vi) | §6–7 | **частично** | Есть emb-lock, mode-lock, B7 flip=0; нет явных (ii) count-eq partial, (iii)/(iv) empty±gone, (v) mixed shrink/repost, (vi) parent/child C |
| **§8 Q2–Q5** закрыть | §8 | **внесена** | Открытым оставлен только Q6 |

### 1.3. Предикаты Q2–Q5

| Q | Ответ P1 | В v2 | Статус |
|---|---|---|---|
| Q2 | expect до DELETE; постчек UNION full/partial | §2.6 + ссылка p1 §Q2 | **внесена** (семантика + указатель на SQL) |
| Q3 | STOP; delete-only = partial ∧ свежий gone ∧ \|G\|>0 | §2.1 + p1 §Q3 | **внесена** |
| Q4 | orphan/key_deleted_delta только full; unexplained: full entity-wide / partial row-level G | §2.2–2.3 + p1 §Q4 | **внесена** |
| Q5 | числитель 10% = unmatched-full ∪ G-partial; wave только full; +ent_guard | §2.5 + p1 §Q5 | **внесена** |

---

## 2. Разбор Q6 (по коду)

**Вопрос (§8 v2):** закрывает ли витринный orphan-путь удаление child-строк
при gone родителя, если child ∉ стейдж такта?

### 2.1. Что делает orphan-путь

Цепочка — **свидетель для гвардов**, не DELETE:

1. **unmatched** наполняется только по сущностям стейджа
   (`EXECUTE …(src_table)` из `DISTINCT src_table FROM tmp3_corpus`, :326-333;
   тело PREPARE фильтрует `c.src_table = $1`, :230 / :281).
2. **delta_rec** (:481-495) ← unmatched ∩ collapse_cand.
3. **orphan_rec** (:572-575) ← delta_rec ⋈ rec_dead.
4. **deleted_delta_rows** (:577-582) ← orphan_rec ∧ ¬doc_alive — витринный
   список ключей «родитель мёртв».
5. **key_deleted_delta** (:620-625) — агрегат для quality/гвардов
   (`уйдёт` по collapse_cand), **не** statement удаления.
6. Потребление:
   - гейт «частичная потеря» :645 — `NOT EXISTS key_deleted_delta` (исключает
     STOP);
   - гвард 10% :688-709 — вычитает entity из «снесло бы»;
   - die_unexplained :997-998 — entity-wide `NOT EXISTS key_deleted_delta`
     (объясняет unmatched_kill, **не удаляет**).

### 2.2. Кто реально удаляет

Единственный DELETE строк корпуса по unmatched-логике:

```1371:1374:ubuntu/serenedb/corpus_merge.sql
DELETE FROM search_corpus c
WHERE c.src_table IN (SELECT DISTINCT src_table FROM tmp3_corpus)
  AND NOT EXISTS (SELECT 1 FROM tmp3_corpus t
                  WHERE t.src_table = c.src_table AND t.row_key = c.row_key);
```

Фильтр `IN (SELECT DISTINCT src_table FROM tmp3_corpus)`: сущность, которой
**нет** в стейдже, **не входит** в множество удаления. Sources-orphan
(:1381-1382) трогает только таблицы вне `search_sources`, не children живого
источника.

### 2.3. Следствие для child ∉ стейдж

| Шаг | Child ∉ tmp3_corpus? | Эффект |
|---|---|---|
| unmatched / orphan / deleted_delta_rows | да — child не в диспетчере :331 | child-ключей в витринном orphan **нет** |
| key_deleted_delta / die_unexplained / 10%-гвард | нет строк child | **не** объясняет и **не** удаляет child |
| DELETE :1371 | `src_table` child ∉ DISTINCT tmp3 | **anti-join child не трогает** |

Даже если parent в стейдже и ушёл anti-join'ом / gone, child-сироты с живым
emb остаются в корпусе до полного rebuild ребёнка.

### 2.4. Ответ Q6

**Нет.** Витринный orphan-путь (:577-582 → :620-625 → :997-998 / :688-709)
**не** закрывает удаление детей при gone родителя, если child ∉ стейдж.
Ключ: :1371 режет по `tmp3_corpus`; orphan — только witness по unmatched
стейджа.

**Следствие:** механизм C (§1.3 v2) **нужен** (оставить STOP-детект;
не снимать в пользу «только замок на регрессию»).

---

## 3. Атаки P1 1–7 → v2

| # | Атака P1 | В v2 | Вердикт |
|---|---|---|---|
| 1 | Инверсия `\if` / anti-join в true | §1.1 else=дословный anti-join; §1.5 structural assert; B7 flip=0 | **закрыта** |
| 2 | Entity без mode при flip=1 | §1.4 STOP mode отсутствует | **закрыта** |
| 3 | Parent full / child partial — сироты ТЧ | §1.3 механизм C; Q6 (этот круг) = orphan не спасает | **закрыта спецификацией C** (код C ещё не написан — план ок; фикстура (vi) слабая) |
| 4 | Empty + фальшивый маркер / пустой expand | §2.1 \|gone_expand\|>0 | **закрыта** |
| 5 | Сужение unmatched ломает shrink/repost full | §2.2 запрет сужать full-путь; §10.10 | **закрыта** |
| 6 | B2 без сужения ent_guard 0.1% | §2.5 | **закрыта** |
| 7 | die_unmatched без сужения | §2.4 | **закрыта** |

---

## 4. Вердикт

### P1-часть v2 готова к показу владельцу?

**Почти — с двумя обязательными дописками до волны-показа по P1.**

Семантика B1/B2, предикаты Q2–Q5, атаки 1–2 и 4–7 закрыты в тексте v2.
Атака 3 закрыта выбором C; Q6 по коду подтверждает, что C нельзя снять.

### Что осталось (дословные правки в план)

1. **§8 / §1.3 — ответ Q6:**  
   > Q6 = нет (orphan не удаляет child ∉ стейдж; :1371 фильтр по tmp3_corpus).
   > Механизм C оставить. Только замок на регрессию — недостаточно.

2. **B6/B7 — явный список оффлайн-фикстур partial без flip (из P1):**
   - (i) partial-стейдж + anti-join выключен → count emb соседей бит-в-байт;
   - (ii) count-eq partial по expect;
   - (iii) empty+gone-only PASS;
   - (iv) empty без маркеров / без expand STOP;
   - (v) mixed full+partial: shrink/repost full зелёные;
   - (vi) parent gone / child ∉ стейдж → срабатывает C (STOP).

3. *(желательно, не блокер показа)* §10 или B7: одной фразой — при
   `partial_rebuild=0` unmatched/wave/guards не меняют кардинальности
   STOP-классов vs baseline (включая NULL-mode край).

После (1)–(2) — P1-часть v2 **готова** к показу владельцу (остальной план —
другие линзы волны 3).
