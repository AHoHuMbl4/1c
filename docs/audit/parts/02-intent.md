# 02. intent

Участок: `ubuntu/serenedb/serene_ask.py:809–1372`.

## Зачем участок нужен

Переводит текст вопроса на человеческом языке в типизированную структуру отбора (`terms`, `kind`, `measure`, `want`, `period`/`period2`, `amount`, `about`) через вызов языковой модели и проверку ответа кодом (`INTENT_SYS` `809:848`, `_normalize_intent` `1109:1225`, `parse_intent` `1289:1348`). Промт задаёт смысл полей; форма и потери держатся разбором типов, не текстом промта (`851:875`). При полном провале разбора — `RuntimeError` (`1242:1243`), не пустая «честная» структура.

## Входы

| Что | Где |
|---|---|
| `question: str` | аргумент `parse_intent` `1289`, `_normalize_intent` `1109`, `_one_intent` `1228` |
| `today` | аргумент `parse_intent` `1289`; уходит в user-сообщение `1330` |
| `msgs` | список сообщений в `_one_intent` `1228` (system=`INTENT_SYS`, user=`today`+вопрос) |
| сырой dict модели `d` | `_normalize_intent` `1109` |
| `raw_terms` / поля JSON | `_intent_terms` `989`, нормализаторы `940:986` |
| `groups` | `same_concept_groups` `1057` |
| `samples` | `_merge_intents` `1262` — список нормализованных разборов |
| env | см. «Переключатели» |

К схеме БД, таблицам и строкам корпуса участок из этого кода не обращается (`1290:1294` в docstring; фактический SQL только `ts_lexize` в `same_concept_groups`).

## Порядок работы

1. `parse_intent(question, today)` (`1289`): ключ памяти `(today, question)` (`1324`); при `INTENT_MEMO > 0` и попадании — `json.loads` и return (`1325:1328`).
2. Сбор `msgs`: system=`INTENT_SYS`, user=`today=%s\n\nQuestion: %s` (`1329:1330`).
3. Первый образец: `_one_intent(msgs, question)` (`1331`).
4. Цикл до `INTENT_SAMPLES`: пока `min(отрыв по полям _INTENT_FIELDS) < INTENT_LEAD` — ещё `_one_intent` (`1332:1335`).
5. `_merge_intents(samples)` (`1336`).
6. `same_concept_groups(out["terms"])`; при сведении — правка `terms` и запись в `parse.fixed` (`1337:1343`).
7. При `INTENT_MEMO > 0`: если словарь полон — `clear`, затем запись JSON (`1344:1347`); return `out` (`1348`).

`_one_intent` (`1228:1244`):
1. `ds_chat(msgs, max_tokens=INTENT_MAX_TOKENS)` (`1230`).
2. `_first_intent_object(raw)` — лучший `{...}` по числу полей из `terms/kind/want/measure/period/amount/about` (`1351:1370`, блоки через `_json_blocks` `910:937`).
3. Если `None` — второй `ds_chat` с assistant+user `"Return the JSON object."` (`1238:1241`).
4. Снова `None` → `RuntimeError("модель не вернула разбор вопроса")` (`1242:1243`).
5. Иначе `_normalize_intent(d, question)` (`1244`).

`_normalize_intent` (`1109:1225`): `terms` → `_intent_terms`; `kind`/`measure` → `_intent_text` (+ `fixed` при списке >1); вырезка из `terms` написаний, совпадающих целиком с `kind`/`measure` после `_intent_word` (`1132:1142`); `want` ∈ `{list,sum,count}` иначе `"list"` (`1144:1149`); `about` ∈ `{data,coverage}` иначе `"data"` (`1151:1152`); `period`/`period2` — только ISO `YYYY-MM-DD`, иначе `lost`; перевёрнутый from>to → очистка + `lost` (`1154:1210`); `amount` — op∈`_AMOUNT_OPS`, числа через `_intent_number` (`1174:1192`); `assumed` — границы периода, чей год не встречается цифрами в `question` (`1220:1224`); `parse={ok,lost,fixed,assumed}`.

`_merge_intents` (`1262:1286`): при 1 образце — копия + `unstable=[]`, `samples=1`; иначе по каждому полю из `_INTENT_FIELDS` победитель по частоте (`_field_lead` `1251:1259`), при `distinct>1` поле в `unstable`; `parse` берётся у ближайшего образца + `unstable`/`samples`.

`same_concept_groups` (`1057:1096`): при `<2` групп — без изменений; иначе один `SELECT` из `ts_lexize(STEM_DICT, …)` и опционально `ts_lexize(ASK_SOLR_SYNONYMS_DICT, …)`; слияние групп при включении stem-множеств (`1088:1094`); ошибка `psql` → группы как есть, `0` сведённых (`1070:1071`).

## Выходы

`parse_intent` возвращает dict: `terms` (list[list[str]]), `kind`, `measure`, `want`, `about`, `period`, `period2`, `amount`, `parse` (`ok`, `lost`, `fixed`, `assumed`, после merge ещё `unstable`, `samples`).

Потребители вне участка того же файла: `parse_intent(...)` на `11854`, повтор для `prior` на `11857`, ещё вызов на `15350`.

## Обращения наружу

| Вызов | Место | Назначение |
|---|---|---|
| `ds_chat(...)` | `1230`, повтор `1238:1240` | ответ модели с JSON-разбором |
| `psql("SELECT " + ts_lexize…)` | `1069` | стеммы/синонимы написаний для слияния групп |

HTTP и прочие SQL в участке нет. `lit` — только экранирование литералов в том же SELECT.

## Переключатели

| Переменная | Чтение | Умолчание | Эффект |
|---|---|---|---|
| `ASK_INTENT_MAX_TOKENS` | `888` | `400` | `max_tokens` у `ds_chat` |
| `ASK_INTENT_SAMPLES` | `889` | `5` | верх числа прогонов |
| `ASK_INTENT_LEAD` | `890` | `3` | порог отрыва лидера для остановки цикла |
| `ASK_INTENT_MEMO` | `892` | `512` | размер памяти; `0` — выкл. |
| `ASK_INTENT_GROUPS` | `899` | `6` | макс. групп в `terms` |
| `ASK_INTENT_ALTS` | `900` | `6` | макс. написаний в группе |
| `ASK_STEM_DICT` | `903` | `search_dict_stem` | словарь `ts_lexize` |
| `ASK_SOLR_SYNONYMS` | `906` | `"0"` → False | включать ли второй `ts_lexize` |
| `ASK_SOLR_SYNONYMS_DICT` | `907` | `""` | имя словаря синонимов (пусто → syn не используется, `1062`) |

Константы допуска: `_WANT_OK` `876`, `_ABOUT_OK` `877`, `_AMOUNT_OPS` `883`, `_INTENT_FIELDS` `884`.

## Развилки

- Попадание в `_INTENT_MEMO` → немедленный return без модели (`1325:1328`).
- Нет JSON после 1–2 `ds_chat` → `RuntimeError` (`1242:1243`).
- `terms` строкой/числом → одна группа + `fixed` (`993:997`); не list/tuple → `lost` + `[]` (`998:1000`).
- Срез групп/альтернатив по бюджету → `lost`/`fixed` (`1014:1024`).
- `want` чужой → `fixed`, итог `"list"` (`1145:1149`); `about` чужой → `"data"` (`1151:1152`).
- Невалидный/перевёрнутый period(2) → `lost`, поле пустое (`1154:1210`).
- `amount.op` вне списка / нет value / between без value2 → `lost` (`1179:1184`); число без op → `op: null` (`1187:1189`).
- Год границы периода нет в цифрах вопроса → `parse.assumed` (`1220:1224`).
- Отрыв полей < `INTENT_LEAD` и samples < max → доп. прогоны (`1332:1335`).
- Расхождение полей между samples → `parse.unstable` (`1276:1277`).
- `ASK_SOLR_SYNONYMS` и непустой dict → доп. `ts_lexize` (`1062:1067`); сбой SQL → без слияния (`1070:1071`).
- Родство stem-множеств → слияние групп (`1088:1094`).

## Чего здесь нет

- Поиска по корпусу / выбора сущности / SQL-отбора записей — нет.
- Разбора дат кроме `YYYY-MM-DD` — нет (`973:986`).
- Поля `period2` в схеме `INTENT_SYS` — нет (`813:831`); нормализация `period2` в коде есть (`1194:1210`).
- Списков стоп-слов / языковых правил в коде — нет (`1028:1030`, `901:902`).
- Обращения к схеме 1С / `$metadata` — нет.
- Персистентной памяти на диск — нет (только процессный `_INTENT_MEMO` `893`).
- Валидации `kind`/`measure` по справочнику базы — нет (только строки).
