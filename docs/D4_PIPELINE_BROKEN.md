# Д4 — такт свежести упал (okna, 27.08)

Блокер продукта: данные из 1С не доезжали; бот предупреждал
«последнее обновление из 1С было ~4500 мин назад».

## 1. Сколько стоял такт

| Метка | Факт |
|---|---|
| Последний успешный `Finished` | **2026-08-24 05:40:32 UTC** |
| Первое падение по этой причине | **2026-08-24 19:36:21** — `syntax error at or near ":"` на `:"solr_syn_dict"` |
| Срез оркестратора | 27.08 ~08:42 |
| Падений `СБОРКА ПРЕРВАНА: развёртывание объектов` за 7 дней | **3083** (все с одной ошибкой `syntax error`) |
| Простой по этой причине | **~2,5 суток** (24.08 19:36 → 27.08 08:42); от последнего OK — **~3,1 суток** |

Не всегда эта причина: 23.08 были другие отказы (эмбеддер / postcheck /
timeout), но **с 24.08 05:40 до 19:36** такты снова проходили успешно.
Непрерывная цепочка «развёртывание объектов» / `:"solr_syn_dict"` — с
**24.08 19:36** до починки.

Разбивка `СБОРКА ПРЕРВАНА` за 7 дней: развёртывание объектов 3083; сборка
корпуса 355; эмбеддер не та модель 69; precheck 3; postcheck 2.

## 2. Кто зовёт `corpus_init.sql` и где `solr_syn_dict`

Цепочка: `1c-serene-pipeline@postgres` → `/opt/1c-mcp-reports/pipeline.sh`
→ `./build.sh` → `psql … -f corpus_init.sql`.

В **репозитории** (`ubuntu/serenedb/build.sh`):

- `SOLR_SYN_DICT="${ASK_SOLR_SYNONYMS_DICT:-${SOLR_SYN_DICT:-search_dict_syn}}"`
- шаг 0: `psql … -v dict_locale=… -v solr_syn_dict="$SOLR_SYN_DICT" -f corpus_init.sql`

На **живом okna** на момент срыва:

| Файл | mtime | Содержание |
|---|---|---|
| `corpus_init.sql` | 24.08 19:34 | уже с `CREATE … :"solr_syn_dict"` |
| `build.sh` | 21.08 12:08 | `psql … -v dict_locale=… -f corpus_init.sql` — **без** `-v solr_syn_dict` |

Итог: переменная задаётся в репозиторном `build.sh`; в живом такте её не
было, потому что на сервере лежал **старый** `build.sh` при **новом**
`corpus_init.sql`. psql получил литерал `:"solr_syn_dict"` → syntax error.

## 3. Починка

1. **`corpus_init.sql`** — только подстановка (морфологию словаря не трогали,
   контур С5): перед `CREATE` добавлено

   ```
   \if :{?solr_syn_dict}
   \else
   \set solr_syn_dict search_dict_syn
   \endif
   ```

   То же умолчание, что в `build.sh`. Даже старый вызывающий без `-v` не
   роняет такт.

2. **`build.sh`** — явный `fail`, если `SOLR_SYN_DICT` пуст; `-v` как было.

3. **Замок** `ubuntu/serenedb/test_psql_init_vars.py` — оффлайн: все `:vars`
   init/precheck покрыты `-v` в `build.sh`; искусственно убранный
   `-v solr_syn_dict` ловится отдельной проверкой. Замер: **PASS 9 FAIL 0**.

## 4. Расхождение версий / дыра выката

- Полный раскладчик **`ubuntu/serenedb/deploy.sh`** копирует `*.sh` и `*.sql`
  (SQL-слой **входит**).
- На продукте `SERENE_SRC_DIR` пуст → такт **не** зовёт `deploy.sh`.
- Горячий выкат **`work/acceptance/deploy-okna-serene-ask.sh`** до Д4
  выкатывал только ask/словарные `*.py`/`branch_alias*` —
  **`build.sh` / `corpus_init.sql` / `corpus_precheck.sql` в списке не было**.

Вторая дыра (прямо): SQL-слой такта **не входил** в единственный штатный
горячий выкат на okna. Частичная ручная подкладка init 24.08 19:34 без
обновления `build.sh` и дала 3083 падения.

Исправление: эти три файла добавлены в `FILES`/`FILES_R` скрипта и в таблицу
`RUNBOOK_DEPLOY.md` §10.2.

## 5. Живой прогон

(заполняется после выката и `systemctl start 1c-serene-pipeline@postgres`)

- `systemctl is-active`: …
- хвост журнала: …
- свежесть (`build_ts` / предупреждение бота): …

## 6. Замок — сломанный vs починенный

```text
# починенный (дерево после Д4)
$ python3 ubuntu/serenedb/test_psql_init_vars.py
PASS 9 FAIL 0

# сломанный: тест сам вырезает -v solr_syn_dict из копии build и проверяет
# «сломанный build (без -v solr_syn_dict) ловится» → ok
# если убрать проверку покрытия -v в реальном build.sh — красный
# «build passes -v solr_syn_dict to corpus_init»
```

Рантайм: пустой `SOLR_SYN_DICT` → `СБОРКА ПРЕРВАНА: не задан SOLR_SYN_DICT`
до psql; отсутствие `-v` при живом init → умолчание `\if`, такт не падает
на syntax error.

Доки: Sql › Statements › CREATE TEXT SEARCH DICTIONARY.
