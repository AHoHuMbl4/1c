# И0 — утилита эталонов: живой прогон okna (27.08.2026)

Задача [`PLAN_TO_TARGET.md`](PLAN_TO_TARGET.md) §Поток И / И0.
Инструмент: [`work/gold/client_gold.py`](../work/gold/client_gold.py) (build:
packet↔vitrine) + базовая классификация [`ubuntu/serenedb/etalon_1c.py`](../ubuntu/serenedb/etalon_1c.py).
Замки: `work/gold/test_client_gold.py` (**16/0**), `ubuntu/serenedb/test_etalon_1c.py` (**70/0**).
Набор: `ubuntu/serenedb/client-gold-okna.tsv`.

## Что сделано

1. Прочитан существующий инструмент (verify / generate / classify). Недоделок-заглушек
   нет; добавлено для закрытия прогона на okna (packet-режим):
   - `fact.sql` в срезе — факт 1С из **витрины** одним SQL (без HTTP-шлюза);
   - `--from-search-tables` — покрытие сущностей из `search_tables`;
   - `cmd_verify` не требует OData, если все срезы на `fact`/`corpus`.
2. Замок: `python3 test_etalon_1c.py` → **PASS 70 / FAIL 0**.
3. Проверка шлюза OData okna — **не выполнена по транспорту сессии**: Cursor
   runtime floor блокирует чтение `~/.ssh/id_ed25519_deploy` (SSH
   `gpu-erw.timpul.pro:2202`). Локальные туннели несут ask `:18091/:18092` и
   SereneDB `:17890`, **порта OData okna среди них нет**. На этом хосте
   (`lxc-claude-1c`) `:6011/:6021` — чужие контуры; upstream 1С
   `192.168.56.1:6003` — connection refused. По
   [`PLAN_MVP_PACKET_TRANSPORT.md`](PLAN_MVP_PACKET_TRANSPORT.md) okna в режиме
   packet: Ubuntu до OData 1С **не** ходит. **Не фиксируем «шлюз мёртв»** —
   живой юнит на okna из этой сессии не проверялся; dual-verify выполнен
   витрина↔корпус (выгрузка 1С пакетами vs слой поиска).
4. Живой `verify` на okna (туннель `port=17890`, DSN из `/tmp/okna-probe.env`):
   **12 срезов**, код выхода 0.
5. `generate --from-journal --from-search-tables` → `client-gold-okna.tsv`
   (**54** вопроса; эталоны проставлены на 12 сверенных).

## Таблица сверки (Europe/Chisinau, сегодня = 2026-08-27, четверг / праздник MD)

| id | Вопрос | Класс | Факт 1С (витрина) | Корпус | Статус |
|---|---|---|---|---|---|
| kontr | сколько у нас вообще клиентов сейчас | С | **362** | 353 | mismatch |
| nomen | сколько позиций у нас в прайсе всего | С | **2389** | 2375 | mismatch |
| org | Сколько организаций? | С | **1** | 1 | match |
| bank | Сколько банков в справочнике? | С | **293** | 293 | match |
| val | Сколько валют? | С | **8** | 6 | mismatch |
| reg_rows | движений в регистре реализации | С | **78176** | 77901 | mismatch |
| yesterday | вчера сколько продали | С→лаг | **147281.15** | 0 | freshness_lag |
| day_before | позавчера сколько было продаж | С→лаг | **171018.11** | 470219.12 | freshness_lag |
| last_week | а на прошлой неделе … | С | **1262950.40** | 1262950.4 | match |
| last_month | сколько было в прошлом месяце всего | С | **2767450.98** | 2767450.98 | match |
| today | сегодня сколько уже наотгружали | Д | **0.00** | 0 | match |
| this_week | сколько сделали за эту неделю | Д | **336383.00** | 470821.66 | freshness_lag |

**Итого:** срезов 12; match 5; freshness_lag 3; mismatch 4 (очередь независимого
прочтения); ошибок транспорта 0. Эталон в gold везде = факт витрины (1С).

Контроль ACCEPTANCE §C на прошлый месяц: **2 767 450,98** — совпал.

## Разбор расхождений (два прочтения → эталон = 1С)

### 1–4. Справочники / строки регистра (mismatch)

| Срез | Прочтение A (витрина = пакеты 1С) | Прочтение B (корпус) | Вердикт |
|---|---|---|---|
| kontr | `count(*)` без папок/удалённых = 362 | `search_corpus` flags = 353 | Δ9: в витрину доехали строки после заморозки корпуса. **Эталон 362** |
| nomen | без папок/удалённых = 2389 | корпус = 2375 | Δ14, та же причина. **Эталон 2389** |
| val | deletionmark≠true = 8 | корпус = 6 | Δ2. **Эталон 8** |
| reg_rows | 78176 строк регистра | 77901 в корпусе | Δ275. **Эталон 78176** |

Интерпретация SQL одинакова; расхождение — **лаг такта** при остановленном
пайплайне (Д5 / `need_metadata`), не спор о смысле вопроса. Статус `mismatch`
оставлен классификатором для `period=stable` (каталоги); в отчёте помечаем
причину: корпус заморожен.

### 5–7. Относительные периоды (freshness_lag) — не FAIL

Посуточный разрез (факт):

| День | Витрина rows/sum | Корпус rows/sum |
|---|---|---|
| 2026-08-24 | 51 / 18 083,74 | 5 / 602,54 |
| 2026-08-25 | 43 / 171 018,11 | 596 / 470 219,12 |
| 2026-08-26 | 133 / 147 281,15 | — |
| 2026-08-27 (сегодня, праздник) | 0 | 0 |

Корпус обрывается на устаревшем снимке 25.08 (старые 596 строк); витрина уже
переписана пакетами. «Вчера» / «позавчера» / «эта неделя» — этикетка
`freshness_lag`, эталон = витрина. Такт остановлен внешней причиной — **не
FAIL инструмента**.

### Закрытые периоды без лага

Прошлая неделя и прошлый месяц: витрина = корпус копейка в копейку.

## Команда повтора

```bash
# туннель okna уже: :17890 → SereneDB, пароль в /tmp/okna-probe.env
set -a && . /tmp/okna-probe.env && set +a
export ETALON_DSN='host=127.0.0.1 port=17890 user=postgres dbname=postgres'
cd /srv/1c/ubuntu/serenedb
python3 test_etalon_1c.py
python3 etalon_1c.py verify --slices slices-okna-i0.json --out /tmp/i0-okna-verify.json
python3 etalon_1c.py generate --from-journal --limit-journal 40 \
  --from-search-tables --limit-tables 20 --out client-gold-okna.tsv
```

Когда SSH к okna разрешён сессии: `systemctl list-units | grep -i odata`,
GET `$metadata` со шлюза, при живом шлюзе — те же срезы с `odata.entity`
вместо / вместе с `fact.sql`.

## Файлы

| Файл | Роль |
|---|---|
| `ubuntu/serenedb/etalon_1c.py` | инструмент |
| `ubuntu/serenedb/test_etalon_1c.py` | офлайн-замок 70/0 |
| `ubuntu/serenedb/slices-okna-i0.json` | 12 срезов прогона |
| `ubuntu/serenedb/client-gold-okna.tsv` | 54 вопроса, 12 с эталоном 1С |
| `docs/I0_ETALON_TOOL.md` | этот отчёт |

Доки SereneDB (батч корпуса): Scalar Subquery; UNION ALL (bag semantics).
