#!/usr/bin/env python3
"""
1C → KB ETL: холодный контур «второго мозга».

Читает данные из 1С СТРОГО через read-only OData-шлюз (только GET), превращает
справочники и документы в markdown-таблицы и пишет их в клон KB-репо (GitLab),
коммитит и пушит. Дальше oikb (kb-poll) сам подхватывает новый коммит и индексирует
в Open WebUI → бот отвечает по данным 1С.

Почему так:
- Инвариант проекта: 1С только читаем. ETL ходит через :6011 (GET-only шлюз) под
  read-only пользователем ai_reader — записать в 1С физически нечем (два слоя).
- md-таблицы (а не сырой json) — потому что braine из них считает агрегаты SQL'ем
  (sqlpath-скилл) и цитирует источники; retrieval ищет по тексту.

Идемпотентность: файлы перезаписываются целиком, git коммитит только реальные диффы.
Инкремент документов по дате — TODO прода (сейчас полная перевыгрузка; на чистой/малой
базе дёшево). Список сущностей — в ENTITIES ниже (конфиг; на проде расширяется).

Конфиг — env:
  ETL_ODATA_BASE   базовый URL шлюза (default http://127.0.0.1:6011)
  ETL_KB_REPO      git-URL KB-репо с токеном (обязателен для push)
  ETL_KB_DIR       рабочий клон (default /opt/1c-etl/kb)
  ETL_KB_SUBDIR    подпапка в репо под выгрузку 1С (default 1c)
  ETL_TOP          лимит записей на сущность (default 5000)
  ETL_GIT_NAME/EMAIL  идентичность коммитов
Только stdlib.
"""
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ODATA_BASE = os.environ.get("ETL_ODATA_BASE", "http://127.0.0.1:6011").rstrip("/")
KB_REPO    = os.environ.get("ETL_KB_REPO", "")
KB_DIR     = os.environ.get("ETL_KB_DIR", "/opt/1c-etl/kb")
KB_SUBDIR  = os.environ.get("ETL_KB_SUBDIR", "1c")
TOP        = int(os.environ.get("ETL_TOP", "5000"))
GIT_NAME   = os.environ.get("ETL_GIT_NAME", "1c-etl")
GIT_EMAIL  = os.environ.get("ETL_GIT_EMAIL", "1c-etl@unde.life")
TIMEOUT    = float(os.environ.get("ETL_TIMEOUT", "120"))

# Сущности к выгрузке. Тип → список имён (без префикса Catalog_/Document_).
# На проде список расширяется под нужные разделы ERP.
ENTITIES = {
    "Catalog": [
        "Организации", "Валюты", "Номенклатура", "Контрагенты", "Склады",
        "ФизическиеЛица", "БанковскиеСчета", "Договоры", "ПодразделенияОрганизаций",
        "СтатьиДвиженияДенежныхСредств", "НоменклатурныеГруппы", "СтатьиЗатрат",
        "Валюты", "Кассы",
    ],
    "Document": [
        "РеализацияТоваровУслуг", "ПоступлениеТоваровУслуг", "ПлатежноеПоручение",
        "СписаниеСРасчетногоСчета", "ПоступлениеНаРасчетныйСчет",
        "ПриходныйКассовыйОрдер", "РасходныйКассовыйОрдер", "СчетНаОплатуПокупателю",
    ],
}

# Поля-«шум» OData, которые не несут смысла для мозга — прячем из таблиц.
NOISE_FIELDS = {
    "odata.metadata", "odata.type", "odata.id", "odata.editLink",
    "Predefined", "PredefinedDataName", "DataVersion",
}


def log(msg):
    print(f"{datetime.now(timezone.utc):%H:%M:%S} {msg}", flush=True)


def odata_get(entity_set, params):
    q = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    url = f"{ODATA_BASE}/{urllib.parse.quote(entity_set)}?{q}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_entity(prefix, name):
    """Тянет записи сущности постранично. Возвращает (records, error)."""
    entity_set = f"{prefix}_{name}"
    records, skip = [], 0
    while True:
        try:
            data = odata_get(entity_set, {
                "$format": "json", "$top": str(min(1000, TOP - len(records))), "$skip": str(skip),
            })
        except Exception as e:
            return records, f"{type(e).__name__}: {e}"
        batch = data.get("value", [])
        records.extend(batch)
        if len(batch) < 1000 or len(records) >= TOP:
            break
        skip += len(batch)
    return records, None


def scalar(v):
    """Приводит значение поля к однострочному тексту; сложное — компактный json."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "да" if v else "нет"
    if isinstance(v, (int, float, str)):
        return str(v).replace("|", "\\|").replace("\n", " ").strip()
    return json.dumps(v, ensure_ascii=False)[:120]


def to_markdown(prefix, name, records):
    ru_kind = "Справочник" if prefix == "Catalog" else "Документ"
    title = f"{ru_kind}: {name}"
    lines = [f"# {title}", "", f"Источник: 1С OData `{prefix}_{name}`. Записей: {len(records)}.", ""]
    if not records:
        lines.append("_Нет данных._")
        return "\n".join(lines) + "\n"
    # колонки = объединение полей (по порядку первого вхождения), без шума
    cols = []
    for rec in records:
        for k in rec.keys():
            if k not in NOISE_FIELDS and k not in cols:
                cols.append(k)
    # приоритет читаемых полей вперёд
    front = [c for c in ("Code", "Number", "Description", "Date", "Posted") if c in cols]
    cols = front + [c for c in cols if c not in front]
    lines.append("| " + " | ".join(cols) + " |")
    lines.append("| " + " | ".join(["---"] * len(cols)) + " |")
    for rec in records:
        lines.append("| " + " | ".join(scalar(rec.get(c)) for c in cols) + " |")
    return "\n".join(lines) + "\n"


def git(*args, check=True):
    return subprocess.run(["git", "-C", KB_DIR, *args], check=check,
                          capture_output=True, text=True)


def ensure_repo():
    if os.path.isdir(os.path.join(KB_DIR, ".git")):
        git("remote", "set-url", "origin", KB_REPO)
        git("fetch", "-q", "origin")
        git("reset", "-q", "--hard", "origin/main", check=False)
        git("pull", "-q", "--no-rebase", check=False)
    else:
        subprocess.run(["git", "clone", "-q", KB_REPO, KB_DIR], check=True,
                       capture_output=True, text=True)
    git("config", "user.name", GIT_NAME)
    git("config", "user.email", GIT_EMAIL)


def main():
    if not KB_REPO:
        sys.exit("ETL_KB_REPO не задан")
    log(f"OData: {ODATA_BASE}  KB: {KB_DIR}/{KB_SUBDIR}")
    ensure_repo()

    out_root = os.path.join(KB_DIR, KB_SUBDIR)
    total_rec, written, skipped = 0, 0, []
    summary_rows = []
    for prefix, names in ENTITIES.items():
        sub = "catalogs" if prefix == "Catalog" else "documents"
        os.makedirs(os.path.join(out_root, sub), exist_ok=True)
        for name in dict.fromkeys(names):   # dedup, порядок сохранён
            recs, err = fetch_entity(prefix, name)
            if err:
                skipped.append(f"{prefix}_{name}: {err}")
                log(f"  SKIP {prefix}_{name}: {err}")
                continue
            md = to_markdown(prefix, name, recs)
            path = os.path.join(out_root, sub, f"{name}.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(md)
            written += 1
            total_rec += len(recs)
            summary_rows.append((f"{prefix}_{name}", len(recs)))
            log(f"  OK   {prefix}_{name}: {len(recs)} записей")

    # индекс выгрузки — тоже md (попадёт в KB)
    idx = [f"# Выгрузка 1С в базу знаний", "",
           f"Обновлено (UTC): {datetime.now(timezone.utc):%Y-%m-%d %H:%M}",
           f"Файлов: {written}, всего записей: {total_rec}.", "",
           "| Сущность | Записей |", "| --- | --- |"]
    idx += [f"| {n} | {c} |" for n, c in summary_rows]
    if skipped:
        idx += ["", "## Пропущено", ""] + [f"- {s}" for s in skipped]
    with open(os.path.join(out_root, "_index.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(idx) + "\n")

    git("add", "-A")
    st = git("status", "--porcelain").stdout.strip()
    if not st:
        log("изменений нет — коммит не нужен")
        return
    msg = f"etl(1c): выгрузка {written} сущностей, {total_rec} записей [{datetime.now(timezone.utc):%Y-%m-%d %H:%M}]"
    git("commit", "-q", "-m", msg)
    push = git("push", "-q", "origin", "HEAD:main", check=False)
    if push.returncode != 0:
        log(f"PUSH FAIL: {push.stderr.strip()}")
        sys.exit(1)
    log(f"PUSHED: {msg}")


if __name__ == "__main__":
    main()
