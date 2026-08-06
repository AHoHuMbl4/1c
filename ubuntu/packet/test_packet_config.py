#!/usr/bin/env python3
"""Оффлайн-проба packet_config (config-builder) и свежести конфига в packet_server.

БЕЗ базы: обращения к витрине (packet_config._rows) подменены заготовками — тот же
приём, что test_step2 подменяет psql у serene_ask. Записи (packet_config._exec)
перехватываются, и их SQL сверяется с формой serene_sync чтением её кода. Файловая
часть настоящая: временный PACKET_BASES, атомарная перезапись, сервер на 127.0.0.1:0.

🔴 Отбор контура (перепись ∩/∖ class/force, приоритет force > class) сделан ОДНИМ
запросом в движке (п. 20 TARGET), поэтому его поведенческие случаи оффлайн не
проверяются — приоритет веток CASE доказан живым замером на ut_test (сборка
26.07.3): контур-запрос дал то же, что Python-склейка, keep=784, service=805 число
в число. Здесь проверяется ФОРМА запроса (порядок веток в тексте, условные JOIN'ы,
safe_col-выражение, ровно один contour-запрос на заход) и Python-часть — признак
only_binary по снимку $metadata: это разбор XML, а не запрос к данным, ему место
вне движка.

Чего проба не проверяет: сам SQL против живого движка (приёмы psql --csv, GRANT
настоящей роли) — это свойства живой витрины, здесь их нет.

Прогон: python3 ubuntu/packet/test_packet_config.py
Бинарь age — из PACKET_AGE_BIN, PATH или dev-копии work/packet/bin/.
"""

from __future__ import annotations

import http.client
import json
import os
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEV_AGE = os.path.join(_REPO, "work", "packet", "bin", "age", "age")
_DEV_KEYGEN = os.path.join(_REPO, "work", "packet", "bin", "age", "age-keygen")
if not os.environ.get("PACKET_AGE_BIN") and os.path.exists(_DEV_AGE):
    os.environ["PACKET_AGE_BIN"] = _DEV_AGE
    os.environ["PACKET_AGE_KEYGEN_BIN"] = _DEV_KEYGEN

import packet_crypto as C  # noqa: E402

# Контур пробы: временный каталог, env — до импорта packet_server и packet_config
# (их конфиг читается на импорте).
_TMP = tempfile.TemporaryDirectory()
ROOT = os.path.join(_TMP.name, "root")
os.makedirs(ROOT)
TOKEN = "tok-ut-config-proba"
IDENTITY = os.path.join(_TMP.name, "ut.key")
PUB = C.keygen(IDENTITY)
BASES_PATH = os.path.join(_TMP.name, "bases.json")
# Params специально не умолчательные: проба (в) проверяет, что builder сохраняет
# уже записанные params, а не подставляет свои.
PARAMS = {"page_size": 5000, "tact_seconds": 900, "chunk_mb": 16}
BASES_DOC = {
    "ut": {"token": TOKEN, "identity": IDENTITY, "note": "поле вне контракта — сохранить",
           "config": {"config_version": 3, "entities": ["Old"], "params": PARAMS}},
    "other": {"token": "tok-other", "identity": "other.key",
              "config": {"config_version": 7, "entities": ["X"],
                         "params": {"page_size": 1, "tact_seconds": 2, "chunk_mb": 3}}},
}
with open(BASES_PATH, "w", encoding="utf-8") as f:
    json.dump(BASES_DOC, f, ensure_ascii=False)

os.environ["PACKET_ROOT"] = ROOT
os.environ["PACKET_BASES"] = BASES_PATH

import packet_config as PC  # noqa: E402
import packet_server as S  # noqa: E402

# Снимок $metadata — файлом, как в бою (packet_apply пишет, config читает).
META_DIR = os.path.join(_TMP.name, "packet-meta")
PC.PACKET_META_DIR = META_DIR


def write_meta(content: str) -> None:
    d = os.path.join(META_DIR, "ut")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "$metadata"), "w", encoding="utf-8") as f:
        f.write(content)

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("ok  " if cond else "FAIL") + f"  {name}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


# --- подставная витрина ---------------------------------------------------------


class FakeDB:
    """Заготовки ответов по якорям запросов (/* tables */, /* contour */).
    contour=None — переписи нет: запрос падает, как настоящий psql на
    несуществующей base_profile."""

    def __init__(self, exist=("class", "force"), contour=()):
        self.exist = set(exist)
        self.contour = contour
        self.queries: list[str] = []
        self.execs: list[str] = []

    def rows(self, dsn: str, sql: str):
        self.queries.append(sql)
        if "/* tables */" in sql:
            out = []
            if "class" in self.exist:
                out.append(("search_entity_class",))
            if "force" in self.exist:
                out.append(("search_entity_force",))
            return out
        if "/* contour */" in sql:
            if self.contour is None:
                raise RuntimeError("relation does not exist: base_profile")
            return list(self.contour)
        raise RuntimeError(f"unexpected sql: {sql[:80]}")

    def exec(self, dsn: str, sql: str):
        self.execs.append(sql)


def run_config(db: FakeDB, dry_run: bool = False) -> int:
    real_rows, real_exec = PC._rows, PC._exec
    PC._rows, PC._exec = db.rows, db.exec
    try:
        return PC.run("ut", "fake-dsn", BASES_PATH, dry_run=dry_run)
    finally:
        PC._rows, PC._exec = real_rows, real_exec


def load_file() -> dict:
    with open(BASES_PATH, encoding="utf-8") as f:
        return json.load(f)


# --- заготовки контуров ------------------------------------------------------------

# Снимок $metadata: Catalog_Бинарь — всё двоичное; Catalog_Форсирован — тоже, но его
# возвращает вердикт 'load'; Catalog_Обычный — с человеческим текстом.
META_XML = """<edmx:Edmx xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx"><Schema>
<EntityType Name="Catalog_Бинарь"><Key><PropertyRef Name="Ref_Key"/></Key>
<Property Name="Ref_Key" Type="Edm.String"/>
<Property Name="Хранилище" Type="Edm.Stream"/>
<Property Name="Хранилище_Base64Data" Type="Edm.String"/>
</EntityType>
<EntityType Name="Catalog_Форсирован"><Key><PropertyRef Name="Ref_Key"/></Key>
<Property Name="Ref_Key" Type="Edm.String"/>
<Property Name="Данные" Type="Edm.Binary"/>
</EntityType>
<EntityType Name="Catalog_Обычный"><Key><PropertyRef Name="Ref_Key"/></Key>
<Property Name="Ref_Key" Type="Edm.String"/>
<Property Name="Наименование" Type="Edm.String"/>
</EntityType>
</Schema></edmx:Edmx>"""

# Ответ contour-запроса движка: (entity, verdict). Приоритет force > class здесь
# не играет — он вычислен движком до нас (живой замер 784/805, шапка файла).
CONTOUR = [("Catalog_Альфа", "keep"), ("Catalog_Обычный", "keep"),
           ("Catalog_Форсирован", "load"), ("Catalog_Пропуск", "skip"),
           ("Catalog_Служебный", "service"), ("Catalog_Бинарь", "keep")]

EXPECTED_ENTITIES = ["Catalog_Альфа", "Catalog_Обычный", "Catalog_Форсирован"]
EXPECTED_SKIPS = {"Catalog_Пропуск": PC.WHY_FORCE,
                  "Catalog_Служебный": PC.WHY_CLASS,
                  "Catalog_Бинарь": PC.WHY_BINARY}


def full_db() -> FakeDB:
    return FakeDB(exist=("class", "force"), contour=list(CONTOUR))


PORT = 0


def req(path: str, token=TOKEN):
    conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=30)
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    conn.request("GET", path, headers=headers)
    r = conn.getresponse()
    data = r.read()
    conn.close()
    try:
        return r.status, json.loads(data) if data else {}
    except ValueError:
        return r.status, {"_raw": data[:200].decode("utf-8", "replace")}


def main() -> int:
    global PORT

    # -- (а) ФОРМА contour-запроса (поведение приоритета доказано живым замером)
    sql_both = PC._contour_sql(has_class=True, has_force=True)
    check("а: якорь и safe_col-выражение в запросе",
          "/* contour */" in sql_both and "regexp_replace" in sql_both
          and "\\p{L}\\p{N}" in sql_both and "trim(BOTH '_'" in sql_both
          and "'c_' || k0" in sql_both)
    check("а: ветка force идёт в CASE раньше ветки class (приоритет как у serene_sync)",
          sql_both.index("'load'") < sql_both.index("'service'")
          and sql_both.index("'skip'") < sql_both.index("'service'"))
    check("а: оба JOIN при обеих таблицах",
          "LEFT JOIN search_entity_class" in sql_both
          and "LEFT JOIN search_entity_force" in sql_both)
    sql_force = PC._contour_sql(has_class=False, has_force=True)
    check("а: без таблицы class — ни ветки 'service', ни её JOIN",
          "'service'" not in sql_force and "search_entity_class" not in sql_force
          and "search_entity_force" in sql_force)
    sql_class = PC._contour_sql(has_class=True, has_force=False)
    check("а: без таблицы force — ни веток load/skip, ни её JOIN",
          "'load'" not in sql_class and "'skip'" not in sql_class
          and "search_entity_force" not in sql_class
          and "search_entity_class" in sql_class)
    sql_none = PC._contour_sql(has_class=False, has_force=False)
    check("а: без обеих — голый keep без JOIN",
          "'keep' AS verdict" in sql_none and "JOIN" not in sql_none)
    check("а: запрос существования — с фильтром по текущей базе (ловушка №25)",
          "/* tables */" in PC._TABLES_SQL
          and "database_name = current_database()" in PC._TABLES_SQL)

    # -- (а2) Python-часть: only_binary по снимку + раскладка вердиктов движка
    entities, skip = PC.compute_contour(list(CONTOUR), PC._props_by_type(META_XML))
    check("а2: контур — keep/load минус only_binary", entities == EXPECTED_ENTITIES,
          repr(entities))
    check("а2: причины по каждому исключённому", skip == EXPECTED_SKIPS, repr(skip))
    check("а2: verdict 'load' сильнее only_binary (Python-сторона признака)",
          "Catalog_Форсирован" in entities and "Catalog_Форсирован" not in skip)
    ent2, skip2 = PC.compute_contour(list(CONTOUR), None)
    check("а2: без файла снимка only_binary не применяется",
          "Catalog_Бинарь" in ent2
          and skip2 == {k: v for k, v in EXPECTED_SKIPS.items() if k != "Catalog_Бинарь"},
          repr(skip2))
    # то же на уровне _read_sources: пустой каталог снимков → props None
    real_dir = PC.PACKET_META_DIR
    PC.PACKET_META_DIR = os.path.join(_TMP.name, "packet-meta-empty")
    db_src = full_db()
    real_rows = PC._rows
    PC._rows = db_src.rows
    try:
        _rows2, props2 = PC._read_sources("fake-dsn", "ut")
    finally:
        PC._rows = real_rows
        PC.PACKET_META_DIR = real_dir
    check("а2: _read_sources без файла — props None, признак не применяется",
          props2 is None)

    # -- (а3) на заход ровно два чтения витрины: tables + contour, контур — один
    write_meta(META_XML)
    db = full_db()
    run_config(db)
    check("а3: два чтения витрины на заход, contour-запрос ровно один",
          len(db.queries) == 2
          and sum("/* contour */" in q for q in db.queries) == 1
          and sum("/* tables */" in q for q in db.queries) == 1,
          repr(db.queries)[:200])

    # -- (б) config_version растёт только при изменении; (в) чужие записи целы
    db = full_db()
    rc = run_config(db)
    doc = load_file()
    check("б: первый заход — config_version 3 → 4",
          rc == 0 and doc["ut"]["config"]["config_version"] == 4, repr(doc["ut"]["config"]))
    check("б: entities записаны итоговым списком",
          doc["ut"]["config"]["entities"] == EXPECTED_ENTITIES,
          repr(doc["ut"]["config"]["entities"]))
    check("в: params из файла сохранены, не подменены умолчаниями",
          doc["ut"]["config"]["params"] == PARAMS, repr(doc["ut"]["config"]["params"]))
    check("в: токен, identity и постороннее поле базы не тронуты",
          doc["ut"]["token"] == TOKEN and doc["ut"]["identity"] == IDENTITY
          and doc["ut"]["note"] == BASES_DOC["ut"]["note"])
    check("в: запись другой базы не тронута", doc["other"] == BASES_DOC["other"])

    before = open(BASES_PATH, "rb").read()
    rc = run_config(full_db())
    check("б: повтор без изменений — файл не переписан, версия та же",
          rc == 0 and open(BASES_PATH, "rb").read() == before
          and load_file()["ut"]["config"]["config_version"] == 4)

    # изменение: движок отдал другой вердикт (владелец снял skip) → контур вырос
    db3 = full_db()
    db3.contour = [(e, "keep" if e == "Catalog_Пропуск" else v) for e, v in CONTOUR]
    rc = run_config(db3)
    doc = load_file()
    check("б: изменение контура — config_version 4 → 5",
          rc == 0 and doc["ut"]["config"]["config_version"] == 5
          and doc["ut"]["config"]["entities"] == sorted(EXPECTED_ENTITIES + ["Catalog_Пропуск"]),
          repr(doc["ut"]["config"]))

    # -- (г) search_entity_skipped — форма записи как у serene_sync (сверка чтением кода)
    sync_src = open(os.path.join(_REPO, "ubuntu", "serenedb", "serene_sync.py"),
                    encoding="utf-8").read()
    # У serene_sync DDL собран из двух строковых литералов — сверяем по частям.
    ddl = "search_entity_skipped (entity VARCHAR, why VARCHAR, seen_at TIMESTAMP)"
    ddl_parts = ("search_entity_skipped", "(entity VARCHAR, why VARCHAR, seen_at TIMESTAMP)")
    check("г: схема таблицы дословно как у serene_sync",
          all(p in sync_src for p in ddl_parts))
    check("г: DDL записан в витрину",
          any(ddl in sql for sql in db.execs), repr(db.execs)[:200])
    written = next((sql for sql in db.execs if ddl in sql), "")
    for fragment in ("GRANT SELECT ON search_entity_skipped TO",
                     "DELETE FROM search_entity_skipped;",
                     "INSERT INTO search_entity_skipped",
                     "FROM (VALUES", "now()"):
        check(f"г: форма serene_sync — «{fragment}»",
              fragment in sync_src and fragment in written)
    check("г: GRANT той же читающей роли, что у serene_sync (serene_ro)",
          "GRANT SELECT ON search_entity_skipped TO serene_ro" in written)
    for why in (PC.WHY_FORCE, PC.WHY_CLASS, PC.WHY_BINARY):
        check(f"г: причина «{why[:30]}…» дословно из serene_sync",
              why in sync_src and why in written)
    check("г: все три исключения попали в VALUES",
          all(e in written for e in EXPECTED_SKIPS))

    # -- (е) packet_server отдаёт новый config_version без перезапуска
    if not S.init():
        print("FAIL  init() не принял файл баз")
        return 1
    srv = S.Server(("127.0.0.1", 0), S.Handler)
    PORT = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    st, r = req("/v1/agent/config?base_id=ut&config_version=0&agent_version=proba")
    check("е: стартовый конфиг — версия 5 из файла",
          st == 200 and r.get("config_version") == 5 and r.get("recipient_pubkey") == PUB,
          f"{st} {r}")
    st, r = req("/v1/agent/config?base_id=ut&config_version=5&agent_version=proba")
    check("е: версия равна — короткий ответ", st == 200 and r == {"config_version": 5},
          f"{st} {r}")

    # builder пишет версию 6 (Форсирован теряет 'load' → его забирает only_binary)
    db4 = full_db()
    db4.contour = [(e, "keep" if e == "Catalog_Форсирован" else v) for e, v in CONTOUR]
    rc = run_config(db4)
    stt = os.stat(BASES_PATH)
    os.utime(BASES_PATH, (stt.st_atime, stt.st_mtime + 2))  # mtime — гарантированно новее кэша
    st, r = req("/v1/agent/config?base_id=ut&config_version=5&agent_version=proba")
    check("е: после записи builder-а сервер отдал версию 6 БЕЗ перезапуска",
          rc == 0 and st == 200 and r.get("config_version") == 6
          and "Catalog_Форсирован" not in r.get("entities", [])
          and "Catalog_Пропуск" not in r.get("entities", []),
          f"rc={rc} {st} {r}")
    st, r = req("/v1/agent/config?base_id=ut&config_version=6&agent_version=proba")
    check("е: свежая версия равна — короткий ответ", st == 200 and r == {"config_version": 6},
          f"{st} {r}")
    st, r = req("/v1/agent/config?base_id=ut&config_version=0", token="wrong")
    check("е: авторизация по свежему файлу работает (чужой токен — 401)",
          st == 401 and r.get("error") == "unauthorized", f"{st} {r}")

    srv.shutdown()

    # -- (ё) --dry-run ничего не пишет
    before = open(BASES_PATH, "rb").read()
    db5 = full_db()
    db5.contour = [(e, "keep") for e, _v in CONTOUR]  # контур точно изменился бы
    real_rows, real_exec = PC._rows, PC._exec
    PC._rows, PC._exec = db5.rows, db5.exec
    try:
        rc = PC.main(["ut", "--dsn", "fake-dsn", "--bases", BASES_PATH, "--dry-run"])
    finally:
        PC._rows, PC._exec = real_rows, real_exec
    check("ё: dry-run — код 0, файл бит-в-бит тот же, записей в витрину нет",
          rc == 0 and open(BASES_PATH, "rb").read() == before and db5.execs == [],
          f"rc={rc} execs={len(db5.execs)}")

    # -- гигиена отказов: неизвестная база и отсутствующая перепись — отказ без записи
    before = open(BASES_PATH, "rb").read()
    real_rows = PC._rows
    PC._rows = FakeDB(contour=None).rows
    try:
        rc_empty = PC.run("ut", "fake-dsn", BASES_PATH)
    finally:
        PC._rows = real_rows
    rc_unknown = PC.run("no-such-base", "fake-dsn", BASES_PATH)
    check("гигиена: нет переписи и чужая база — отказ, файл не тронут",
          rc_empty == 2 and rc_unknown == 2 and open(BASES_PATH, "rb").read() == before,
          f"rc={rc_empty},{rc_unknown}")

    _TMP.cleanup()
    print(f"\n{'ПРОБА ЗЕЛЁНАЯ' if not FAILS else 'ПАДЕНИЯ: ' + ', '.join(FAILS)}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
