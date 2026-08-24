# Инвентарь бизнес-справочников (§7bis) — локальные следы

**Дата:** 2026-08-24  
**Объём:** дерево `/srv/1c` + живой замер okna 24.08 (ниже §«живой»).  
**Живой замер okna `[24.08]`:** да — см. секцию «живой $metadata 24.08».  
XML-снимок `$metadata` на диске пуст (`packet-meta/okna-1/` только
`.first-data` + `skipped.json`); контур пакетный, OData-шлюза нет — состав
снят по живой витрине SereneDB `:7890` + `search_tables`.  
**Код ask не менялся.** Списки имён в исполняемый код не вшиваются.

Иерархия источников — [`docs/PLAN_ANSWER_CONTRACT.md`](../docs/PLAN_ANSWER_CONTRACT.md) §7bis:
1С `$metadata` → агрегаты из данных → развилка+память → внешний справочник последним.

---

## 1. Где лежат локальные следы

| Артефакт | Что это | База |
|---|---|---|
| [`docs/completeness-okna/contour.txt`](../docs/completeness-okna/contour.txt) | 819 имён контура пакета (`okna-1.config.entities`) | **okna** |
| [`docs/completeness-okna/arrived.txt`](../docs/completeness-okna/arrived.txt) | 369 сущностей, доехавших в витрину | **okna** |
| [`docs/COMPLETENESS_OKNA.md`](../docs/COMPLETENESS_OKNA.md) | опись полноты; контур ≠ полный `$metadata` | **okna** |
| [`work/manifest-diff/live-metadata-ut11.xml`](manifest-diff/live-metadata-ut11.xml) | полный живой `$metadata` УТ 11 | **ut11**, не okna |
| [`work/manifest-diff/gen-metadata-ut11.xml`](manifest-diff/gen-metadata-ut11.xml) | синтетический `$metadata` той же базы | **ut11** |
| [`docs/completeness-klient1/arrived.txt`](../docs/completeness-klient1/arrived.txt) | доехавшие сущности klient-1 (типовой стек УТ) | **klient-1**, не okna |
| [`ubuntu/serenedb/corpus_init.sql`](../ubuntu/serenedb/corpus_init.sql) | схема `search_tables` / `search_meta` | универсально |
| [`ubuntu/serenedb/corpus_build.sql`](../ubuntu/serenedb/corpus_build.sql) | чтение `$metadata` движком | универсально |

⚠️ Контур okna — список из конфига пакета, не дамп `$metadata`. Отсутствие имени
в `contour`/`arrived` **не доказывает** отсутствия сущности в OData; наличиеет
только «в локальных okna-артефактах не видно».

---

## 2. Кандидаты (таблица)

Уверенность:

- **есть в dump okna** — имя в `completeness-okna` (contour и/или arrived);
- **только типовое имя** — есть в ut11 `$metadata` и/или klient-1 arrived, на okna локально не найдено;
- **не найдено локально** — ни в okna-списках, ни как типовое имя в наших дампах.

| Кандидат сущности | Где найден (файл:строка) | Уверенность | Следующий замер на живой okna |
|---|---|---|---|
| `InformationRegister_Календарь` | `docs/completeness-okna/arrived.txt:328`, `contour.txt:724` | есть в dump okna | `GET …/$metadata` → есть ли EntitySet; поля (дата / вид дня / рабочий); `count` строк; пригодно ли как ось «календарные vs рабочие» |
| `Catalog_ПроизводственныеКалендари` | ut11: `work/manifest-diff/live-metadata-ut11.xml:244338` (EntitySet); klient-1: `docs/completeness-klient1/arrived.txt:282` | только типовое имя | есть ли на okna под этим или другим именем; не путать с `InformationRegister_Календарь` |
| `InformationRegister_ДанныеПроизводственногоКалендаря` | ut11: `live-metadata-ut11.xml:242098`; klient-1: `arrived.txt:1370` | только типовое имя | то же; это канон УТ для рабочих/праздничных дней |
| `Catalog_Календари` (+ ТЧ расписания) | ut11: `live-metadata-ut11.xml:244166`; klient-1: `arrived.txt:183–185` | только типовое имя | на okna в completeness **нет** |
| `InformationRegister_КалендарныеГрафики` | ut11: `live-metadata-ut11.xml:241376`; klient-1: `arrived.txt:1390` | только типовое имя | на okna в completeness **нет** |
| `InformationRegister_ПериодыНерабочихДнейКалендаря` | klient-1: `arrived.txt:1438` | только типовое имя | на okna / в ut11 EntitySet-поиске по completeness-okna **не найдено** |
| `РегламентированныйПроизводственныйКалендарь` (имя из §7bis) | ни в completeness-okna, ни как EntitySet в ut11-дампе под этим токеном | не найдено локально, нужен живой `$metadata` | поиск по `$metadata` okna (русские/латинские/транслит варианты); возможно это объект конфигурации, не EntitySet OData |
| `Catalog_Валюты` | okna: `arrived.txt:35`, `contour.txt:88`; ut11: `live-metadata-ut11.xml:244692` | есть в dump okna | поля кода/наименования; пересечение с фактами продаж |
| `Catalog_КлассификаторВалют` | okna: `arrived.txt:69`, `contour.txt:139` | есть в dump okna | отличить от `Catalog_Валюты` (классификатор vs рабочие валюты) |
| `InformationRegister_КурсыВалют` | okna: `arrived.txt:332`, `contour.txt:733`; ut11: `live-metadata-ut11.xml:241352` | есть в dump okna | Period + валюта; нужна ли ось курса для развилок |
| `Constant_ВалютаБухгалтерскогоУчета` | okna: `arrived.txt:155`, `contour.txt:264` | есть в dump okna | одна константа — якорь «валюта учёта», не справочник |
| `Catalog_Города` | okna: `arrived.txt:52`, `contour.txt:107` | есть в dump okna | гео-ось «клиенты из …»; связи с контрагентами |
| `Catalog_Страны` | okna: `arrived.txt:121`, `contour.txt:209` | есть в dump okna | то же; на УТ имя часто `Catalog_СтраныМира` |
| `Catalog_СтраныМира` | ut11: `live-metadata-ut11.xml:243356`; klient-1: `arrived.txt:319` | только типовое имя | на okna локально — `Catalog_Страны`, не `СтраныМира` |
| `Catalog_КлассификаторРайонов` | okna: `arrived.txt:78`, `contour.txt:148` | есть в dump okna | уточнить семантику (районы страны vs адм. единицы) |
| `Constant_Страна` | okna: `arrived.txt:186`, `contour.txt:295` | есть в dump okna | якорь страны учёта |
| `Catalog_БизнесРегионы` | ut11: `live-metadata-ut11.xml:244700`; klient-1 константы `ИспользоватьБизнесРегионы` | только типовое имя | на okna в completeness **нет** |
| `InformationRegister_АдресныеОбъекты` (+ ФИАС-стек) | ut11: `live-metadata-ut11.xml:241562`; klient-1: `arrived.txt:1352` (+ `ДополнительныеАдресныеСведения`, `ЗагруженныеВерсииАдресныхСведений`, …) | только типовое имя | на okna в completeness **нет**; замер klient-1 «ФИАС ~5,5 млн» (§7bis) — **не** okna |
| ФИАС / КЛАДР как имена EntitySet | completeness-okna: совпадений по `ФИАС`/`КЛАДР`/`АдресныеОбъект` нет | не найдено локально (на okna), нужен живой `$metadata` | подтвердить отсутствие адресного классификатора на okna; гео опираться на `Города`/`Страны`/`КлассификаторРайонов`, если они в `$metadata` |

---

## 3. Куда вставлять ось календаря (существующие читатели `$metadata`)

Новый загрузчик не нужен. Точки расширения уже есть:

| Место | Роль | Файл:строки |
|---|---|---|
| Сборка корпуса | движок сам `read_text(:'gate' \|\| '/$metadata')` → `tmp3_ent` / `tmp3_prop` / `tmp3_key`; уже пишет классы в `search_meta` (напр. `balance_registers`) | `ubuntu/serenedb/corpus_build.sql:31–100` |
| Запуск сборки | `GATE="${ETL_ODATA_BASE:-…}"`, `-v gate="$GATE"` | `ubuntu/serenedb/build.sh:32`, `:250` |
| Схема каталога сущностей | `search_tables` (метка/parent), `search_meta` | `ubuntu/serenedb/corpus_init.sql:48–72` |
| HTTP / packet-снимок (Python) | `_load_metadata`, `_parse_metadata_xml`, `published_entity_sets` | `ubuntu/serenedb/poc_load_entity.py:88–130`, `:448–457` |
| Контур пакета | `_entity_sets` / `_props_by_type` из файла `$metadata` | `ubuntu/packet/packet_config.py:133–146` |
| Запись снимка | `<PACKET_META_DIR>/<base_id>/$metadata` | `ubuntu/packet/packet_apply.py:588–615` |

Практичный следующий код-шаг (не в этом заходе): по аналогии с
`balance_registers` — детерминированный отбор EntitySet из `tmp3_ent` по
**структуре** (поля даты/вида дня), без списка имён конфигурации; метка оси —
в `search_meta` / карту рядом с `search_balance_map`.

---

## 4. Вывод по первому шагу §7bis (производственный календарь на okna)

- **Живой okna `[24.08]`:** ось «календарные vs рабочие дни» **можно заводить**
  на `InformationRegister_Календарь` + `ChartOfCharacteristicTypes_ДниНедели`
  (явные виды: рабочий / выходной / праздничный / сокращённый /
  предпраздничный) + `Catalog_ГрафикиРаботы`. Типового УТ
  `ДанныеПроизводственногоКалендаря` / `ПроизводственныеКалендари` в витрине
  **нет** — не блокер: локальный регистр уже несёт разметку вида дня.
- Валюты и гео-якоря (`Catalog_Валюты`, `Города`, `Страны`,
  `КлассификаторРайонов`) в витрине есть и непусты; ФИАС /
  `АдресныеОбъекты` — **нет** (гео опирается на `Города`/`Страны`/`Районы`).
- XML `$metadata` на диске okna по-прежнему отсутствует (пакетный контур);
  источник замера — витрина, не HTTP OData.

---

## живой $metadata 24.08

**Хост:** okna (`gpu-erw.timpul.pro:2202`), SereneDB **26.08.1** `127.0.0.1:7890`,
`dbname=postgres`. UTC **2026-08-24T16:51Z**.  
**XML `$metadata`:** файл
`/var/lib/serenedb/packet-meta/okna-1/$metadata` **отсутствует** (в каталоге
только `.first-data` + `skipped.json`; `ETL_ODATA_BASE` = этот каталог;
`1c-odata-gateway` на okna нет — пакетный контур).  
**Источник состава:** живые таблицы витрины + строки `search_tables`
(эквивалент «доехавших» EntitySet). Свои выгрузки наружу не писались —
только `count(*)` / `\d`-аналог через `information_schema`.

### Найденные сущности (шаблоны Календар*/Производствен*/Валют*/Адрес*/ФИАС*/Город*/Страны*)

| Имя (OData / витрина) | Есть? | Строк | Источник замера |
|---|---|---|---|
| `InformationRegister_Календарь` | есть | **12 085** | `count(*)` витрина; в `search_tables` label «Календарь»; поля `Дата`, `День_Key`, `Часы`, `Значение`, `ГрафикРаботы_Key` |
| `ChartOfCharacteristicTypes_ДниНедели` | есть | **5** | витрина; join с `День_Key` календаря: Рабочий / Выходной / Сокращённый / Праздничный / Предпраздничный |
| `Catalog_ГрафикиРаботы` | есть | (справочник графиков) | витрина; ключи календаря → «Пятидневная…» / «Шестидневная…» |
| `Catalog_ПроизводственныеКалендари` | нет | — | `pg_class` public: таблицы нет |
| `InformationRegister_ДанныеПроизводственногоКалендаря` | нет | — | то же |
| `Catalog_Календари` | нет | — | то же |
| `InformationRegister_КалендарныеГрафики` | нет | — | то же |
| `InformationRegister_ПериодыНерабочихДнейКалендаря` | нет | — | то же |
| `Catalog_Валюты` | есть | **6** | `count(*)` витрина; `search_tables` |
| `Catalog_КлассификаторВалют` | есть | **52** | `count(*)` витрина |
| `InformationRegister_КурсыВалют` | есть | **3 824** | `count(*)` витрина |
| `Constant_ВалютаБухгалтерскогоУчета` | есть | **1** | `count(*)` витрина |
| `Catalog_Города` | есть | **116** | `count(*)` витрина (описания часто = адрес/склад, не «чистый» город) |
| `Catalog_Страны` | есть | **6** | `count(*)` витрина |
| `Catalog_КлассификаторРайонов` | есть | **51** | `count(*)` витрина |
| `Constant_Страна` | есть | **1** | `count(*)` витрина |
| `Catalog_СтраныМира` / `Catalog_БизнесРегионы` | нет | — | `pg_class`: нет |
| `InformationRegister_АдресныеОбъекты` (+ ФИАС-стек) | нет | — | `pg_class` / pattern `фиас\|кладр\|адресн`: пусто |

### Вердикт оси W (календарные / рабочие дни)

**Можно заводить** на связке `InformationRegister_Календарь` ↔
`ChartOfCharacteristicTypes_ДниНедели` (и при необходимости
`Catalog_ГрафикиРаботы`): в данных уже есть явная разметка рабочего /
выходного / праздничного дня и часы. Типовой УТ-календарь на okna не
опубликован — для оси не требуется. Внешний справочник праздников не нужен
на этом шаге.

---

## 5. Как снимали / что осталось

1. ~~Снимок XML `$metadata`~~ — на новой okna файла нет; при появлении
   `packet_apply` с `metadata.included=true` можно перепроверить EntitySet-список
   без опоры на витрину.
2. Поиск по витрине + `search_tables` по шаблонам (сделано 24.08).
3. `count` и структура для кандидатов (сделано).
4. Код оси W — после выката W-трека (не в этом заходе).
