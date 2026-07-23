#!/usr/bin/env python3
"""
1C → KB ETL: холодный контур «второго мозга». Конфигурационно-НЕЙТРАЛЕН —
раскатывается копипастом на любую конфигурацию 1С (Бухгалтерия, ERP, УТ, …).

Что делает: читает данные из 1С СТРОГО через read-only OData-шлюз (только GET),
АВТООБНАРУЖИВАЕТ опубликованные сущности (не по захардкоженному списку!),
превращает их в markdown-таблицы и пишет в клон KB-репо (GitLab), коммитит, пушит.
Дальше oikb/kb-poll индексируют в Open WebUI → бот отвечает по данным 1С.

Универсальность (почему копипаст-раскатка работает на любом бизнесе):
- Сущности берутся из самого OData (`GET /` → все Catalog_*/Document_*), а не из
  списка под конкретную конфигурацию. Состав OData задаётся тоже автоматически
  (перебор всех справочников/документов при публикации — см. RUNBOOK §5.3).
- Пустые сущности пропускаются ($count) → в KB попадает только то, где есть данные
  (на любой конфигурации — свой набор, без служебного мусора).
- Резолв ссылок guid→наименование и чистка полей — по платформенным паттернам 1С
  (Ref_Key/Description, суффиксы _Key/_Type), не зависят от конфигурации.
- Тонкая настройка на конкретном бизнесе — через env (ETL_INCLUDE/ETL_EXCLUDE),
  НЕ правкой кода.

Инвариант: 1С только читаем (шлюз режет не-GET → 405; у ai_reader нет прав записи).

Конфиг — env:
  ETL_ODATA_BASE   URL шлюза (default http://127.0.0.1:6011)
  ETL_KB_REPO      git-URL KB-репо с токеном (обязателен)
  ETL_KB_DIR       рабочий клон (default /opt/1c-etl/kb)
  ETL_KB_SUBDIR    подпапка под выгрузку 1С (default 1c)
  ETL_INCLUDE      опц. список сущностей/имён через запятую — override автообнаружения
                   (напр. "Catalog_Номенклатура,Document_РеализацияТоваровУслуг")
  ETL_EXCLUDE      опц. список подстрок для исключения (напр. "Удалить,Служебн")
  ETL_TOP          лимит записей на сущность (default 5000)
  ETL_SKIP_EMPTY   пропускать пустые (default 1)
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
SKIP_EMPTY = os.environ.get("ETL_SKIP_EMPTY", "1") not in ("0", "false", "no", "")
INCLUDE    = [s.strip() for s in os.environ.get("ETL_INCLUDE", "").split(",") if s.strip()]
EXCLUDE    = [s.strip() for s in os.environ.get("ETL_EXCLUDE", "").split(",") if s.strip()]
SELECTED_FILE = os.environ.get("ETL_SELECTED_FILE", "/etc/1c-etl-selected.txt")
GIT_NAME   = os.environ.get("ETL_GIT_NAME", "1c-etl")
GIT_EMAIL  = os.environ.get("ETL_GIT_EMAIL", "1c-etl@unde.life")
TIMEOUT    = float(os.environ.get("ETL_TIMEOUT", "120"))

# Префиксы OData, которые тянем как «сущности верхнего уровня» (конфиг-нейтрально).
# Регистры добавляются на прод-этапе (когда включены в состав OData): просто
# допиши "InformationRegister","AccumulationRegister" — discover их подхватит.
TOP_PREFIXES = ("Catalog", "Document")

NOISE_FIELDS = {
    "odata.metadata", "odata.type", "odata.id", "odata.editLink",
    "Predefined", "PredefinedDataName", "DataVersion", "Ref_Key",
}
NULL_GUID = "00000000-0000-0000-0000-000000000000"


def log(msg):
    print(f"{datetime.now(timezone.utc):%H:%M:%S} {msg}", flush=True)


def looks_guid(s):
    return (isinstance(s, str) and len(s) == 36
            and s[8] == "-" and s[13] == "-" and s[18] == "-" and s[23] == "-")


def clean_date(s):
    if isinstance(s, str) and len(s) >= 19 and s[4] == "-" and s[7] == "-" and s[10] == "T":
        return "" if s.startswith("0001-01-01") else s[:10]
    return s


def is_noise_col(k):
    return (k in NOISE_FIELDS or k.endswith("_Type")
            or k.endswith("@navigationLinkUrl") or k.endswith("_Base64Data"))


def http_get(path, want_json=True):
    url = f"{ODATA_BASE}/{path}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if want_json else raw


def discover_entity_sets():
    """Что тянуть, по приоритету: ETL_INCLUDE → выбор из веб-UI (галочки) → авто из OData."""
    if INCLUDE:
        return INCLUDE
    if os.path.exists(SELECTED_FILE):
        sel = [l.strip() for l in open(SELECTED_FILE, encoding="utf-8") if l.strip()]
        if sel:
            log(f"источник списка: {SELECTED_FILE} (галочки из UI)")
            return sel
    doc = http_get("?$format=json")
    sets = []
    for e in doc.get("value", []):
        n = e.get("name", "")
        # верхний уровень = ровно один '_' после префикса (табличные части имеют >1)
        if n.split("_", 1)[0] in TOP_PREFIXES and n.count("_") == 1:
            sets.append(n)
    return sets


def entity_count(entity_set):
    try:
        return int(http_get(f"{urllib.parse.quote(entity_set)}/$count", want_json=False).strip())
    except Exception:
        return None   # $count не поддержан — не знаем, тянем


def fetch_entity(entity_set):
    records, skip = [], 0
    while True:
        try:
            data = http_get(f"{urllib.parse.quote(entity_set)}?" + urllib.parse.urlencode(
                {"$format": "json", "$top": str(min(1000, TOP - len(records))), "$skip": str(skip)},
                quote_via=urllib.parse.quote))
        except Exception as e:
            return records, f"{type(e).__name__}: {e}"
        batch = data.get("value", [])
        records.extend(batch)
        if len(batch) < 1000 or len(records) >= TOP:
            break
        skip += len(batch)
    return records, None


def split_set(entity_set):
    if "_" in entity_set:
        p, n = entity_set.split("_", 1)
        return p, n
    return "Catalog", entity_set


def representation(prefix, name, rec):
    if prefix == "Catalog":
        d = str(rec.get("Description") or "").strip()
        if d:
            return d
        c = str(rec.get("Code") or "").strip()
        return f"{name} {c}".strip() if c else name
    num = str(rec.get("Number") or "").strip()
    date = clean_date(str(rec.get("Date") or ""))
    return " ".join([name] + ([f"№{num}"] if num else []) + ([f"от {date}"] if date else []))


def scalar(v, refmap):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "да" if v else "нет"
    if looks_guid(v):
        return "" if v == NULL_GUID else refmap.get(v, v)
    if isinstance(v, str):
        return str(clean_date(v)).replace("|", "\\|").replace("\n", " ").strip()
    if isinstance(v, (int, float)):
        return str(v)
    return json.dumps(v, ensure_ascii=False)[:120]


def to_markdown(prefix, name, records, refmap):
    ru = "Справочник" if prefix == "Catalog" else "Документ"
    lines = [f"# {ru}: {name}", "",
             f"Источник: 1С OData `{prefix}_{name}`. Записей: {len(records)}.", ""]
    if not records:
        return "\n".join(lines + ["_Нет данных._"]) + "\n"
    cols = []
    for rec in records:
        for k in rec.keys():
            if not is_noise_col(k) and k not in cols:
                cols.append(k)
    rendered = [{c: scalar(rec.get(c), refmap) for c in cols} for rec in records]
    cols = [c for c in cols if any(row[c] for row in rendered)]   # без пустых колонок
    front = [c for c in ("Code", "Number", "Description", "Date", "Posted") if c in cols]
    cols = front + [c for c in cols if c not in front]
    header = [c[:-4] if c.endswith("_Key") else c for c in cols]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join(["---"] * len(cols)) + " |")
    for row in rendered:
        lines.append("| " + " | ".join(row[c] for c in cols) + " |")
    return "\n".join(lines) + "\n"


def git(*args, check=True):
    return subprocess.run(["git", "-C", KB_DIR, *args], check=check, capture_output=True, text=True)


def ensure_repo():
    if os.path.isdir(os.path.join(KB_DIR, ".git")):
        git("remote", "set-url", "origin", KB_REPO)
        git("fetch", "-q", "origin", check=False)
        git("reset", "-q", "--hard", "origin/main", check=False)
    else:
        subprocess.run(["git", "clone", "-q", KB_REPO, KB_DIR], check=True, capture_output=True, text=True)
    git("config", "user.name", GIT_NAME)
    git("config", "user.email", GIT_EMAIL)


def excluded(entity_set):
    return any(x.lower() in entity_set.lower() for x in EXCLUDE)


def main():
    if not KB_REPO:
        sys.exit("ETL_KB_REPO не задан")
    log(f"OData: {ODATA_BASE}  KB: {KB_DIR}/{KB_SUBDIR}")
    ensure_repo()

    sets = [s for s in discover_entity_sets() if not excluded(s)]
    log(f"обнаружено сущностей: {len(sets)}" + (" (из ETL_INCLUDE)" if INCLUDE else " (авто из OData)"))

    # Фаза 1: выгрузка непустых + карта ссылок guid→имя
    fetched, refmap, skipped = [], {}, []
    for es in sets:
        if SKIP_EMPTY:
            cnt = entity_count(es)
            if cnt == 0:
                continue
        recs, err = fetch_entity(es)
        if err:
            skipped.append(f"{es}: {err}")
            continue
        if not recs:
            continue
        prefix, name = split_set(es)
        fetched.append((prefix, name, recs))
        for rec in recs:
            ref = rec.get("Ref_Key")
            if ref and ref != NULL_GUID:
                refmap[ref] = representation(prefix, name, rec)
        log(f"  {es}: {len(recs)}")
    log(f"выгружено сущностей с данными: {len(fetched)}, карта ссылок: {len(refmap)}")

    # Фаза 2: рендер + очистка старой выгрузки (чтобы исчезнувшие сущности не висели)
    out_root = os.path.join(KB_DIR, KB_SUBDIR)
    for sub in ("catalogs", "documents"):
        d = os.path.join(out_root, sub)
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.endswith(".md"):
                    os.remove(os.path.join(d, f))
        os.makedirs(d, exist_ok=True)

    total_rec, summary = 0, []
    for prefix, name, recs in fetched:
        sub = "catalogs" if prefix == "Catalog" else "documents"
        with open(os.path.join(out_root, sub, f"{name}.md"), "w", encoding="utf-8") as f:
            f.write(to_markdown(prefix, name, recs, refmap))
        total_rec += len(recs)
        summary.append((f"{prefix}_{name}", len(recs)))

    idx = ["# Выгрузка 1С в базу знаний", "",
           f"Обновлено (UTC): {datetime.now(timezone.utc):%Y-%m-%d %H:%M}",
           f"Сущностей с данными: {len(fetched)}, записей: {total_rec}.", "",
           "| Сущность | Записей |", "| --- | --- |"]
    idx += [f"| {n} | {c} |" for n, c in sorted(summary)]
    if skipped:
        idx += ["", "## Пропущено (ошибки)", ""] + [f"- {s}" for s in skipped]
    with open(os.path.join(out_root, "_index.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(idx) + "\n")

    git("add", "-A")
    if not git("status", "--porcelain").stdout.strip():
        log("изменений нет")
        return
    msg = f"etl(1c): {len(fetched)} сущностей, {total_rec} записей [{datetime.now(timezone.utc):%Y-%m-%d %H:%M}]"
    git("commit", "-q", "-m", msg)
    push = git("push", "-q", "origin", "HEAD:main", check=False)
    if push.returncode != 0:
        log(f"PUSH FAIL: {push.stderr.strip()}")
        sys.exit(1)
    log(f"PUSHED: {msg}")


if __name__ == "__main__":
    main()
