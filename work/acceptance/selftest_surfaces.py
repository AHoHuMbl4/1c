#!/usr/bin/env python3
"""ЯРУС 1 САМОПРОВЕРКИ: достижимость деловой сущности ПОВЕРХНОСТЯМИ ОТБОРА — из данных,
без модели ответов, без эмбеддера веером, детерминированно.

План `docs/PLAN_ANSWER_CONTRACT.md` §4 (слепое пятно — число) и замок 17 (§10):
метрика недостижимых сущностей на каждой базе; рост — брак. Ярус 2 (живой путь
через /ask на стратифицированной выборке) — `selftest_run.py` + `selftest_check.py`.

Чем ярус 1 отличается от прогона через /ask: здесь не участвуют ни разбор вопроса
моделью, ни шаг 4 (выбор), ни модель ответов. Измеряется ПОТОЛОК системы
(полнота шага 3): сущность, которую не донесла ни одна поверхность ни одним её
словом, в кандидаты не попадает — это и есть адрес слепого пятна, бесплатно и
за минуты.

Поверхности — ровно те, что зовёт бой (`meaning_candidates`, `serene_ask.py`), теми же
продуктовыми функциями, с тем же боевым порогом `MEANING_TOP` (окружение читается из
тех же EnvironmentFile, что и юнит):

  1. `alias`    — `alias_hits`: словарь синонимов сущности (`alias_idx`, ts-запрос);
  2. `card`     — `card_hits`: слова карточки сущности (название, синонимы, величины,
                  имена реквизитов);
  3. `literal`  — шаг 2: `probe` → `match_expr` → `tables_of`, буквальное совпадение
                  слова со строками корпуса сущности (без LIMIT — как в бою);
  4. `vector`   — `near_tables`: kNN по вектору карточки/метки; достижимость = место
                  в полном порядке не дальше боевого порога; само место пишется в отчёт.

Слова сущности — из самой базы (п. 19, значений данных нет): метка
(`search_tables.label`) + ВСЕ алиасы (`search_entity_alias.aliases`). Табличная часть
засчитывается за свой документ (`search_tables.parent`) — то же правило, что у
`candidate_surfaces_bench.py`.

🔴 ЧЕСТНЫЕ ГРАНИЦЫ (как у candidate_surfaces_bench): в бою вход поверхностей богаче —
разбор модели даёт словоформы и варианты написания, а смысловая поверхность спрашивается
всем вопросом целиком. Здесь — слова самой сущности по одному. Число — ВЕРХНЯЯ оценка
слепого пятна: живой разбор может достать ещё что-то, но то, что недостижимо своими же
словами, недостижимо наверняка.

Экономия без потери смысла: лексические поверхности (чистый SQL) идут первыми, вектор —
только для ещё не достигнутых (каждое слово = один вызов эмбеддера); сущность,
достигнутая хоть раз, дальше не проверяется. Недостижимость — наоборот, доказывается
полным перебором всех слов на всех поверхностях.

Классы причин недостижимости (у каждого промаха — один основной + флаги):
  нет алиаса     — словаря для сущности нет вовсе, слово одно (метка);
  буквально пусто — ни одна лексическая поверхность слово не донесла, а вектор
                   этим часом не измерен (эмбеддер контура лёг — у боя та же картина);
  нет вектора    — у карточки/метки сущности emb IS NULL, смысловой путь закрыт;
  вектор рядом   — ближайшее место в векторном порядке в пределах 3× порога (дотянуть
                   словарём/разбором), но за боевым порогом;
  вектор далеко  — вектор есть, но ближе 3× порога сущность не поднимается ни одним словом;
  service-ошибка — отдельный список: сущность размечена service (вне набора), но имеет
                   человеческие алиасы — то есть «о таком спрашивают», а конвейер её
                   исключил. Подозрение на ошибку классификации, считается отдельно.

ДЕТЕРМИНИЗМ (замок): на неизменной базе два прогона дают одинаковый per-entity файл —
сущности и слова отсортированы, порядок векторной выдачи детерминирован движком
(расстояние, src_table), дат и случайности в файле нет.

Использование:
    ASK_BASE=ut_test python3 work/acceptance/selftest_surfaces.py [src1,src2,…]

Пишет:
  work/acceptance/runs/selftest-<база>-surfaces.jsonl        — строка на сущность;
  work/acceptance/runs/selftest-<база>-surfaces-report.json  — метрика и расклад классов.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = os.environ.get("ASK_BASE", "ut_test")
ONLY = set((sys.argv[1] or "").split(",")) if len(sys.argv) > 1 and sys.argv[1] else None
RUNS = os.path.join(ROOT, "work", "acceptance", "runs")
# Контрольный прогон по списку сущностей пишет в отдельные файлы — полный снимок
# базы им не затирается.
SFX = "-probe" if len(sys.argv) > 1 and sys.argv[1] else ""
OUT = os.path.join(RUNS, "selftest-%s-surfaces%s.jsonl" % (BASE, SFX))
REPORT = os.path.join(RUNS, "selftest-%s-surfaces%s-report.json" % (BASE, SFX))

# Полный векторный порядок: место сущности среди всех, а не «вошла ли в топ».
# Боевой порог применяем сами к этому месту — так в отчёте видна и глубина промаха.
FULL = 1000000


def load_env(path):
    """Окружение юнита читается КАК EnvironmentFile, а не через оболочку
    (тот же приём, что `step5_live.py`: `set -a; . файл` рвёт DSN с пробелами)."""
    try:
        fh = open(path, encoding="utf-8")
    except OSError:
        return
    with fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            os.environ.setdefault(k.strip(), v)


# Порядок — как `EnvironmentFile` в юните `1c-serene-ask@`: побазовый сильнее общего.
load_env("/etc/1c-serene-ask-%s.env" % BASE)
load_env("/etc/1c-serene-ask.env")
load_env("/etc/1c-embed.env")
load_env("/etc/1c-mcp-reports.env")

sys.path.insert(0, os.path.join(ROOT, "ubuntu", "serenedb"))
import serene_ask as A  # noqa: E402

TOP = A.MEANING_TOP


def business_entities():
    """Деловые сущности: всё из search_tables, кроме cls='service' (как у генератора)."""
    return [(r[0], r[1] or "") for r in A.psql(
        "SELECT t.src_table, coalesce(t.label,'') FROM %s t "
        "WHERE NOT EXISTS (SELECT 1 FROM search_entity_class c "
        "                  WHERE c.src_table = t.src_table AND c.cls = 'service') "
        "ORDER BY t.src_table" % A.TABLES)]


def aliases_of():
    """ВСЕ алиасы сущности. Таблицы может не быть вовсе (база без вики)."""
    try:
        rows = A.psql(
            "SELECT src_table, aliases FROM search_entity_alias "
            "WHERE coalesce(aliases,'') <> ''")
    except RuntimeError:
        return {}
    out = {}
    for r in rows:
        if not r or not r[0]:
            continue
        words = sorted({a.strip() for a in (r[1] or "").split(",") if a.strip()})
        if words:
            out[r[0]] = words
    return out


def parent_map():
    """Табличная часть → её документ (правило candidate_surfaces_bench)."""
    par = {}
    for r in A.psql("SELECT src_table, coalesce(nullif(parent,''), src_table) "
                    "FROM %s" % A.TABLES):
        if r and r[0]:
            par[r[0]] = r[1]
    return par


def has_emb_map():
    """У каких сущностей ЕСТЬ вектор — по отметке переписи, без похода к эмбеддеру.

    Таблица выбирается тем же правилом, что у `near_tables` (карточка предпочтительнее
    метки), но по отметке `emb_model_<таблица>` в переписи, а не по живости эмбеддера:
    вектор сущности существует и тогда, когда эмбеддер в этот час лёг. Класс
    «нет вектора» описывает ДАННЫЕ (emb IS NULL), а не доступность сервиса.
    """
    def marked(table):
        try:
            rows = A.psql("SELECT note FROM search_quality WHERE k = %s"
                          % A.lit("emb_model_" + table))
        except RuntimeError:
            return False
        return bool(rows) and (rows[0][0] or "").strip() == A.EMBED_MODEL
    src = A.CARD if marked(A.CARD) else (A.TABLES if marked(A.TABLES) else "")
    if not src:
        return "", set()
    rows = A.psql("SELECT src_table FROM %s WHERE emb IS NOT NULL" % src)
    return src, {r[0] for r in rows if r and r[0]}


def fam(t, par):
    return par.get(t) or t


def lexical_hit(word, fam_word, par):
    """Три лексические поверхности одним probe на слово. Чистый SQL, без эмбеддера."""
    try:
        exprs, _kinds = A.probe([[word]])
    except RuntimeError:
        return None                     # база молчит — прогон бессмыслен, пусть упадёт выше
    if not exprs:
        return {"alias": False, "card": False, "literal": False}
    match, _k = A.match_expr(exprs, [])
    lit = A.tables_of(match, []) if match else {}
    return {
        "alias": any(fam(t, par) == fam_word for t in A.alias_hits(exprs, TOP)),
        "card": any(fam(t, par) == fam_word for t in A.card_hits(exprs, TOP)),
        "literal": any(fam(t, par) == fam_word for t in lit),
    }


def vector_rank(word, fam_word, par):
    """Место семейства сущности в ПОЛНОМ векторном порядке по слову (1-based), None — нет."""
    try:
        order = A.near_tables(word, FULL)
    except RuntimeError:
        return None
    seen = {}
    for i, t in enumerate(order):
        f = fam(t, par)
        if f not in seen:
            seen[f] = i + 1
    return seen.get(fam_word)


def main():
    ents = business_entities()
    alias = aliases_of()
    par = parent_map()
    emb_src, with_emb = has_emb_map()
    # Живость эмбеддера — один раз на прогон (внутри кэш на 5 минут): векторная фаза
    # идёт только когда бой в этот час тоже мог бы ей пользоваться.
    vector_live = A.embed_model_live()
    if ONLY:
        ents = [e for e in ents if e[0] in ONLY]
    # Служебные с человеческими алиасами — подозрение на service-ошибку: в набор они
    # не входят, но «о таком спрашивают», а конвейер их исключил.
    business = {s for s, _ in business_entities()}
    service_suspects = sorted(s for s in alias if s not in business)

    rows = []
    for src, label in ents:
        fam_word = fam(src, par)
        words = []
        if label:
            words.append(label)
        words.extend(a for a in alias.get(src, []) if a != label)
        rec = {"base": BASE, "src_table": src, "label": label,
               "family": fam_word, "words": words,
               "has_alias": bool(alias.get(src)),
               "has_emb": fam_word in with_emb,
               "surfaces": {"alias": False, "card": False,
                            "literal": False, "vector": False},
               "first_surface": None, "first_word": None,
               "best_vector_rank": None, "reachable": False}
        # Фаза 1: лексика (SQL, дёшево). Первое попадание закрывает сущность —
        # перебор всех слов достаётся только недостигнутым: именно там картина
        # по каждой поверхности и нужна, а у достигнутых она стоила бы лишних запросов.
        for w in words:
            hit = lexical_hit(w, fam_word, par)
            if hit is None:
                raise SystemExit("база не отвечает — прогон остановлен на %s" % src)
            for k in ("alias", "card", "literal"):
                rec["surfaces"][k] = rec["surfaces"][k] or hit[k]
            if any(hit.values()):
                rec["first_surface"] = next(k for k in ("alias", "card", "literal")
                                            if hit[k])
                rec["first_word"] = w
                break
        # Фаза 2: вектор — только если лексика не достала и эмбеддер жив. Перебор всех
        # слов до первого попадания в боевой порог; лучшее место пишется в любом случае.
        if vector_live and not any(rec["surfaces"][k] for k in ("alias", "card", "literal")):
            for w in words:
                rank = vector_rank(w, fam_word, par)
                if rank is not None and (rec["best_vector_rank"] is None
                                         or rank < rec["best_vector_rank"]):
                    rec["best_vector_rank"] = rank
                if rank is not None and rank <= TOP:
                    rec["surfaces"]["vector"] = True
                    rec["first_surface"] = "vector"
                    rec["first_word"] = w
                    break
        rec["reachable"] = any(rec["surfaces"].values())
        if not rec["reachable"]:
            if not rec["has_alias"]:
                cls = "нет алиаса"
            elif not vector_live:
                cls = "буквально пусто"      # лексика пуста, вектор этим часом не измерен
            elif not rec["has_emb"]:
                cls = "нет вектора"
            elif rec["best_vector_rank"] is not None and rec["best_vector_rank"] <= 3 * TOP:
                cls = "вектор рядом"
            else:
                cls = "вектор далеко"
            rec["reason_class"] = cls
        rows.append(rec)

    os.makedirs(RUNS, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        for rec in rows:
            fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")

    total = len(rows)
    missed = [r for r in rows if not r["reachable"]]
    classes = {}
    for r in missed:
        classes[r["reason_class"]] = classes.get(r["reason_class"], 0) + 1
    per_surface = {k: sum(1 for r in rows if r["surfaces"][k])
                   for k in ("alias", "card", "literal", "vector")}
    report = {
        "base": BASE,
        "threshold_top": TOP,
        "vector_source": emb_src or None,
        "vector_live": vector_live,
        "entities": total,
        "reachable": total - len(missed),
        "unreachable": len(missed),
        "unreachable_share": (round(1.0 * len(missed) / total, 4) if total else None),
        "surface_hits": per_surface,
        "reason_classes": classes,
        "unreachable_entities": [
            {"src_table": r["src_table"], "label": r["label"],
             "reason": r["reason_class"], "best_vector_rank": r["best_vector_rank"],
             "has_alias": r["has_alias"], "has_emb": r["has_emb"]}
            for r in missed],
        "service_suspects": service_suspects,
    }
    with open(REPORT, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2, sort_keys=True)

    print("%s: деловых сущностей %d, порог топ-%d, вектор по %s, эмбеддер %s"
          % (BASE, total, TOP, emb_src or "нет отметки модели",
             "жив" if vector_live else "НЕ ОТВЕЧАЕТ — векторная фаза пропущена"))
    print("  достигнуто %d, НЕДОСТИГНУТО %d (%.1f%%) — слепое пятно"
          % (total - len(missed), len(missed),
             100.0 * len(missed) / total if total else 0.0))
    for k, v in sorted(per_surface.items()):
        print("  поверхность %-7s донесла: %d" % (k, v))
    for k, v in sorted(classes.items(), key=lambda kv: -kv[1]):
        print("  класс %-14s %d" % (k, v))
    for r in missed:
        print("  ПРОМАХ %-55s %-12s вектор=%s алиас=%s"
              % (r["src_table"], r["reason_class"],
                 r["best_vector_rank"], "да" if r["has_alias"] else "нет"))
    if service_suspects:
        print("  service-ПОДОЗРЕНИЕ (есть алиасы, но размечена service): %d"
              % len(service_suspects))
        for s in service_suspects:
            print("    %s" % s)
    print("-> %s\n-> %s" % (OUT, REPORT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
