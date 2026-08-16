#!/usr/bin/env python3
"""
MCP-сервер поверх `serene_ask` — даёт OpenClaw-боту инструмент `ask_1c`, которым он
черпает факты из данных 1С через SereneDB.

Роль в интеграции:
  человек → OpenClaw-бот (перефразирует вопрос по вики) → инструмент `ask_1c` (этот
  сервер) → `serene_ask` (поиск в SereneDB, счёт в базе, гейт чисел) → бот формулирует
  живой ответ → verify-плагин сверяет числа → клиент

🔴 ЗАЧЕМ НОВЫЙ МОСТ, А НЕ ПРАВКА СТАРОГО. Прежний `mcp_braine.py` обращается к
`BRAINE_URL` (:8090) — к слою braine, выведенному из продукта; [замер 30.07] порт не
слушает вовсе, и бот на любой вопрос отвечал «сервер 1С не отвечает». Это второй раз
класс `HOW_NOT_TO §2.14`: вывод компонента не закончен, пока не убраны его связки.
Решение владельца 30.07: новый мост, бот отвечает по второй базе (`ut_test`).

🔴 ЧЕМ ЭТОТ МОСТ ОТЛИЧАЕТСЯ ПО СУТИ: он пробрасывает `focus`, `measure` и `context`,
поэтому работает ЦЕПОЧКА, а не один выстрел:

  вопрос → (если сомнение) уточнение о сущности → уточнение о величине → ответ

Без этих полей уточнение оставалось односторонним: сервис спрашивал, а ответ человека
вернуть было нечем. Порядок задан п. 21 контракта: ответ → уточняющий вопрос → отказ.

`context` — предыдущий разговор; его ведёт OpenClaw. Он используется ТОЛЬКО арбитром
внутри `serene_ask` (выбор между готовыми ответами) и в отбор данных не попадает.

Транспорт — Streamable HTTP (официальный MCP SDK `mcp`, FastMCP). Конфиг — env:
  ASK_URL    (default http://127.0.0.1:8099)
  ASK_TOKEN  (Bearer сервиса ответов; обязателен, иначе он вернёт 401)
  MCP_HOST/MCP_PORT (default 127.0.0.1:6016)
  MCP_TOKEN  (Bearer этого сервера; без него сервис НЕ стартует)
"""
import json
import os
import sys
import urllib.error
import urllib.request

from mcp.server.fastmcp import FastMCP

ASK_URL = os.environ.get("ASK_URL", "http://127.0.0.1:8099").rstrip("/")
ASK_TOKEN = os.environ.get("ASK_TOKEN", "")
MCP_HOST = os.environ.get("MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.environ.get("MCP_PORT", "6016"))
TIMEOUT = float(os.environ.get("ASK_TIMEOUT", "300"))

mcp = FastMCP("serene-ask", host=MCP_HOST, port=MCP_PORT)

# --- авторизация MCP -------------------------------------------------------------
# Сервис отдаёт данные 1С, поэтому дверь закрыта. fail-closed: пустой токен не должен
# молча открывать доступ — эту ошибку мы уже проходили на шлюзе и на прежнем мосте.
# Заголовок передаётся штатным механизмом OpenClaw: `mcp.servers.<имя>.headers`.
MCP_TOKEN = os.environ.get("MCP_TOKEN", "")


def _serve_with_auth(mcp_obj):
    import uvicorn
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse

    if not MCP_TOKEN:
        sys.stderr.write("FATAL: MCP_TOKEN не задан — сервис отдавал бы данные 1С без "
                         "авторизации. Задайте токен в окружении.\n")
        raise SystemExit(2)

    class Auth(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            if request.headers.get("authorization", "") != "Bearer " + MCP_TOKEN:
                return JSONResponse({"error": "unauthorized"}, status_code=401)
            return await call_next(request)

    app = mcp_obj.streamable_http_app()
    app.add_middleware(Auth)
    uvicorn.run(app, host=MCP_HOST, port=MCP_PORT, log_level="warning")


def _ask(question, focus=None, measure=None, context=None, prior=None):
    payload = {"question": question}
    if focus:
        payload["focus"] = focus
    if measure:
        payload["measure"] = measure
    if context:
        payload["context"] = context
    if prior:
        payload["prior"] = prior
    req = urllib.request.Request(ASK_URL + "/ask",
                                 data=json.dumps(payload).encode("utf-8"),
                                 method="POST")
    req.add_header("Content-Type", "application/json")
    if ASK_TOKEN:
        req.add_header("Authorization", "Bearer " + ASK_TOKEN)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


# Тексты, которые видит человек, вынесены в окружение: продукт коробочный, и язык
# клиента заранее неизвестен. Описание инструмента (его читает модель бота) — на
# английском и без предметных примеров, чтобы не тянуть ответ в конкретный язык и не
# предполагать торговую конфигурацию.
# 🔴 ЭТИ СТРОКИ ЧИТАЕТ МОДЕЛЬ, А НЕ ЧЕЛОВЕК, поэтому они по-английски. Русский текст
# здесь тянул модель ответить клиенту по-русски — ровно в той ветке, ради которой ниже по
# стеку заведён `clarify_text` на языке вопроса.
NO_DATA_REPLY = os.environ.get(
    "MCP_NO_DATA_REPLY", "[NO DATA] Tell the user there is no such data.")
ERROR_REPLY = os.environ.get(
    "MCP_ERROR_REPLY", "[SERVICE ERROR: {detail}] Tell the user the data is unavailable.")
CLARIFY_LABEL = os.environ.get("MCP_CLARIFY_LABEL", "OPTIONS")
# 🔴 ГЕЙТ ОТКЛОНИЛ ФОРМУЛИРОВКУ — НО ЧИСЛА ПОСЧИТАНЫ И ВЕРНЫ. Сервис отдаёт их
# `kind=figures` отдельным полем и прямо говорит в коде: «отдаём структурой, а не своей
# прозой… вызывающий формулирует сам». Мост этого не делал: он брал `text`, а там в этой
# ветке лежит ОТКАЗ (`ASK_TOTAL_TEXT` пуст по умолчанию и не задан ни в одном env, значит
# `refuse_text(question)`). Итог — отказ при наличии посчитанных данных, то есть ровно
# то, что п. 21 контракта называет дефектом, а не осторожностью.
FIGURES_HINT = os.environ.get(
    "MCP_FIGURES_HINT",
    "[FIGURES] The wording of the draft answer could not be verified, so it was dropped. "
    "The values below ARE computed by the database and are correct. Answer the user's "
    "question from these values, copying the digits exactly. Do not add any other figure.")
# Что не поместилось/не дошло (п. 13: молчаливая потеря = дефект). До 02.08 поле
# `partial` мост не передавал вовсе, хотя `API_ASK` обещает его как видимое клиенту.
PARTIAL_HINT = os.environ.get(
    "MCP_PARTIAL_HINT",
    "[PARTIAL] Not everything was taken into account. Tell the user so in one short "
    "sentence, using the figures below as they are.")
CLARIFY_HINT = os.environ.get(
    "MCP_CLARIFY_HINT",
    "[CLARIFICATION NEEDED] Put the question below to the user in your own words with the "
    "options.")


def _num(v):
    """Число для модели: без хвоста .0 у целых — иначе гейт сверяет «1236800.0» с «1236800».

    Формат тот же, что у `serene_ask` в его собственных подстановках, и это не косметика:
    белый список гейта собирается из ТЕКСТА, который ушёл боту.
    """
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return str(v)
    return "%d" % v if float(v) == int(v) else "%.2f" % v


def _kv_block(label, d):
    """Плоский блок `ключ=значение` — только для PARTIAL-потерь, не для figures.

    Для `kind=figures` плоский словарь не используется (аудит §8–§9, план §5): иначе вторая модель
    снова назначала бы ролям смысл. Числа ответа уходят семантическими ролями атома.
    """
    if not isinstance(d, dict):
        return ""
    lines = ["- %s=%s" % (k, _num(v)) for k, v in d.items() if v is not None]
    return ("%s:\n%s" % (label, "\n".join(lines))) if lines else ""


def _period_line(period):
    if not isinstance(period, dict):
        return ""
    pf = str(period.get("from") or "").strip()
    pt = str(period.get("to") or "").strip()
    if not pf and not pt:
        return ""
    window = "%s..%s" % (pf, pt) if (pf and pt) else (pf or pt)
    origin = str(period.get("origin") or "").strip()
    return ("%s %s" % (window, origin)).strip() if origin else window


def _atom_roles_block(atom, index=None):
    """Текст для модели бота из атома: явные семантические роли, не плоский словарь.

    Роли фиксированы кодом (operation / value / measure_label / unit / period /
    completeness / proof_status). Переназначить «число к чужой подписи» нечем.
    """
    if not isinstance(atom, dict):
        return ""
    lines = []
    if index is not None:
        lines.append("pair=p%d" % index)
    op = atom.get("operation")
    if op:
        lines.append("operation=%s" % op)
    # value — display_value (уже отформатирован строителем), иначе exact
    val = atom.get("display_value")
    if val is None and atom.get("exact_value") is not None:
        val = _num(atom["exact_value"])
    if val is not None:
        lines.append("value=%s" % val)
    lab = (atom.get("measure_label") or "").strip()
    if lab:
        lines.append("measure_label=%s" % lab)
    unit = atom.get("unit_or_currency")
    if unit is not None and str(unit).strip():
        lines.append("unit=%s" % unit)
    per = _period_line(atom.get("period"))
    if per:
        lines.append("period=%s" % per)
    excl = atom.get("excluded")
    if isinstance(excl, dict) and excl:
        bits = ["%s=%s" % (k, _num(v)) for k, v in excl.items() if v is not None]
        if bits:
            lines.append("excluded=%s" % ",".join(bits))
    comp = atom.get("completeness")
    if isinstance(comp, dict) and comp.get("missing") is not None:
        lines.append("completeness_missing=%s" % _num(comp["missing"]))
    ps = atom.get("proof_status")
    if ps:
        lines.append("proof_status=%s" % ps)
    return "\n".join("- %s" % x for x in lines)


def _atoms_of(data):
    """Атомы ответа: список `atoms`, иначе одиночный `atom`, иначе пусто."""
    atoms = data.get("atoms")
    if isinstance(atoms, list) and atoms:
        return [a for a in atoms if isinstance(a, dict)]
    one = data.get("atom")
    if isinstance(one, dict):
        return [one]
    return []


# Поля атома/варианта, которые МОЖНО показать модели бота. Внутренний `src` и
# `interpretation_id` — доказательство пересчёта; в текст инструмента не входят
# (иначе снова утекут имена таблиц, как до 03.08).
_ATOM_PUBLIC = (
    "operation", "exact_value", "display_value", "measure_label",
    "unit_or_currency", "period", "filters", "grain", "axis", "form",
    "completeness", "freshness", "excluded", "proof_status",
)
_OPT_PUBLIC = ("label", "entity_label", "hint", "found", "distinct_by")


def _atoms_public(atoms):
    out = []
    for a in atoms or []:
        if not isinstance(a, dict):
            continue
        out.append({k: a[k] for k in _ATOM_PUBLIC if k in a and a[k] is not None})
    return out


def _options_public(opts):
    out = []
    for o in opts or []:
        if not isinstance(o, dict):
            continue
        pub = {k: o[k] for k in _OPT_PUBLIC
               if o.get(k) is not None and o.get(k) != ""}
        if pub:
            out.append(pub)
    return out


def _atom_json_block(atoms=None, options=None):
    """JSON для гейта/канала: семантические роли без внутренних имён таблиц."""
    payload = {"atoms": _atoms_public(atoms), "options": _options_public(options)}
    if not payload["atoms"] and not payload["options"]:
        return ""
    return "ATOM_JSON:\n" + json.dumps(payload, ensure_ascii=False, default=str)


def _figures_for_bot(data):
    """Блок figures для модели: семантические роли атомов (+ JSON атомов/options).

    Плоский `figures` key=value здесь не отдаётся — иначе вторая модель снова
    переназначает роли (аудит §8). Старые маркеры протокола сохраняются.
    """
    atoms = _atoms_of(data)
    parts = []
    if atoms:
        blocks = []
        for i, a in enumerate(atoms):
            b = _atom_roles_block(a, index=i if len(atoms) > 1 else None)
            if b:
                blocks.append(b)
        if blocks:
            parts.append("FIGURES:\n" + "\n\n".join(blocks))
        # Структура проходит JSON-ом: канал/гейт читают роли, не пересобирают пары.
        block = _atom_json_block(atoms, data.get("options"))
        if block:
            parts.append(block)
    return "\n\n".join(parts)


# 🔴 ВНУТРЕННИЙ СЧЁТЧИК, НАЗВАННЫЙ СВОИМ ИМЕНЕМ, СТАНОВИТСЯ ЛОЖЬЮ О ДАННЫХ (`F251`).
#
# Сервис кладёт в `partial` пометки о своих отсечках: сколько ВИДОВ ЗАПИСЕЙ рассмотрено,
# сколько показано модели, что не понято в вопросе. Мост отдавал их боту как есть —
# `reranked_of=1502`, `reranked=60`, — и модель, не зная, что это, выдумывала смысл.
# `[замер 04.08, живой прогон через бота]` на вопросе «покажи три самые крупные продажи»
# человек получил: «это выборка из 60 записей, а всего в базе 1 502 документа». Оба числа
# ЗАКОННЫ (они пришли ответом инструмента, гейт их пропустил верно), но сказанное про них
# — неправда: 1 502 это число видов записей, рассмотренных отбором, а не документов в базе.
# Гейт такое не ловит по построению: он сверяет числа, а не то, чем их называют.
#
# Поэтому имена переводятся здесь, на границе «внутреннее → клиентское», и переводятся
# КОДОМ: просьбу «не выдумывай смысл» модель читает и не исполняет (правило владельца).
# Ключ, которому имени не нашлось, числом наружу не идёт вовсе — вместо него счётчик
# «сколько ещё отсечек было»: потеря не молчаливая (п. 13), но и выдумать по ней нечего.
# П. 19: бюджет отбора видов — не неполнота посчитанного множества. F251 переименовал
# ключи, но речевой акт «учли не всё» остался — модель честно врала про «записи».
PARTIAL_BUDGET_KEYS = frozenset({
    "entities_shown", "entities_total",
    "partial_shown", "partial_total",
    "reranked", "reranked_of",
})
PARTIAL_ASSUMPTION_KEYS = frozenset({
    "intent_assumed", "period_assumed_dropped",
})
PARTIAL_LOSS_KEYS = frozenset({
    "coverage_missing", "undated_excluded", "intent_lost",
})

PARTIAL_LABELS = {
    "coverage_missing": "rows_missing_from_search",
    "undated_excluded": "records_without_date_excluded",
    "intent_lost": "question_parts_not_understood",
}


def _partial_count_loss(d):
    """Пометки о неполноте ПОСЧИТАННОГО множества — единственный повод для PARTIAL_HINT."""
    if not isinstance(d, dict):
        return {}
    return {k: v for k, v in d.items()
            if v is not None and k in PARTIAL_LOSS_KEYS}


def _named_partial(d):
    """Пометки потери счёта под именами, которые можно произнести человеку, не соврав."""
    if not isinstance(d, dict):
        return {}
    out, unnamed = {}, 0
    for k, v in d.items():
        if v is None:
            continue
        if k in PARTIAL_LABELS:
            out[PARTIAL_LABELS[k]] = v
        else:
            unnamed += 1
            sys.stderr.write("mcp_ask: пометка отсечки без имени для человека: %s\n" % k)
    if unnamed:
        out["other_limits_applied"] = unnamed
    return out


def _with_partial(out, data):
    """Дописать, что учтено не всё (п. 13) — только при потере счёта выбранного источника."""
    loss = _partial_count_loss(data.get("partial"))
    block = _kv_block("PARTIAL", _named_partial(loss))
    if not block:
        return out
    return out + "\n\n" + PARTIAL_HINT + "\n\n" + block


@mcp.tool()
def ask_1c(question: str, focus: str = "", measure: str = "",
           context: str = "", prior: str = "") -> str:
    """Ask about data stored in the company's ERP system.

    Figures come from the database and are checked before they are returned; pass them
    on as they are.

    If you already know which kind of record the question is about — for example the
    knowledge base named it while you were rephrasing the question — pass that name in
    `focus` on the FIRST call. Do not ask the user about it instead: naming a record type
    is not an answer, and the figures still have to be counted here.

    The reply may instead ask to CLARIFY, when the question fits several record types or
    several quantities. Put that question to the user with the options from the tool.

    :param question: the user's question, in their own language, about company data.
    :param focus: the kind of record to count over, as written for people.
    :param measure: quantity name, as written for people.
    :param context: optional background; not used for intent parsing.
    """
    try:
        data = _ask(question, focus or None, measure or None, context or None,
                    prior or None)
    except urllib.error.HTTPError as e:
        return ERROR_REPLY.format(detail="HTTP %d" % e.code)
    except Exception as e:                     # noqa: BLE001 — сеть/таймаут
        return ERROR_REPLY.format(detail=type(e).__name__)

    kind = data.get("kind", "")
    text = (data.get("text") or "").strip()

    # Отказ сервиса — НЕ то же самое, что отсутствие данных (п. 18): клиенту надо
    # сказать про сбой, а не про пустую базу, иначе он решит, что данных нет.
    if kind == "unavailable":
        return ERROR_REPLY.format(detail=text[:120] or "unavailable")

    if kind == "clarify":
        opts = data.get("options") or []
        lines = []
        # 🔴 ВНУТРЕННЕЕ ИМЯ ТАБЛИЦЫ МОДЕЛИ НЕ ОТДАЁТСЯ — И ЭТО ПО ПОСТРОЕНИЮ, А НЕ ФИЛЬТРОМ.
        # Было: `- Реализация Товаров Услуг | focus=document_реализациятоваровуслуг`, и
        # docstring велел скопировать `focus` дословно. Дальше бот пересказывал варианты
        # человеку своими словами — и внутреннее имя уходило клиенту мимо `ask_1c`, то есть
        # мимо зачистки плагина (`F218` закрывал её только на ответах инструмента).
        # [замер 03.08] так утекли «Реализация Товаров Услуг_Товары», `НДСРегл`, `НДСУпр`.
        # Стало: боту виден ОДИН и тот же человеческий текст — и как подпись варианта, и
        # как значение `focus`. Скопировать нечего, кроме того, что и так предназначено
        # человеку. Обратно в имя источника его сводит сервис (`resolve_focus`, 02.08) —
        # он принимает человеческое название наравне с внутренним, спрашивая базу, а не
        # разбирая строку. [замер 03.08] меток 1 502, различных 1 496: неоднозначны 6, и на
        # них `resolve_focus` честно возвращает «не свёл» и уходит обычным путём выбора.
        for o in opts:
            if not isinstance(o, dict):
                continue
            # `measure` заполнено — выбирается величина; иначе выбирается сущность.
            if o.get("measure"):
                # ⚠ Имя величины остаётся внутренним (`НДСРегл`): это ключ данных, и
                # человеческого имени у него сегодня нет ниоткуда. Отдельная работа.
                # 🔴 `focus` здесь — СУЩНОСТЬ, а не величина: в этой ветке `label` занят
                # именем величины, поэтому человеческое имя сущности приходит отдельным
                # полем `entity_label` (заведено в `serene_ask` тем же заходом). Пусто —
                # `focus` не передаём вовсе: лучше пустое поле, чем внутреннее имя наружу
                # или, того хуже, имя величины, поданное как сущность.
                name = o.get("label") or o["measure"]
                lines.append("- %s | measure=%s | focus=%s"
                             % (name, name, o.get("entity_label") or ""))
            elif o.get("src"):
                name = o.get("label") or o["src"]
                # Пояснение стоит РЯДОМ с подписью, но в `focus` не входит: значением
                # выбора остаётся ровно та строка, которую человек видит подписью, —
                # длинный `focus` бот копировал бы с ошибками. Пусто — строка прежняя.
                why = (o.get("hint") or "").strip()
                lines.append(("- %s — %s | focus=%s" % (name, why, name)) if why
                             else ("- %s | focus=%s" % (name, name)))
        out = CLARIFY_HINT
        if text:
            out += "\n\n" + text
        if lines:
            out += "\n\n%s:\n%s" % (CLARIFY_LABEL, "\n".join(lines))
        # OPTIONS остаются текстовым протоколом; рядом — структура для гейта/канала.
        block = _atom_json_block(_atoms_of(data), opts)
        if block:
            out += "\n\n" + block
        return _with_partial(out, data)

    # 🔴 ГЕЙТ ОТКЛОНИЛ ПРОЗУ, ЧИСЛА ПОСЧИТАНЫ. `text` в этой ветке — НЕ ответ: это либо
    # отказ (`refuse_text`), либо та самая непрошедшая формулировка. Пересылать его боту
    # значит отдать отказ, имея данные. Отдаём то, ради чего ветка и заведена, — числа.
    if kind == "figures":
        block = _figures_for_bot(data)
        if block:
            return _with_partial(FIGURES_HINT + "\n\n" + block, data)
        # Атома нет (старый сервис) — плоский словарь figures не отдаём: лучше пусто,
        # чем снова дать второй модели переназначить роли (аудит §8).
        return _with_partial(FIGURES_HINT, data)

    if kind == "no_data":
        if text:
            marker = "[NO DATA]"
            out = text if text.startswith(marker) else (marker + " " + text)
            return _with_partial(out, data)
        return NO_DATA_REPLY
    if not text:
        return NO_DATA_REPLY

    # Величина, по которой считали, названа рядом с ответом: у сущности бывает девять
    # величин со словом «сумма», и молчаливый выбор неотличим от догадки (п. 12).
    # `serene_ask` уже дописывает это в текст, если модель не назвала сама, — здесь
    # поле пробрасывается отдельно, чтобы бот мог сказать это своими словами.
    m = (data.get("measure") or "").strip()
    if m and m.lower() not in text.lower():
        text += "\n\n[величина: %s]" % m
    # Атом ответа — структурой рядом с текстом (гейт читает подписи/числа из ATOM_JSON).
    block = _atom_json_block(_atoms_of(data), data.get("options"))
    if block:
        text += "\n\n" + block
    return _with_partial(text, data)


if __name__ == "__main__":
    if not ASK_TOKEN:
        sys.stderr.write("WARN: ASK_TOKEN пуст — сервис ответов вернёт 401\n")
    _serve_with_auth(mcp)
