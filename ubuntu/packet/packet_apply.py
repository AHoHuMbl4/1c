#!/usr/bin/env python3
"""Apply-компонент пакетного транспорта: перевод пакетов verified → applied.

Один заход обходит все пакеты verified (всех баз либо одной — флаг/env) в порядке
seq: манифест разбирается, чанки дешифруются (age) и распаковываются (zstd) во
временный каталог, затем изменения уходят в витрину SereneDB теми же SQL-формами,
что у poc_load_entity.py (merge-дельта, полная загрузка с QUALIFY-дедупом, gone).

Атомарность пакета (контракт §8): DDL в SereneDB вне транзакций, поэтому каждая
операция повторяема без вреда, а контрактные таблицы и отметка applied пишутся
последними одной DML-транзакцией. Обрыв до неё оставляет пакет в verified, и
следующий заход повторяет его целиком.

Конфиг — env: PACKET_ROOT, PACKET_BASES (JSON баз, формат packet_server),
SERENEDB_DSN, PACKET_ZSTD_BIN, PACKET_META_DIR, PACKET_APPLY_*. Только stdlib.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

import packet_crypto as C

PACKET_ROOT = os.environ.get("PACKET_ROOT", "/var/lib/1c-packet")
PACKET_BASES = os.environ.get("PACKET_BASES", "/etc/1c-packet-bases.json")
DSN = os.environ.get("SERENEDB_DSN", "host=127.0.0.1 port=7890 user=postgres dbname=postgres")
ZSTD_BIN = os.environ.get("PACKET_ZSTD_BIN", "/usr/bin/zstd")

# Предел длины строки CSV — бюджет памяти читателя, как ETL_CSV_MAX_LINE у
# poc_load_entity (то же значение по умолчанию, то же основание).
PACKET_APPLY_CSV_MAX_LINE = int(os.environ.get("PACKET_APPLY_CSV_MAX_LINE", str(200 * 1024 * 1024)))
# Ключи на удаление идут VALUES-наборами по столько штук за запрос.
PACKET_APPLY_GONE_BATCH = int(os.environ.get("PACKET_APPLY_GONE_BATCH", "1000"))
# Читающая роль витрины для GRANT. Имя — идентификатор, приходит из окружения,
# поэтому пропускается только форма идентификатора, иначе берётся умолчание
# (то же решение, что serene_sync._ro_role).
_ro_env = os.environ.get("PACKET_APPLY_RO_ROLE", "serene_ro")
RO_ROLE = _ro_env if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", _ro_env) else "serene_ro"

# Потоки движка для сессий apply. 🔴 `SET threads` у движка ГЛОБАЛЕН, а не
# сессионен: значение переживает разрыв соединения и меняет пул ВСЕГО движка
# (живой замер 12.08: после apply с «SET threads=4» новая psql-сессия видит 4
# при --cpu_threads=160 в conf; на okna-1 об это встал precheck сборки —
# «пул исполнителей движка = 4»). Поэтому умолчание — НЕ ВМЕШИВАТЬСЯ (0):
# apply не смеет молча переконфигурировать движок под собой. Память полного
# merge держит не эта ручка, а предел строки read_csv (_csv_source: buffer
# читателя = 16 × maximum_line_size) и спилл на диск (WorkingDirectory юнита
# движка). Явный PACKET_APPLY_THREADS>0 остаётся как ручка, но помните: он
# перекроит пул глобально до рестарта движка.
# Доки: Configuration › Pragmas › Threads (SET threads = N).
try:
    APPLY_THREADS = int(os.environ.get("PACKET_APPLY_THREADS", "").strip() or "0")
except ValueError:
    APPLY_THREADS = 0
_SQL_PREFIX = ("SET threads=%d;\n" % APPLY_THREADS) if APPLY_THREADS > 0 else ""

# Чанки со служебными именами хранятся без вставки «.csv» (контракт §2).
_SERVICE_CHUNKS = ("metadata", "gone", "index", "log")
# Режим файла — по магии, а не по конфигу (пилот без age-слоя 06.08); те же
# константы, что у packet_server, — apply самостоятельный процесс, форма
# хранения общая по контракту (шапка packet_server.py).
_AGE_MAGIC = b"age-encryption.org/"
_ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
# Операции сущности, при которых данные заливаются чанками (остальные — gone_only).
_DATA_OPS = ("full", "full_entity", "delta")

BASES: dict = {}


def _log(msg: str) -> None:
    sys.stderr.write("apply %s\n" % msg)


def _chunk_filenames(name: str) -> tuple[str, str]:
    """Имена хранения чанка: (age-форма, plain-форма) — как у packet_server."""
    base = name + (".zst" if name in _SERVICE_CHUNKS else ".csv.zst")
    return base + ".age", base


def _sniff(path: str) -> str:
    """Режим файла по магии: 'age' | 'zstd' | 'other' (как у packet_server)."""
    try:
        with open(path, "rb") as f:
            head = f.read(len(_AGE_MAGIC))
    except OSError:
        return "other"
    if head.startswith(_AGE_MAGIC):
        return "age"
    if head.startswith(_ZSTD_MAGIC):
        return "zstd"
    return "other"


def _read_json(path: str, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write_json_atomic(path: str, obj) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)


def _base_dir(base_id: str) -> str:
    return os.path.join(PACKET_ROOT, "inbox", base_id)


def _pkg_dir(base_id: str, pkg_id: str) -> str:
    return os.path.join(_base_dir(base_id), pkg_id)


def _base_state(base_id: str) -> dict:
    st = _read_json(os.path.join(_base_dir(base_id), "state.json"), None)
    if not isinstance(st, dict):
        st = {"last_applied_seq": 0, "packages": {}}
    st.setdefault("last_applied_seq", 0)
    st.setdefault("packages", {})
    return st


def _set_pkg_state(base_id: str, pkg_id: str, state: str, error, seq=None) -> None:
    # Дубль записи packet_server._set_pkg_state: apply — самостоятельный процесс,
    # форма state.json общая по контракту хранения (шапка packet_server.py).
    pkg_dir = _pkg_dir(base_id, pkg_id)
    st = _read_json(os.path.join(pkg_dir, "state.json"), None)
    if not isinstance(st, dict):
        st = {}
    st["state"] = state
    st["error"] = error
    if seq is not None:
        st["seq"] = seq
    st["updated_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _write_json_atomic(os.path.join(pkg_dir, "state.json"), st)
    bs = _base_state(base_id)
    bs["packages"][pkg_id] = {"state": state, "error": error}
    _write_json_atomic(os.path.join(_base_dir(base_id), "state.json"), bs)


def _mark_applied(base_id: str, pkg_id: str, seq: int) -> None:
    _set_pkg_state(base_id, pkg_id, "applied", None, seq=seq)
    bs = _base_state(base_id)
    bs["last_applied_seq"] = max(int(bs.get("last_applied_seq", 0)), seq)
    _write_json_atomic(os.path.join(_base_dir(base_id), "state.json"), bs)


def safe_col(name) -> str:
    # Та же функция, что poc_load_entity.safe_col: имя колонки для любого алфавита.
    out = []
    for ch in str(name):
        out.append(ch if (ch.isalnum() or ch == "_") else "_")
    s = "".join(out).strip("_")
    if not s or s[0].isdigit():
        s = "c_" + s
    return s


def _lit(v) -> str:
    return "'" + str(v).replace("'", "''") + "'"


def _psql(sql: str) -> None:
    # SQL идёт через stdin, а не аргументом -c: у argv жёсткий предел, и длинный
    # список ключей его перекрывает (разбор у poc_load_entity._psql_rows).
    # Префикс SET threads — только здесь: у скалярных чтений тег «SET» ложился
    # бы в stdout и ломал разбор числа (проба 12.08: «SET\n2» вместо «2»).
    p = subprocess.run(["psql", DSN, "-v", "ON_ERROR_STOP=1", "-f", "-"],
                       input=_SQL_PREFIX + sql, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip()[:300])


def _psql_scalar(sql: str) -> str:
    p = subprocess.run(["psql", DSN, "-tA", "-v", "ON_ERROR_STOP=1", "-f", "-"],
                       input=sql, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip()[:300])
    return p.stdout.strip()


def _psql_col(sql: str) -> list[str]:
    """Одна колонка строками; пустой ответ — пустой список."""
    out = _psql_scalar(sql)
    return [ln for ln in out.splitlines() if ln.strip()] if out else []


class Quarantine(RuntimeError):
    # Сбой, после которого пакет уходит в quarantined с кодом причины.
    pass


# --- разбор пакета ------------------------------------------------------------


def _decrypt_chunks(base_id: str, pkg_id: str, manifest: dict, tmp: str) -> dict:
    """Все чанки пакета: (age →) zstd → открытый файл во временном каталоге.

    Режим каждого чанка — по магии: age расшифровывается, plain zst идёт сразу
    в распаковку (пилот без age-слоя 06.08)."""
    identity = (BASES.get(base_id) or {}).get("identity", "")
    out = {}
    for e in manifest["chunks"]:
        name = e["name"]
        enc = None
        for fn in _chunk_filenames(name):
            p = os.path.join(_pkg_dir(base_id, pkg_id), fn)
            if os.path.exists(p):
                enc = p
                break
        if enc is None:
            # Пакет verified, а чанка на диске нет — необратимая порча пакета
            # (кейс K5, 11.08: чанк log со старым именем log.csv.zst клал базу в
            # вечный «failed» и останавливал применение всех поздних пакетов
            # базы каждый такт таймера). Карантин, а не вечный повтор.
            raise Quarantine("chunk_missing:%s" % name)
        dec = os.path.join(tmp, name + ".zst")
        if _sniff(enc) == "age":
            C.decrypt_file(enc, dec, identity)
        else:
            dec = enc
        plain = os.path.join(tmp, name + (".csv" if name not in _SERVICE_CHUNKS else ""))
        with open(plain, "wb") as fh:
            p = subprocess.run([ZSTD_BIN, "-d", "-q", "-c", dec],
                               stdout=fh, stderr=subprocess.PIPE)
        if p.returncode != 0:
            raise RuntimeError("zstd: %s" % p.stderr.decode("utf-8", "replace").strip()[:200])
        os.chmod(plain, 0o644)
        out[name] = plain
    return out


def _longest_record_data(data: bytes) -> int:
    """Длина самой длинной ЛОГИЧЕСКОЙ записи CSV в байтах данных.

    Запись может занимать много физических строк: поле в кавычках вправе
    содержать переводы строк (живой случай okna-1 15.08, пакет 000002,
    chunk-00148: 3 записи по 1,4–2,6 МБ — base64-картинки, разбитые на строки
    по ~280 Б; самая длинная физическая строка 280 Б, и счёт по ней занижал
    предел в тысячи раз — read_csv падал «CSV Error on Line: 1»).

    Автомат кавычек: экранирование по контракту — удвоение (quote='"',
    escape='"'), а пара удвоенных кавычек даёт два переключения состояния, то
    есть не меняет его, — поэтому хватает простого переключателя на каждой
    кавычке, разбирать пары не нужно. Работа идёт на скорости bytes.split, не
    питоньего цикла по байтам. Кавычки в данных редки (поля с GUID/числами/
    датами агент не кавычит), так что цикл по сегментам короткий; файл без
    кавычек уходит в быстрый путь.
    """
    if b'"' not in data:
        return max((len(l) for l in data.split(b"\n")), default=0)
    longest = 0
    cur = 0          # длина текущей записи с учётом уже пройденных сегментов
    in_q = False     # состояние: внутри ли кавычек
    segs = data.split(b'"')
    for idx, seg in enumerate(segs):
        if idx:
            cur += 1             # сама кавычка — часть записи
            in_q = not in_q
        if in_q:
            cur += len(seg)      # переводы строк внутри кавычек — тоже запись
        else:
            lines = seg.split(b"\n")
            cur += len(lines[0])
            for ln in lines[1:]:
                longest = max(longest, cur)
                cur = len(ln)
    return max(longest, cur)


def _longest_records(paths: list[str]) -> dict:
    """По каждому файлу — самая длинная запись (0 — измерить не удалось)."""
    out = {}
    for p in paths:
        try:
            with open(p, "rb") as f:
                out[p] = _longest_record_data(f.read())
        except OSError:
            out[p] = 0
    return out


def _longest_record(paths: list[str]) -> int:
    """Длина самой длинной ЛОГИЧЕСКОЙ записи CSV в файлах, в байтах.
    0 — измерить не удалось. См. _longest_record_data.
    """
    return max(_longest_records(paths).values(), default=0)


def _csv_source(paths: list[str]) -> str:
    """SELECT-источник read_csv с опциями контракта poc_load_entity (header,
    all_varchar, quote/escape, предел строки). Несколько чанков — UNION ALL.

    🔴 Предел строки прижимается к крупнейшему файлу источника: buffer_size
    читателя по умолчанию = 16 × maximum_line_size (доки: Data import and
    export › Csv › Overview, parameters), и потолок 200 МиБ означал разовую
    аллокацию 3,1 ГиБ — на юните с memory_limit 6 ГиБ это валило apply целиком
    (живой случай okna-1 12.08, пакет 000002: 83 падения подряд, витрина пуста).
    Строка CSV не бывает длиннее своего файла, поэтому фактический размер чанка
    — честная верхняя граница без знания базы; env-потолок остаётся страховкой
    от гигантского чанка.

    🔴 Одного размера файла НЕДОСТАТОЧНО, и это стоило простоя (klient-1 14.08,
    пакет 000003). Буфер берётся НА КАЖДЫЙ read_csv в UNION ALL, поэтому сущность
    из 18 чанков по 32 МБ просит 16 × 32 МБ × 18 = 9,2 ГБ при memory_limit
    9,3 ГиБ — «could not allocate block» на каждом такте, 40 минут падений.
    Мельче резать чанки бесполезно: общий буфер = 16 × объём сущности и от
    нарезки не зависит (мельче чанк — больше читателей). Поэтому предел
    считается по ФАКТУ, самой длинной ЗАПИСИ (а не физической строке — запись
    может быть разорвана переводами строк внутри кавычек, см. _longest_record):
    в том же чанке 6668 записей на 32 МБ, то есть ~4,8 КБ на запись —
    завышение было в тысячи раз.

    🔴 Предел — ПОФАЙЛОВЫЙ, у каждого read_csv свой (klient-1 16.08, пакет
    000011). Один чанк с записью 22,4 МБ (base64 большого файла) среди 25
    обычных давал общий предел 23,5 МБ × 16 × 26 читателей = 9,1 ГиБ — снова
    «could not allocate block» при memory_limit 9,3 ГиБ. Гигантская запись —
    свойство ОДНОГО файла, поэтому предел считается для каждого файла
    отдельно: 16 × (23,5 МБ + 25 × 1 МиБ) ≈ 0,8 ГиБ. У чанков без гигантов
    поведение прежнее: предел = max(запись + 4096, 1 МиБ), прижатый к размеру
    файла и env-потолку."""
    # Пол 1 МиБ на файл — чтобы не уйти ниже разумного (умолчание движка 2 МБ).
    # Ошибка в меньшую сторону безопасна: читатель скажет «строка не влезла»
    # громко, и потолок поднимается ключом PACKET_APPLY_CSV_MAX_LINE. Ошибка в
    # большую — то самое падение по памяти.
    caps: dict = {}
    recs = _longest_records([p for p in paths if os.path.exists(p)])
    for p in paths:
        cap = PACKET_APPLY_CSV_MAX_LINE
        try:
            cap = min(cap, os.path.getsize(p) + 4096)
        except OSError:
            pass
        rec = recs.get(p, 0)
        if rec > 0:
            cap = min(cap, max(rec + 4096, 1 << 20))
        caps[p] = cap
    if 16 * sum(caps.values()) > (1 << 30):
        _log("apply ВНИМАНИЕ буфер читателей ~%.1f ГиБ (%d чанков, сумма пределов "
             "%d Б) — возможен отказ по памяти движка"
             % (16 * sum(caps.values()) / (1 << 30), len(paths), sum(caps.values())))
    reads = []
    for p in paths:
        opts = ("header=true, all_varchar=true, quote='\"', escape='\"', "
                "maximum_line_size=%d" % caps[p])
        reads.append("SELECT * FROM read_csv(%s, %s)" % (_lit(p), opts))
    if len(reads) == 1:
        return reads[0]
    return "(" + " UNION ALL ".join(reads) + ")"


def _csv_header(path: str) -> list[str]:
    """Заголовок CSV-чанка (состав колонок дельты — он уже в safe_col-форме)."""
    with open(path, newline="", encoding="utf-8") as f:
        return next(csv.reader(f))


def _full_sql(table: str, src: str) -> str:
    # Формы poc_load_entity.load_entity: DROP + CREATE, затем GRANT читающей роли.
    #
    # 🔴 Дедуп ведётся по ПОЛНОЙ строке (DISTINCT), а не по объявленному ключу.
    # Объявленный ключ — ЗАЯВКА источника, а не факт: когда данные ей не отвечают,
    # `QUALIFY row_number() PARTITION BY ключ` оставлял ОДНУ строку на ключ и
    # молча выбрасывал остальные — п.13 (молчаливая потеря = дефект).
    # Живой случай klient-1 14.08: 1С объявляет у регистра-НАБОРА
    # AccumulationRegister_X ключ (Recorder, Recorder_Type) — одна запись на
    # документ, а сами строки лежат вложенным списком RecordSet. Агент список
    # разворачивает в плоские строки (правильно), но ключ в манифесте остаётся
    # родительский и строку уже не различает. Итог на первой загрузке клиента:
    # ДвиженияНоменклатураДоходыРасходы 141 586 строк → 8 783 в витрине (−93,8%),
    # ВыручкаИСебестоимостьПродаж 117 049 → 19 572 (−83%), и НИ СЛОВА в журнале.
    # Тот же механизм резал и по урезанному ключу (okna-1 12.08: от ключа
    # оставался один LineNumber — строки разных документов сливались в одну).
    # DISTINCT снимает ровно то, ради чего дедуп и заводился: полные повторы
    # строк от перекрытия страниц и повторной отправки чанка. Строки, у которых
    # ключ общий, а содержимое разное, — это данные, и они остаются.
    # Уникальность ключа проверяется после загрузки (_check_key_identifies).
    wrapped = src if src.startswith("(") else None
    select = ("SELECT DISTINCT * FROM %s AS q" % wrapped) if wrapped \
        else src.replace("SELECT *", "SELECT DISTINCT *", 1)
    return ('DROP TABLE IF EXISTS "%s";\n'
            'CREATE TABLE "%s" AS %s;\n'
            'GRANT SELECT ON "%s" TO %s;\n' % (table, table, select, table, RO_ROLE))


def _check_key_identifies(base_id: str, pkg_id: str, table: str,
                          key_cols: list[str]) -> None:
    # Различает ли объявленный ключ строки витрины; не различает — строка в
    # журнал. Не карантин и не отказ: строки на месте (дедуп идёт по полной
    # строке). Смысл записи в том, что слияние дельты по неразличающему ключу
    # трогает не ту строку, а группировка по нему даёт не то число, — и это
    # видно до того, как по таблице ответят клиенту.
    if not key_cols:
        return
    part = ", ".join('"%s"' % k for k in key_cols)
    # Проверка наблюдательная: её отказ не смеет валить загрузку, которая уже
    # прошла. Составной ключ считается как строковое значение — форма живьём
    # проверена на klient-1 14.08 (count(DISTINCT (Recorder, Recorder_Type))
    # вернул 19 572 из 117 049 строк).
    try:
        dup = int(_psql_scalar('SELECT count(*) - count(DISTINCT (%s)) FROM "%s"'
                               % (part, table)))
    except (RuntimeError, TypeError, ValueError) as e:
        _log("base=%s pkg=%s entity=%s проверку ключа снять не удалось: %s"
             % (base_id, pkg_id, table, e))
        return
    if dup > 0:
        _log("apply ВНИМАНИЕ base=%s pkg=%s entity=%s объявленный ключ %s НЕ различает "
             "строки: %d строк делят ключ с другими (строки сохранены, дельта по "
             "такому ключу тронет не ту строку)" % (base_id, pkg_id, table, key_cols, dup))


def _check_rows_landed(base_id: str, pkg_id: str, table: str, rows_sent) -> None:
    # Прислано против легло. Сеть общая: ловит убыль любой природы, а не только
    # ту, что уже знаем. После дедупа по полной строке единственная законная
    # причина убыли — полные повторы строк (перекрытие страниц 1С, повторная
    # отправка чанка), поэтому число называется тем, что оно есть, без тревоги.
    if not isinstance(rows_sent, int) or rows_sent <= 0:
        return
    try:
        got = int(_psql_scalar('SELECT count(*) FROM "%s"' % table))
    except (RuntimeError, TypeError, ValueError):
        return
    if got < rows_sent:
        d = rows_sent - got
        _log("base=%s pkg=%s entity=%s прислано %d, легло %d, снято полных повторов "
             "%d (%.1f%%)" % (base_id, pkg_id, table, rows_sent, got, d,
                              100.0 * d / rows_sent))


def _contour_gap(entities: list, tables: set, upto) -> list:
    """Сущности контура, которые агент уже прошёл, а в витрине их нет.

    Чистая функция — вся работа с файлами снаружи. `upto` — сущность, которую
    агент читает сейчас (из progress.json): контур он обходит в том же порядке,
    в каком получил, поэтому всё до неё либо доехало, либо потеряно. `upto=None`
    — считаем по всему контуру (загрузка закончена или хода не знаем).
    """
    names = [e for e in entities if isinstance(e, str)]
    if upto is not None and upto in names:
        names = names[:names.index(upto)]
    return [e for e in names if safe_col(e).lower() not in tables]


def _check_contour_arrived(base_id: str) -> None:
    # 🔴 Что НЕ доехало, приёмник не знает ниоткуда: секции skipped в манифестах
    # klient-1 нет ни в одной порции (замер 15.08 — `skipped=null` во всех
    # десяти), а сам агент пропуски классифицирует и пишет только в свой журнал
    # — диагностический артефакт, не контракт. Живой случай того же дня:
    # AccumulationRegister_СебестоимостьТоваров_RecordType агент читал 6,7 часа,
    # прочитал 638 330 строк и выбросил по OutOfMemoryException; ещё 2 121
    # сущность отпала по правам (HTTP 401). Приёмнику не сказали ни о чём.
    # Поэтому счёт снимается здесь: контур известен (config.entities базы),
    # витрина известна, разница — на виду.
    # Пустая сущность от потерянной так не отличается (агент про «строк 0» тоже
    # молчит), поэтому строка журнала называет вещи как есть, без тревоги.
    rec = BASES.get(base_id) or {}
    entities = ((rec.get("config") or {}).get("entities")) or []
    if not entities:
        return
    try:
        tables = set(_psql_col("SELECT table_name FROM duckdb_tables() "
                               "WHERE database_name = current_database()"))
    except RuntimeError as e:
        _log("base=%s: контур сверить не удалось: %s" % (base_id, str(e)[:150]))
        return
    prog = _read_json(os.path.join(_base_dir(base_id), "progress.json"), {})
    upto = prog.get("entity") if isinstance(prog, dict) else None
    gap = _contour_gap(entities, tables, upto)
    if not gap:
        return
    _log("base=%s контур %d, пройдено до %s, НЕ В ВИТРИНЕ %d (пусто или потеряно): %s%s"
         % (base_id, len(entities), upto or "конца", len(gap), ", ".join(gap[:10]),
            " …" if len(gap) > 10 else ""))


def _check_mix_versions(table: str) -> None:
    # Инвариант К3 (контракт §9): одна версия на Ref_Key, запрос как у
    # poc_load_entity.load_entity_delta. Нарушение — карантин, дельту не льём.
    n = _psql_scalar('SELECT count(*) FROM (SELECT "Ref_Key" FROM "%s" '
                     'GROUP BY 1 HAVING count(DISTINCT "DataVersion")>1)' % table)
    if n and int(n) > 0:
        raise Quarantine("mix_versions")


def _delta_delete_clause(table: str, mart_cols: list) -> str:
    """DELETE дельты: Ref_Key если есть, иначе Recorder+LineNumber регистра."""
    nat = [c for c in ("Recorder", "LineNumber", "Recorder_Type") if c in mart_cols]
    if "Ref_Key" in mart_cols:
        return ('DELETE FROM "%s" WHERE "Ref_Key" IN '
                '(SELECT "Ref_Key" FROM "d_%s");\n' % (table, table))
    if "Recorder" in nat and "LineNumber" in nat:
        eqs = " AND ".join(
            '"%s"."%s" IS NOT DISTINCT FROM "d_%s"."%s"' % (table, c, table, c)
            for c in nat)
        return ('DELETE FROM "%s" WHERE EXISTS (SELECT 1 FROM "d_%s" '
                'WHERE %s);\n' % (table, table, eqs))
    raise Quarantine("delta_without_key")


def _delta_sql(table: str, src: str, header: list[str]) -> str:
    # Источник истины формы — poc_load_entity.load_entity_delta (строки ~707-736):
    # состав колонок дельты выравнивается по ВИТРИНЕ (её список из duckdb_columns),
    # недостающие — пустые строки ('' — так пишет эталон: _cell(None)). Свой вариант
    # merge не заводим: надстройка поверх эталонной формы, не перепись (HOW_NOT_TO §3.40).
    # TEMP-таблица → DELETE по Ref_Key → INSERT. Повтор безопасен: DELETE снимает
    # прошлую порцию тех же ключей.
    mart_cols = [r for r in _psql_col(
        'SELECT column_name FROM duckdb_columns() WHERE table_name=%s '
        "AND database_name = current_database() "  # ловушка №25: иначе видны чужие базы
        'ORDER BY column_index' % _lit(table))]
    if not mart_cols:
        raise Quarantine("delta_without_table")
    extra = [c for c in header if c not in mart_cols]
    if extra:
        # Поле появилось в 1С, а полная перезаливка сущности ещё не была: значения
        # этих колонок до ближайшей full_entity не попадают (поведение эталона то же) —
        # но молчать о несовпадении схем нельзя (п. 13).
        _log("delta %s: колонки чанка вне витрины (ждут full_entity): %s"
             % (table, ",".join(extra)))
    sel = ", ".join('"%s"' % c if c in header else "''" for c in mart_cols)
    cols = ", ".join('"%s"' % c for c in mart_cols)
    # 🔴 ЧАНК ДЕЛЬТЫ ДЕДУПЛИЦИРУЕТСЯ ПО ПОЛНОЙ СТРОКЕ (DISTINCT), как и полная
    # загрузка с 14.08 — НЕ по Ref_Key. Агент шлёт дельту документа развёрнутой:
    # по строке на каждую строку табличной части, и строки РАЗЛИЧАЮТСЯ
    # (LineNumber, ТМЦ_Key, Цена — замер на живых чанках okna 15.08, пакет
    # 000033). Дедуп по Ref_Key оставлял одну произвольную строку документа, а
    # DELETE снимал все — каждый затронутый дельтой документ схлопывался до
    # одной строки (okna, document_реализациятмц: −1346 строк против присланного,
    # нашлось сверкой repair-key-dedup.py; журнал молчал, т.к. счёт
    # «прислано/легло» есть только у full). Полные копии (шапка без полей ТЧ)
    # DISTINCT снимает — случай 14.08 «79 копий» закрыт тем же. Повтор пакета
    # по-прежнему безопасен: DELETE снимает прошлую порцию тех же ключей.
    # Регистр без Ref_Key: естественный ключ строки — Recorder+LineNumber
    # (+ Recorder_Type, если колонка есть). DELETE по отсутствующему Ref_Key
    # на 26.07.3 падает; full_entity этот путь не берёт, дельта регистра — да.
    if "Ref_Key" not in mart_cols:
        nat = [c for c in ("Recorder", "LineNumber", "Recorder_Type") if c in mart_cols]
        _log("delta %s: нет Ref_Key, слияние по %s" % (table, nat))
    delete_sql = _delta_delete_clause(table, mart_cols)
    return ('CREATE OR REPLACE TEMP TABLE "d_%s" AS '
            'SELECT DISTINCT * FROM (%s) AS q;\n'
            '%s'
            'INSERT INTO "%s" (%s) SELECT %s FROM "d_%s";\n'
            % (table, src, delete_sql, table, cols, sel, table))


def _apply_gone(path: str, changed_tables: set) -> int:
    """gone.csv (колонки entity,ref_key): DELETE по ключам пачками."""
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if not rows:
        return 0
    header = [h.strip() for h in rows[0]]
    try:
        ie, ir = header.index("entity"), header.index("ref_key")
        data = rows[1:]
    except ValueError:
        ie, ir, data = 0, 1, rows[1:]
    keys: dict[str, list[str]] = {}
    for r in data:
        if len(r) > max(ie, ir):
            keys.setdefault(r[ie], []).append(r[ir])
    total = 0
    for entity, ks in keys.items():
        table = safe_col(entity).lower()
        changed_tables.add(table)
        for i in range(0, len(ks), PACKET_APPLY_GONE_BATCH):
            vals = ",".join("(%s)" % _lit(k) for k in ks[i:i + PACKET_APPLY_GONE_BATCH])
            _psql('DELETE FROM "%s" WHERE "Ref_Key" IN '
                  '(SELECT k FROM (VALUES %s) AS g(k));' % (table, vals))
        total += len(ks)
    return total


# Каталог снимков $metadata: <PACKET_META_DIR>/<base_id>/$metadata. Снимок едет
# ФАЙЛОМ, а не таблицей: read_text в corpus_build.sql читает и локальные файлы,
# поэтому боевой скрипт сборки работает без правок — build.sh получает
# ETL_ODATA_BASE=<каталог>/<base_id>, и движок читает <каталог>/<base_id>/$metadata
# (решение владельца 06.08: боевые скрипты сборки не трогаем).
PACKET_META_DIR = os.environ.get("PACKET_META_DIR", "/var/lib/serenedb/packet-meta")


def _apply_metadata(base_id: str, manifest: dict, path: str) -> None:
    """Снимок $metadata из чанка — в файл <PACKET_META_DIR>/<base_id>/$metadata.

    Атомарно: temp+os.replace в том же каталоге — движок в любой момент видит
    либо старый снимок целиком, либо новый. Файл читает процесс движка (в бою
    apply идёт под root), поэтому владелец и режим выставляются явно."""
    base_dir = os.path.join(PACKET_META_DIR, base_id)
    os.makedirs(base_dir, exist_ok=True)
    os.chmod(base_dir, 0o755)
    fd, tmp = tempfile.mkstemp(dir=base_dir, prefix=".metadata-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as out, open(path, "rb") as src:
            shutil.copyfileobj(src, out)
        os.chmod(tmp, 0o644)
        if os.geteuid() == 0:
            try:
                shutil.chown(tmp, user="serenedb", group="serenedb")
            except LookupError as e:
                raise RuntimeError(f"chown serenedb:serenedb: {e}")
        os.replace(tmp, os.path.join(base_dir, "$metadata"))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _touch_first_data(base_id: str) -> None:
    """Отметка «данные применены» для path-юнита первой сборки слоя
    (1c-serene-firstbuild@<base>): до данных слой собирать нечего — сторож
    «пустой корпус» пайплайна оборвёт такт, — поэтому первую сборку и таймер
    свежести включает этот сигнал, а не появление снимка $metadata."""
    try:
        fd = os.open(os.path.join(PACKET_META_DIR, base_id, ".first-data"),
                     os.O_CREAT | os.O_WRONLY, 0o644)
        os.close(fd)
    except OSError as e:
        _log("base=%s: отметка .first-data не записана (%s) — данные применены, "
             "первую сборку слоя запустить вручную" % (base_id, e))


def _apply_skipped(base_id: str, skipped: list) -> None:
    """Список сущностей, которые агент не смог прочитать (права/RLS/сбой 1С) —
    в <PACKET_META_DIR>/<base_id>/skipped.json, атомарно. Машиночитаемая
    видимость п. 13 TARGET на сервере: по этому файлу отличим «таблица пуста»
    от «закрыто правами в базе-источнике»."""
    base_dir = os.path.join(PACKET_META_DIR, base_id)
    os.makedirs(base_dir, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=base_dir, prefix=".skipped-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump({"updated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                       "entities": skipped}, out, ensure_ascii=False, indent=1)
        os.chmod(tmp, 0o644)
        os.replace(tmp, os.path.join(base_dir, "skipped.json"))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _safe_log_name(s) -> str:
    # Имя файла из недоверенной строки манифеста: только [A-Za-z0-9_.-], «..»
    # свёрнуто (как _valid_id у packet_server), ведущие точки срезаны — итог не
    # может ни выйти за каталог, ни стать скрытым файлом.
    s = re.sub(r"[^A-Za-z0-9_.-]", "_", str(s))
    while ".." in s:
        s = s.replace("..", "__")
    return s.lstrip(".")


def _apply_log(base_id: str, pkg_id: str, section: dict, path: str) -> str:
    """Служебный чанк `log` (лог установщика/агента) — в файл
    <PACKET_META_DIR>/<base_id>/logs/<pkg>[_<source>].log, атомарно.

    Секция манифеста: {"source": <имя исходного файла на агенте>, "chunks": ["log"]}.
    Имя собирается из pkg_id и source через _safe_log_name; коллизия (повторная
    посылка того же лога) прежний файл НЕ затирает — добавляется суффикс -2, -3…
    Возвращает имя записанного файла."""
    logs_dir = os.path.join(PACKET_META_DIR, base_id, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    name = _safe_log_name(pkg_id)
    src = _safe_log_name(section.get("source") or "")
    if src:
        name += "_" + src
    # Исходное имя уже с «.log» — второе расширение не добавляем, суффикс
    # коллизии ставим перед расширением.
    if name.endswith(".log"):
        name = name[:-4]
    dst = os.path.join(logs_dir, name + ".log")
    n = 1
    while os.path.exists(dst):
        n += 1
        dst = os.path.join(logs_dir, "%s-%d.log" % (name, n))
    fd, tmp = tempfile.mkstemp(dir=logs_dir, prefix=".log-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as out, open(path, "rb") as src_f:
            shutil.copyfileobj(src_f, out)
        os.chmod(tmp, 0o644)
        os.replace(tmp, dst)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return os.path.basename(dst)


# --- контрактные таблицы (форма serene_sync) -----------------------------------


def _ensure_contract_tables() -> None:
    # DDL вне транзакции (движок так и работает), IF NOT EXISTS — повторяемо.
    _psql("CREATE TABLE IF NOT EXISTS search_changed_sources (src_table VARCHAR);\n"
          "GRANT SELECT ON search_changed_sources TO %s;\n"
          "CREATE TABLE IF NOT EXISTS base_profile "
          "(entity TEXT, rows BIGINT, problem TEXT, key_props TEXT);\n"
          "CREATE TABLE IF NOT EXISTS search_quality (k TEXT, v BIGINT, note TEXT);\n"
          % RO_ROLE)


def _contract_tx(changed_tables: set, profile: list[dict]) -> None:
    """Последний шаг пакета: контрактные таблицы одной DML-транзакцией.

    🔴 Отметки изменённого ДОПИСЫВАЮТСЯ, а не переписываются, — и apply объявляет
    список полным (`changed_sources_ok = 1`). Прежняя форма повторяла serene_sync
    (перепись целиком) — но у синка сборка идёт следом в том же процессе и съедает
    список сразу, а на юните apply живёт своим таймером: второй пакет затирал
    отметки первого до того, как их видела сборка. Флаг полноты на пакетном
    контуре не ставил никто вовсе (его писал только синк, которого на юните нет
    по построению) — путь «пересобрать изменившееся» был мёртв на каждом юните
    (живой замер okna 14.08: витрина 9632, корпус 8199, такты завершались +0).
    Полнота списка здесь — свойство устройства: apply — единственный писатель
    витрины на пакетном контуре, и каждая применённая таблица попадает в
    `changed_tables`. Потребляет отметки сборка (`corpus_merge`) — только те,
    что пересобрала.
    """
    sql = ["BEGIN;"]
    if changed_tables:
        vals = ",".join("(%s)" % _lit(t) for t in sorted(changed_tables))
        sql.append("INSERT INTO search_changed_sources "
                   "SELECT t FROM (VALUES %s) AS s(t) "
                   "WHERE t NOT IN (SELECT src_table FROM search_changed_sources);" % vals)
        sql.append("DELETE FROM search_quality WHERE k='changed_sources_ok';")
        sql.append("INSERT INTO search_quality VALUES ('changed_sources_ok', 1, "
                   "'список полон: витрину на пакетном контуре пишет только apply');")
    if profile:
        # Форма serene_sync: число строк обновляется, ключ и примечание сущности
        # в профиле сохраняются; вставляются только новые для профиля сущности.
        pairs = ",".join("(%s,%d)" % (_lit(p["entity"]), p["rows"]) for p in profile)
        sql.append("UPDATE base_profile SET rows = v.n FROM (VALUES %s) AS v(e, n) "
                   "WHERE base_profile.entity = v.e;" % pairs)
        vals = ",".join("(%s,%d,%s,%s)" % (_lit(p["entity"]), p["rows"], _lit(""),
                                           _lit(",".join(p.get("key") or [])))
                        for p in profile)
        sql.append("INSERT INTO base_profile SELECT * FROM (VALUES %s) AS v(e, n, p, k) "
                   "WHERE NOT EXISTS (SELECT 1 FROM base_profile WHERE base_profile.entity = v.e);"
                   % vals)
    sql.append("DELETE FROM search_quality WHERE k='mart_changed_ts';")
    sql.append("INSERT INTO search_quality VALUES ('mart_changed_ts', epoch(now())::BIGINT, "
               "'витрина менялась (пакетный apply)');")
    sql.append("COMMIT;")
    _psql("\n".join(sql) + "\n")


# --- план и применение ----------------------------------------------------------


def _plan(base_id: str, pkg_id: str, m: dict) -> list[str]:
    lines = ["пакет %s/%s seq=%d kind=%s" % (base_id, pkg_id, m.get("seq"), m.get("kind"))]
    for ent in m.get("entities") or []:
        lines.append("  сущность %s op=%s rows=%s чанки=%s ключ=%s"
                     % (ent.get("name"), ent.get("op"), ent.get("rows"),
                        ",".join(ent.get("chunks") or []), ",".join(ent.get("key") or [])))
    if (m.get("gone") or {}).get("chunks"):
        lines.append("  gone: чанки=%s" % ",".join(m["gone"].get("chunks") or []))
    if (m.get("metadata") or {}).get("included"):
        lines.append("  metadata: fingerprint=%s" % (m["metadata"].get("fingerprint") or ""))
    lines.append("  контрактная транзакция: search_changed_sources + base_profile + "
                 "search_quality.mart_changed_ts")
    return lines


def apply_package(base_id: str, pkg_id: str, m: dict, dry_run: bool) -> str:
    """Один пакет. Итог: applied / quarantined / failed (остался verified) / planned."""
    seq = m["seq"]
    if dry_run:
        for line in _plan(base_id, pkg_id, m):
            print(line)
        return "planned"
    tmp = tempfile.mkdtemp(prefix="packet-apply-")
    os.chmod(tmp, 0o755)  # каталог читает процесс движка (read_csv)
    try:
        try:
            files = _decrypt_chunks(base_id, pkg_id, m, tmp)
            for s in m.get("skipped") or []:
                if isinstance(s, dict):
                    _log("base=%s pkg=%s SKIPPED entity=%s: %s"
                         % (base_id, pkg_id, s.get("entity"), str(s.get("error"))[:200]))
            # Пустой список — тоже сигнал: «пропущенных больше нет» (права в 1С
            # починили) — skipped.json обязан очиститься, а не висеть вчерашним
            # (замер 11.08, ЗУП: 693 no_read_right закрылись, файл застыл).
            if isinstance(m.get("skipped"), list):
                _apply_skipped(base_id, m["skipped"])
            if (m.get("metadata") or {}).get("included") and "metadata" in files:
                _apply_metadata(base_id, m, files["metadata"])
                _log("base=%s pkg=%s metadata записан" % (base_id, pkg_id))
            if (m.get("log") or {}).get("chunks") and "log" in files:
                log_name = _apply_log(base_id, pkg_id, m["log"], files["log"])
                _log("base=%s pkg=%s log сохранён: %s" % (base_id, pkg_id, log_name))
            changed_tables: set = set()
            profile: list[dict] = []
            for ent in m.get("entities") or []:
                op = ent.get("op")
                if op not in _DATA_OPS:
                    continue
                table = safe_col(ent.get("name", "")).lower()
                chunk_paths = [files[c] for c in ent.get("chunks") or [] if c in files]
                src = _csv_source(chunk_paths)
                if op == "delta":
                    hdr = _csv_header(chunk_paths[0])
                    merge = _delta_sql(table, src, hdr)  # здесь отсутствие таблицы — карантин
                    _check_mix_versions(table)
                    _psql(merge)
                else:
                    key_cols = [safe_col(k) for k in ent.get("key") or []]
                    # 🔴 Ключ дедупликации — только из колонок, которые в чанке
                    # есть. У расчётных регистров OData не отдаёт Recorder
                    # (живой случай okna-1 12.08: CalculationRegister_*_RecordType
                    # объявил ключ [Recorder, LineNumber, Recorder_Type], в CSV —
                    # RegistrationPeriod и пр.; QUALIFY по отсутствующей колонке
                    # валил весь пакет). Пустое пересечение = штатная форма
                    # «без ключа» (DISTINCT), потеря формы видна в журнале.
                    if key_cols and chunk_paths:
                        have = set(_csv_header(chunk_paths[0]))
                        kept = [k for k in key_cols if k in have]
                        if kept != key_cols:
                            _log("base=%s pkg=%s entity=%s ключ урезан по колонкам "
                                 "чанка: %s -> %s" % (base_id, pkg_id, table,
                                                      key_cols, kept or "DISTINCT"))
                            key_cols = kept
                    _psql(_full_sql(table, src))
                    _check_key_identifies(base_id, pkg_id, table, key_cols)
                    _check_rows_landed(base_id, pkg_id, table, ent.get("rows"))
                changed_tables.add(table)
                profile.append({"entity": ent.get("name"), "key": ent.get("key") or [],
                                "table": table})
                _log("base=%s pkg=%s entity=%s op=%s" % (base_id, pkg_id, table, op))
            if (m.get("gone") or {}).get("chunks") and "gone" in files:
                n_gone = _apply_gone(files["gone"], changed_tables)
                _log("base=%s pkg=%s gone=%d" % (base_id, pkg_id, n_gone))
            # Число строк профиля — фактическое, после всех операций пакета
            # (gone снимает строки уже после merge, как у serene_sync).
            for p in profile:
                n = _psql_scalar('SELECT count(*) FROM "%s"' % p["table"])
                p["rows"] = int(n) if n.isdigit() else 0
        except Quarantine as q:
            _set_pkg_state(base_id, pkg_id, "quarantined", str(q), seq=seq)
            _log("QUARANTINE base=%s pkg=%s code=%s" % (base_id, pkg_id, q))
            return "quarantined"
        except (RuntimeError, C.PacketCryptoError, OSError, KeyError) as e:
            # Сбой до контрактной транзакции: пакет остаётся verified, повтор
            # следующего захода безопасен (все операции повторяемы).
            _log("ОШИБКА base=%s pkg=%s: %s — пакет остался verified" % (base_id, pkg_id, str(e)[:300]))
            return "failed"
        try:
            _ensure_contract_tables()
            _contract_tx(changed_tables, profile)
        except RuntimeError as e:
            _set_pkg_state(base_id, pkg_id, "quarantined",
                           "contract_tx_failed: %s" % str(e)[:200], seq=seq)
            _log("QUARANTINE base=%s pkg=%s code=contract_tx_failed" % (base_id, pkg_id))
            return "quarantined"
        _mark_applied(base_id, pkg_id, seq)
        _log("APPLIED base=%s pkg=%s seq=%d" % (base_id, pkg_id, seq))
        if profile:
            _touch_first_data(base_id)
        return "applied"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _iter_verified(only_base: str | None) -> list[tuple[str, str, dict]]:
    """(base_id, pkg_id, manifest) всех пакетов в состоянии verified, по seq."""
    inbox = os.path.join(PACKET_ROOT, "inbox")
    out = []
    if not os.path.isdir(inbox):
        return out
    for base_id in sorted(os.listdir(inbox)):
        if only_base and base_id != only_base:
            continue
        bdir = _base_dir(base_id)
        if not os.path.isdir(bdir):
            continue
        last_applied = _base_state(base_id)["last_applied_seq"]
        for pkg_id in sorted(os.listdir(bdir)):
            pdir = os.path.join(bdir, pkg_id)
            if not os.path.isdir(pdir):
                continue
            st = _read_json(os.path.join(pdir, "state.json"), {})
            if st.get("state") != "verified":
                continue
            m = _read_json(os.path.join(pdir, "manifest.json"), None)
            if not isinstance(m, dict) or not isinstance(m.get("seq"), int):
                _log("base=%s pkg=%s: манифест не читается, пропуск" % (base_id, pkg_id))
                continue
            if m["seq"] <= last_applied:
                _log("base=%s pkg=%s seq=%d <= last_applied=%d, пропуск"
                     % (base_id, pkg_id, m["seq"], last_applied))
                continue
            out.append((base_id, pkg_id, m))
    out.sort(key=lambda t: (t[0], t[2]["seq"]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="apply-компонент пакетного транспорта")
    ap.add_argument("--base", default=os.environ.get("PACKET_APPLY_BASE") or None,
                    help="обработать только эту базу")
    ap.add_argument("--dry-run", action="store_true",
                    default=os.environ.get("PACKET_APPLY_DRY_RUN", "") not in ("", "0"),
                    help="разобрать и напечатать план без обращений к витрине")
    args = ap.parse_args()

    if not os.path.exists(PACKET_BASES):
        sys.stderr.write("FATAL: файл баз %s не найден, задайте PACKET_BASES\n" % PACKET_BASES)
        return 2
    try:
        with open(PACKET_BASES, encoding="utf-8") as f:
            BASES.update(json.load(f))
    except (OSError, ValueError) as e:
        sys.stderr.write("FATAL: файл баз %s не читается: %s\n" % (PACKET_BASES, e))
        return 2

    todo = _iter_verified(args.base)
    if not todo:
        _log("пакетов verified нет — нечего применять")
        return 0
    bad = 0
    skip_bases: set = set()
    touched: list = []
    for base_id, pkg_id, m in todo:
        if base_id in skip_bases:
            continue
        res = apply_package(base_id, pkg_id, m, args.dry_run)
        if base_id not in touched:
            touched.append(base_id)
        if res in ("failed", "quarantined"):
            bad += 1
            # Поздние пакеты этой базы строятся поверх ранних — после сбоя
            # база дальше не идёт, остальные базы продолжаются.
            skip_bases.add(base_id)
    if not args.dry_run:
        for base_id in touched:
            _check_contour_arrived(base_id)
    return 3 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
