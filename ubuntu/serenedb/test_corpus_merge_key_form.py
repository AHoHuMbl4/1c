#!/usr/bin/env python3
"""Оффлайн: сторож corpus_merge — смена формы ключа vs коллапс vs удалённая дельта (п.13).

100 % старых ключей сущности + непустая новая сборка не меньше → пропуск с записью;
rewrite wave (≥90 % без exact-match, объём стейджа ≈ live) → пропуск без построчного
unmatched; частичный уход при росте + живые Recorder в витрине → коллапс, пропуск;
частичный уход + мёртвый Recorder + документ удалён → deleted_delta, пропуск;
частичный уход + мёртвый Recorder + документ жив → STOP (дефект транспорта);
частичный уход иначе или новая меньше старой → STOP.

Запуск: python3 test_corpus_merge_key_form.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
MERGE = os.path.join(ROOT, "corpus_merge.sql")
PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail))[:200] if detail else "")


def classify_entity(было, уйдёт, стало, *, recorder_alive=None, doc_alive=None,
                    mart=None, doc_changed=False):
    """Логика tmp3_merge_ent_guard + key_form + key_collapse + deleted_delta.

    (09.09) shrink: усохшая сборка сверяется с ВИТРИНОЙ прямым \gexec-гейтом
    (стало≠витрина → STOP «разошлась»); подтверждённая убыль — легитимное
    усохание источника, исключается из partial/die_unexplained membership'ом.
    Порогов-из-головы нет (п.0: «обрезанный синк» держит coverage-постчек
    в_1С/в_витрины — видимость, не число).
    """
    if было > 0 and стало < было:
        if mart is not None and mart == стало:
            return "shrink_ok"
        return "shrink_stop"
    if уйдёт > 0 and уйдёт < было:
        # (08.09) cand: «стало >= было» — равный объём тоже замена (каталог
        # 368=368 с пересозданным GUID, такт №22), а не только рост.
        if стало >= было and recorder_alive is True:
            return "collapse_ok"
        if стало >= было and recorder_alive is False and doc_alive is False:
            return "deleted_delta_ok"
        if стало >= было and recorder_alive is False and doc_alive is True:
            # (09.09) repost_delta: документ жив, но ИЗМЕНЯЛСЯ в окне (delta-маркер
            # search_changed_rows) — перепроведение сняло движения: легитимно.
            if doc_changed:
                return "repost_delta_ok"
            return "transport_stop"
        # Легитимные удаления 1С при перепроведении: без пары по refs, но доля
        # мала — порог 0.1% как в SQL (g.уйдёт > g.было * 0.001 → STOP).
        if уйдёт <= было * 0.001:
            return "source_delta_ok"
        return "partial_stop"
    if было > 0 and уйдёт == было and стало > 0 and стало >= было:
        return "key_form_ok"
    return "ok"


# (08.09) равный объём: каталог 368=368, GUID пересоздан
t("equal-volume dead guid -> deleted_delta_ok",
  classify_entity(368, 1, 368, recorder_alive=False, doc_alive=False) == "deleted_delta_ok")
t("equal-volume live guid -> transport_stop",
  classify_entity(368, 1, 368, recorder_alive=False, doc_alive=True) == "transport_stop")
t("equal-volume alive recorder -> collapse_ok",
  classify_entity(368, 1, 368, recorder_alive=True) == "collapse_ok")
t("equal-volume unknown -> partial_stop (1/368 > 0.1%)",
  classify_entity(368, 1, 368) == "partial_stop")

def is_rewrite_wave(было, стало, matched_exact, *, pct_unmatched=0.9, vol_tol=0.05):
    """Логика tmp3_merge_rewrite_wave (per-table, без имён таблиц)."""
    if было <= 0 or стало <= 0 or стало < было:
        return False
    unmatched_ratio = (было - matched_exact) / было
    vol_ratio = abs(стало - было) / было
    return unmatched_ratio >= pct_unmatched and vol_ratio <= vol_tol


def guard_count(unmatched_by_ent, exempt_ents):
    total = sum(unmatched_by_ent.values())
    exempt = sum(n for ent, n in unmatched_by_ent.items() if ent in exempt_ents)
    return total - exempt


# --- симуляция правил ---
t("key_form: 100% уход, новая больше", classify_entity(100, 100, 150) == "key_form_ok")
t("key_form: 100% уход, новая равна", classify_entity(206839, 206839, 208338) == "key_form_ok")
t("collapse: частичный уход, рост, recorder жив",
  classify_entity(75436, 23, 76000, recorder_alive=True) == "collapse_ok")
# (08.09) строгий рост больше не обязателен: равный объём при живом recorder —
# тот же коллапс-класс (замена при сохранении объёма)
t("collapse: равный объём + recorder жив -> collapse_ok",
  classify_entity(100, 50, 100, recorder_alive=True) == "collapse_ok")
t("partial_stop остаётся при усадке стало<было вне shrink",
  classify_entity(100, 50, 99) == "shrink_stop")
t("deleted_delta: мёртвый recorder, документ удалён",
  classify_entity(75436, 11, 76000, recorder_alive=False, doc_alive=False) == "deleted_delta_ok")
t("transport: мёртвый recorder, документ жив",
  classify_entity(75436, 59, 76000, recorder_alive=False, doc_alive=True) == "transport_stop")
t("collapse: мёртвый recorder без doc → delta не collapse",
  classify_entity(100, 50, 120, recorder_alive=False) == "partial_stop")
t("partial: 50 из 100 без recorder", classify_entity(100, 50, 120) == "partial_stop")
t("shrink: новая меньше", classify_entity(100, 100, 80) == "shrink_stop")
t("shrink раньше key_form", classify_entity(100, 100, 50) == "shrink_stop")
t("ok: часть совпала", classify_entity(100, 0, 100) == "ok")
t("ok: новая сущность", classify_entity(0, 0, 50) == "ok")

# --- rewrite wave (okna 31.08: full_entity sha-перезапись) ---
t("rewrite: uценка 321757 live, 15 exact, 321793 stage",
  is_rewrite_wave(321757, 321793, 15))
t("rewrite: реализация 74738 live, 488 exact, 74738 stage",
  is_rewrite_wave(74738, 74738, 488))
t("rewrite → key_form через ent_guard уйдёт=было",
  classify_entity(321757, 321757, 321793) == "key_form_ok")
t("rewrite: 89% unmatched — ниже порога",
  not is_rewrite_wave(100000, 100000, 11001))
t("rewrite: shrink — не волна",
  not is_rewrite_wave(100000, 90000, 5000))
t("rewrite: объём +10% — не волна",
  not is_rewrite_wave(100000, 110001, 5000))
t("rewrite: partial 50% — не волна (collapse/STOP отдельно)",
  not is_rewrite_wave(75436, 76000, 37718))

t("guard: key_form снимает с порога",
  guard_count({"a": 100, "b": 10}, {"a"}) == 10)
t("guard: rewrite_wave снимает с порога",
  guard_count({"a": 321757, "b": 10}, {"a"}) == 10)
t("guard: collapse тоже снимает",
  guard_count({"a": 23, "b": 10}, {"a"}) == 10)
t("guard: deleted_delta снимает",
  guard_count({"a": 11, "b": 10}, {"a"}) == 10)
t("guard: без exempt весь объём",
  guard_count({"a": 100, "b": 10}, set()) == 110)

# --- grep SQL ---
txt = open(MERGE, encoding="utf-8").read()
t("SQL: tmp3_merge_ent_counts", "CREATE OR REPLACE TABLE tmp3_merge_ent_counts AS" in txt)
t("SQL: tmp3_merge_rewrite_wave", "CREATE OR REPLACE TABLE tmp3_merge_rewrite_wave AS" in txt)
t("SQL: unmatched skips rewrite_wave",
  "NOT IN (SELECT src_table FROM tmp3_merge_rewrite_wave)" in txt)
t("SQL: ent_guard rewrite уйдёт=было",
  "WHEN w.src_table IS NOT NULL THEN w.было" in txt)
t("SQL: matched_exact INNER JOIN",
  "INNER JOIN tmp3_corpus t" in txt and "matched_exact" in txt)
t("SQL: rewrite порог 0.9", ">= 0.9" in txt)
t("SQL: rewrite объём 0.05", "<= 0.05" in txt)
t("SQL: tmp3_merge_unmatched", "CREATE OR REPLACE TABLE tmp3_merge_unmatched AS" in txt)
t("SQL: tmp3_merge_ent_guard", "CREATE OR REPLACE TABLE tmp3_merge_ent_guard AS" in txt)
t("SQL: tmp3_merge_key_form", "CREATE OR REPLACE TABLE tmp3_merge_key_form AS" in txt)
t("SQL: tmp3_merge_key_collapse", "CREATE OR REPLACE TABLE tmp3_merge_key_collapse AS" in txt)
t("SQL: tmp3_merge_key_deleted_delta", "CREATE OR REPLACE TABLE tmp3_merge_key_deleted_delta AS" in txt)
t("SQL: p_collapse_dead", "PREPARE p_collapse_dead AS" in txt)
t("SQL: p_doc_alive", "PREPARE p_doc_alive AS" in txt)
t("SQL: p_doc_alive DeletionMark (канон регистра, инцидент 09.09)",
  'lower(try_cast(d."DeletionMark" AS VARCHAR)) IS DISTINCT FROM \'true\'' in txt)
t("SQL: transport_defect STOP", "дефект транспорта" in txt)
t("SQL: repost_delta — delta-маркер объясняет снятие движений (живой стоп 19:34)",
  "tmp3_merge_repost_delta" in txt
  and "k.op = 'delta'" in txt
  and "k.src_table = t.doc_tbl" in txt
  and "(k.key_text = t.rec OR starts_with(k.key_text, t.rec || '|'))" in txt
  and "entity_repost_delta:" in txt)
t("SQL: transport STOP не трогает repost-пары",
  "WHERE NOT EXISTS (SELECT 1 FROM tmp3_merge_repost_delta r" in txt)
t("SQL: repost в die_unexplained (вектор легитимно умирает)",
  txt.count("FROM tmp3_merge_repost_delta r") >= 2)
t("SQL: repost в «частичной потере» (массовое закрытие периода, контрольная rc2)",
  txt.count("FROM tmp3_merge_repost_delta r") >= 3)
t("SQL: deleted_delta без дубля (repost ⊆ transport_defect, контрольная rc2)",
  "AND NOT EXISTS (SELECT 1 FROM tmp3_merge_repost_delta r WHERE r.src_table = c.src_table)"
  not in txt)
t("classify: мёртвый recorder + живой документ + delta-маркер -> repost_delta_ok",
  classify_entity(76214, 10, 76386, recorder_alive=False, doc_alive=True,
                  doc_changed=True) == "repost_delta_ok")
t("classify: мёртвый recorder + живой документ без маркера -> transport_stop",
  classify_entity(76214, 10, 76386, recorder_alive=False, doc_alive=True,
                  doc_changed=False) == "transport_stop")
t("SQL: query_table Recorder", 'query_table($1) q WHERE q."Recorder"' in txt)
t("SQL: Period repost anti-join", "list_contains(k.key_cols, 'Period')" in txt)
t("SQL: частичная потеря STOP", "частичная потеря объектов" in txt)
t("SQL: shrink STOP когда витрина НЕ ПОМЕЩАЕТСЯ в сборку (обрыв; дубли #N — не потеря, стоп 22:00)",
  "меньше старой И меньше витрины" in txt and "tmp3_merge_shrink" in txt
  and ")) > ' || стало" in txt and "entity_source_shrink" in txt)
t("SQL: shrink-проверка прямыми gexec-командами, без PREPARE/mart-таблицы (RR-слепота)",
  "SELECT CASE WHEN (SELECT count(DISTINCT (" in txt
  and "PREPARE p_shrink_mart" not in txt
  and "tmp3_merge_shrink_mart" not in txt)
t("SQL: счёт витрины ПО DECLARED-КЛЮЧУ (fold: объекты, не строки; стоп 21:02)",
  "list_transform(k.key_cols, c -> '\"' || c || '\"')" in txt
  and "lower(k.entity) = s.src_table" in txt)
t("SQL: STOP-gexec НЕ под ON_ERROR_STOP off (контрольная sc5: error() при off молчит)",
  txt.find("\\set ON_ERROR_STOP off", txt.find("tmp3_merge_shrink AS"))
    > txt.find("Частичный уход при росте")
  or txt.count("\\set ON_ERROR_STOP off", txt.find("tmp3_merge_shrink AS"),
               txt.find("Частичный уход при росте")) == 0)
t("SQL: имя сущности в error-литерале экранировано quote_literal",
  "|| ' || ' || quote_literal(src_table)" in txt)
t("SQL: shrink проведён в «частичную потерю» и die_unexplained (membership)",
  txt.count("FROM tmp3_merge_shrink s") >= 2)
t("SQL: чисел-порогов в shrink-блоке нет (п.0; rewrite:0.05 вне зоны)",
  "усохло больше 5" not in txt
  and txt.find("Усыхание сборки") >= 0
  and txt.find("Частичный уход при росте") > txt.find("Усыхание сборки")
  and "0.05" not in txt[txt.find("Усыхание сборки"):txt.find("Частичный уход при росте")])
t("classify: усохла по 1С (витрина=152=стало) -> shrink_ok",
  classify_entity(153, 0, 152, mart=152) == "shrink_ok")
t("classify: обрыв сборки (витрина 153 > стало 152) -> shrink_stop",
  classify_entity(153, 0, 152, mart=153) == "shrink_stop")
t("classify: витрины нет (без full) -> прежний stop",
  classify_entity(153, 0, 152) == "shrink_stop")
t("SQL: quality-ключ по сущности + чистка старья",
  "k LIKE 'entity_source_shrink:%'" in txt)
t("SQL: search_quality entity_key_form_changed",
  "entity_key_form_changed:" in txt)
t("SQL: search_quality entity_rewrite_wave",
  "entity_rewrite_wave:" in txt)
t("SQL: search_quality entity_key_collapse",
  "entity_key_collapse:" in txt)
t("SQL: search_quality entity_deleted_delta",
  "entity_deleted_delta:" in txt)
t("SQL: порог исключает key_form",
  "NOT EXISTS (SELECT 1 FROM tmp3_merge_key_form" in txt)
t("SQL: порог исключает rewrite_wave",
  "NOT EXISTS (SELECT 1 FROM tmp3_merge_rewrite_wave" in txt)
t("SQL: порог исключает key_collapse",
  "NOT EXISTS (SELECT 1 FROM tmp3_merge_key_collapse" in txt)
t("SQL: порог исключает deleted_delta",
  "NOT EXISTS (SELECT 1 FROM tmp3_merge_key_deleted_delta" in txt)
t("SQL: partial исключает collapse",
  "NOT EXISTS (SELECT 1 FROM tmp3_merge_key_collapse k WHERE k.src_table = g.src_table)" in txt)
t("SQL: partial исключает deleted_delta",
  "NOT EXISTS (SELECT 1 FROM tmp3_merge_key_deleted_delta k WHERE k.src_table = g.src_table)" in txt)
t("SQL: нет списка таблиц",
  "informationregister_ценыноменклатуры" not in txt
  and "document_реализациятмц" not in txt)

# --- допуск легитимных дельт 1С (правки по refs + удаления <= 0.1%) ---
t("SQL: edited_delta таблица есть",
  "tmp3_merge_edited_delta" in txt)
t("SQL: уйдёт вычитает правки",
  "coalesce(u.уйдёт, 0::BIGINT) - coalesce(ed.правок, 0::BIGINT)" in txt)
t("SQL: порог 0.1% в partial-stop",
  "g.уйдёт::DOUBLE > g.было * 0.001" in txt)
t("SQL: метрика source_delta пишется",
  "entity_source_delta:" in txt and "entity_edited_delta:" in txt)
t("classify: правка 10 из 76214 — дельта, не стоп",
  classify_entity(76214, 10, 76386) == "source_delta_ok")
t("classify: потеря 200 из 76214 — стоп",
  classify_entity(76214, 200, 76386) == "partial_stop")

# --- B0: partial_rebuild=0 и scaffolding search_changed_rows ---
t("SQL: partial_rebuild=0 константа", "\\set partial_rebuild 0" in txt)
t("SQL: partial_rebuild комментарий",
  "partial_rebuild=0" in txt and "отдельный пакет" in txt)

apply_py = open(os.path.join(ROOT, "..", "packet", "packet_apply.py"),
                encoding="utf-8").read()
pipe = open(os.path.join(ROOT, "pipeline.sh"), encoding="utf-8").read()

t("apply: search_changed_rows DDL",
  "CREATE TABLE IF NOT EXISTS search_changed_rows" in apply_py)
# (09.09, полная B 0c/3d) писатели — upsert с освежением ts (см. test_changed_rows_lock).
t("apply: key_text delta upsert",
  "INSERT INTO search_changed_rows" in apply_py and "delta" in apply_py
  and "FROM \"d_" in apply_py and "DO UPDATE SET ts = EXCLUDED.ts" in apply_py)
t("apply: gone deleted_gone",
  "deleted_gone" in apply_py and "будущая полная B" in apply_py)
t("apply: key_text concat |",
  "|| '|' ||" in apply_py)
t("apply: enrich LineNumber",
  "_enrich_key_cols" in apply_py and "LineNumber" in apply_py)
t("pipeline: IF NOT EXISTS search_changed_rows",
  "CREATE TABLE IF NOT EXISTS search_changed_rows" in pipe)
t("pipeline: tmp_changed_rows_keep",
  "tmp_changed_rows_keep" in pipe)
i_sync = pipe.find("python serene_sync.py")
i_rows = pipe.find("tmp_changed_rows_keep")
t("pipeline: rows snapshot до sync", i_sync >= 0 and i_rows >= 0 and i_rows < i_sync)

print("PASS %d FAIL %d" % (PASS, len(FAIL)))
sys.exit(1 if FAIL else 0)
