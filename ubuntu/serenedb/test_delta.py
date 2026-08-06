#!/usr/bin/env python3
"""ОФФЛАЙН-ПРОБА дельты: разворот вытянутого объекта и соответствие имён колонок.

Без базы, без сети, без модели. Проверяются ровно те две вещи, на которых дельта
развёрнутых документов ломается молча, а не с ошибкой:

1. **Разворот.** Прямой доступ по ключу отдаёт документ ВЛОЖЕННОЙ формой — с табличной
   частью массивом внутри. Витрина хранит его развёрнутым, строка на строку. Если не
   развернуть, в таблицу уедет один ряд с массивом в ячейке вместо десятка строк — потеря
   данных ровно в тех документах, которые изменились (п. 13).

2. **Имена.** Колонки витрины приходят из движка уже безопасными (`safe_col`), а поле в
   ответе 1С зовётся как есть: `Партнер@navigationLinkUrl` в витрине становится
   `Партнер_navigationLinkUrl`. Пока значение искали прямо по имени колонки, все такие
   поля дописывались пустыми.

Запуск: python3 test_delta.py
"""
import os
import sys

os.environ.setdefault("CSV_DIR", "/tmp")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import poc_load_entity as L                       # noqa: E402

FAILS = []


def check(name, got, want):
    if got != want:
        FAILS.append("%s:\n    получено %r\n    ожидалось %r" % (name, got, want))


# Метаданные подкладываются в кэш, чтобы модуль не полез в сеть: `_load_metadata`
# выходит сразу, если кэш не пуст.
L._KEYS_CACHE.update({
    "Document_Проба": ["Ref_Key"],
    "Document_Проба_Товары": ["Ref_Key", "LineNumber"],
    "InformationRegister_Плоский": ["Изм_Key"],
})
L._PROPS_CACHE.update({
    # Свойства, объявленные САМИМ документом: реквизит шапки строкой не затирается.
    "Document_Проба": [("Ref_Key", "Edm.Guid"), ("DataVersion", "Edm.String"),
                       ("Number", "Edm.String"), ("Организация_Key", "Edm.Guid")],
    "InformationRegister_Плоский": [("Изм_Key", "Edm.Guid"), ("Значение", "Edm.String")],
})

# ── 1. Разворот вложенного документа ────────────────────────────────────────────────
doc = {
    "Ref_Key": "aaa", "DataVersion": "v2", "Number": "Д-1", "Организация_Key": "org-1",
    "Товары": [
        {"LineNumber": "1", "Номенклатура_Key": "n1", "Количество": "2"},
        {"LineNumber": "2", "Номенклатура_Key": "n2", "Количество": "5"},
    ],
}
rows, changed = L._flatten_nested([doc], "Document_Проба")
check("разворот: строк по числу строк табличной части", len(rows), 2)
check("разворот: признак разворота выставлен", changed, True)
check("разворот: реквизит шапки сохранён в каждой строке",
      [r.get("Number") for r in rows], ["Д-1", "Д-1"])
check("разворот: версия документа сохранена в каждой строке",
      [r.get("DataVersion") for r in rows], ["v2", "v2"])
check("разворот: строки различаются своими полями",
      [r.get("Номенклатура_Key") for r in rows], ["n1", "n2"])
check("разворот: массив в ячейке не остался",
      any(isinstance(v, list) for r in rows for v in r.values()), False)

# 🔴 Реквизит ШАПКИ не затирается одноимённым реквизитом строки — иначе значение шапки
# исчезает (разбор в `_flatten_nested`, [замер 29.07] 551 подменённое значение).
doc2 = {"Ref_Key": "bbb", "DataVersion": "v1", "Организация_Key": "шапка",
        "Товары": [{"LineNumber": "1", "Организация_Key": "строка"}]}
rows2, _ = L._flatten_nested([doc2], "Document_Проба")
check("разворот: реквизит шапки строкой не затирается",
      rows2[0].get("Организация_Key"), "шапка")

# Плоская сущность разворотом не трогается.
flat = [{"Изм_Key": "k1", "Значение": "1"}, {"Изм_Key": "k2", "Значение": "2"}]
rows3, changed3 = L._flatten_nested(list(flat), "InformationRegister_Плоский")
check("плоская сущность: строки не тронуты", rows3, flat)
check("плоская сущность: признак разворота НЕ выставлен", changed3, False)

# ── 2. Соответствие «колонка витрины → поле 1С» ─────────────────────────────────────
# Так его строит дельта: по самим данным, а не по догадке об именах.
new_rows = [{"Ref_Key": "aaa", "Партнер_Key": "p1",
             "Партнер@navigationLinkUrl": "Catalog_Партнеры(guid'p1')"}]
raw_by_safe = {}
for r in new_rows:
    for k in r:
        raw_by_safe.setdefault(L.safe_col(k), k)

cols = ["Ref_Key", "Партнер_Key", "Партнер_navigationLinkUrl", "Отсутствующая"]
got = [new_rows[0].get(raw_by_safe.get(c, c)) for c in cols]
check("имена: ссылка достаётся по соответствию, а не пустой",
      got, ["aaa", "p1", "Catalog_Партнеры(guid'p1')", None])

# Проба того же без соответствия — так было раньше; строка ниже фиксирует, что дефект
# был настоящим, а не выдуманным.
was = [new_rows[0].get(c) for c in cols]
check("имена: без соответствия ссылка терялась (дефект воспроизводится)",
      was, ["aaa", "p1", None, None])

check("safe_col: '@' становится '_'", L.safe_col("Партнер@navigationLinkUrl"),
      "Партнер_navigationLinkUrl")

# ── 3. Владелец табличной части ─────────────────────────────────────────────────────
# Имя даёт только кандидата; решают проверки по `$metadata`.
L._PROPS_CACHE.update({
    "Document_Проба_Товары": [("Ref_Key", "Edm.Guid"), ("LineNumber", "Edm.String"),
                              ("Номенклатура_Key", "Edm.Guid")],
    # Часть с подчёркиванием внутри имени — владелец всё равно находится.
    "Document_Проба_Виды_Цен": [("Ref_Key", "Edm.Guid"), ("LineNumber", "Edm.String")],
    # Своя версия есть — значит сама себе владелец, дельта работает напрямую.
    "Document_Сама": [("Ref_Key", "Edm.Guid"), ("DataVersion", "Edm.String")],
    # Владельца в `$metadata` нет — гипотеза не подтверждается.
    "Register_Сирота_Строки": [("Ref_Key", "Edm.Guid"), ("LineNumber", "Edm.String")],
    # Ни ключа, ни версии — не набор строк объекта.
    "InformationRegister_Плоский_RecordType": [("Период", "Edm.DateTime")],
})
L._OWNER_CACHE.clear()
check("владелец: табличная часть -> документ",
      L.owner_of("Document_Проба_Товары"), "Document_Проба")
check("владелец: имя части с подчёркиванием тоже находит владельца",
      L.owner_of("Document_Проба_Виды_Цен"), "Document_Проба")
check("владелец: у объекта со своей версией владельца нет",
      L.owner_of("Document_Сама"), None)
check("владелец: кандидата нет в $metadata — None",
      L.owner_of("Register_Сирота_Строки"), None)
check("владелец: без Ref_Key владельца не ищем",
      L.owner_of("InformationRegister_Плоский_RecordType"), None)
check("владелец: неизвестная сущность — None", L.owner_of("Совсем_Чужое"), None)

# ── 4. Объективный признак «искать нечего»: всё двоичное, текста нет ─────────────────
L._PROPS_CACHE.update({
    # Защищённое хранилище 1С: владелец + двоичные данные. Слов нет.
    "InformationRegister_Хранилище": [("Владелец", "Edm.String"), ("Владелец_Type", "Edm.String"),
                                      ("Данные_Base64Data", "Edm.String"),
                                      ("Данные_Type", "Edm.String")],
    # Блоб есть, но есть и человеческий текст — такое грузим.
    "InformationRegister_СБлобомИТекстом": [("Комментарий", "Edm.String"),
                                            ("Данные_Base64Data", "Edm.String")],
    # Двоичного нет вовсе — признак не про нас.
    "InformationRegister_БезБлоба": [("Период", "Edm.DateTime"), ("Значение", "Edm.String")],
    # Поток вместо base64 — тот же случай.
    "Catalog_Поток": [("Ref_Key", "Edm.Guid"), ("DataVersion", "Edm.String"),
                      ("Файл", "Edm.Stream")],
})
check("искать нечего: только владелец и двоичные данные",
      L.only_binary("InformationRegister_Хранилище"), True)
check("искать нечего: блоб рядом с человеческим текстом — грузим",
      L.only_binary("InformationRegister_СБлобомИТекстом"), False)
check("искать нечего: без двоичного признак не срабатывает",
      L.only_binary("InformationRegister_БезБлоба"), False)
check("искать нечего: Edm.Stream считается двоичным (техстроки за текст не идут)",
      L.only_binary("Catalog_Поток"), True)
check("искать нечего: незнакомая сущность — грузим", L.only_binary("Нет_Такой"), False)

# ── итог ────────────────────────────────────────────────────────────────────────────
if FAILS:
    print("ПРОБА НЕ ПРОШЛА, случаев с ошибкой: %d\n" % len(FAILS))
    for f in FAILS:
        print("  " + f)
    sys.exit(1)
print("проба дельты: все случаи прошли")
