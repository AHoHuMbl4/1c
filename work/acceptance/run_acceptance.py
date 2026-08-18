#!/usr/bin/env python3
"""Приёмка ЧЕРЕЗ БОТА, пачками. Вопросы и эталоны берутся из docs/ACCEPTANCE_UT.md.

🔴 §0. ЧЕМ ЭТОТ ПРИБОР ОТЛИЧАЕТСЯ ОТ ПРЕЖНЕГО (правка 02.08, кластер Э1)

Прежняя редакция засчитывала провал за успех и мерила язык, а не работу системы.
Замер «до» на живом наборе (58 вопросов) — числа, а не рассуждение:

| Что | Было | Почему это дефект |
|---|---|---|
| читается вопросов | **54 из 58** | якорь `$` в разборе заголовка: у №27, 56, 57, 58 после кавычек стоит пояснение. Терялись молча |
| сверяется числом | **26 из 58** | у 16 вопросов эталон в доке ЕСТЬ, но он составной («186 заказов, 14 631 167,72») — `float()` его не брал, и вопрос уходил в «без эталона» |
| засчитывается по ЛЮБОМУ числу | **8** (`F210`) | ветка поведения при `answer/figures` проверяла `bool(got)`: ответ с любой цифрой = ВЕРНО, включая перечисленные в доке провалы |
| отказ и уточнение | по спискам русских слов | `F212`: на базе другого языка это не прибор. И `F211`: союз «или» в ответе = «уточнение» |

Устройство новой редакции — правило проекта «есть источник истины? спроси его, а не
разбирай текст» (`CLAUDE.md`, девиз 29.07):

- **что система ответила** берётся из стенограммы сессии бота: результат вызова `ask_1c`
  лежит в `details.structuredContent.result`, а мост ставит туда машинные маркеры
  `[NO DATA]` / `[CLARIFICATION NEEDED]` / `[SERVICE ERROR: …]` (`mcp_ask.py:103-112`).
  Это `kind` сервиса как есть, без языка и без догадок;
- **что видит человек** — финальный текст модели. Сверяются оба: если сервис сказал
  «нет данных», а в ответе человеку появилось число, это **не** верный ответ, как бы
  число ни совпало с эталоном. Прежний прибор этот класс не видел вовсе;
- **эталон не разобран — это не «ВЕРНО»**, а отдельный исход «прибор не проверил».
  Молчаливое вырождение в «любое число» и было `F210`.

🔴 Прежние отметки приёмки («пачка 1-10 → 2-3 верных, 11-20 → 4») сняты СЛОМАННОЙ
линейкой и базой сравнения быть не могут (`DEV_PLAN.md`, Э1).

Проба прибора подменой — `test_acceptance.py`, без базы, сети и модели.
"""
import json, os, re, subprocess, sys, time

DOC = os.environ.get('ACCEPTANCE_DOC', '/srv/1c/docs/ACCEPTANCE_UT.md')
AGENT = os.environ.get('ACCEPTANCE_AGENT', 'main')
BOT_USER = os.environ.get('ACCEPTANCE_BOT_USER', 'undebot')

# Пробелы, которыми разделяют тысячи: обычный, неразрывный, узкий неразрывный, тонкий,
# и невидимый разделитель. Перечень — свойство типографики, а не нашей базы.
SP = '    ⁠'
# 🔴 Число с разделителями тысяч распознаётся ТОЛЬКО группами по три цифры. Прежде
# прибор просто выкидывал пробелы между любыми цифрами (`F211`), и «12 5» становилось
# «125»: два числа ответа склеивались в третье, которого никто не называл.
NUM_RE = re.compile(r'\d{1,3}(?:[%s]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?' % SP)
DATE_RE = re.compile(r'\d{4}-\d{2}-\d{2}')
TIME_RE = re.compile(r'\d{1,2}:\d{2}(?::\d{2})?')
KIND_RE = re.compile(r'no_data|clarify|answer|figures|unavailable')

# Маркеры моста (`mcp_ask.py`). Это протокол, а не текст на языке: менять только вместе
# с мостом и плагином-гейтом.
#
# 🔴 `[FIGURES]` мост начал ставить 02.08 (кластер Э4, `F129`): когда гейт снял неверную
# формулировку, боту уходят посчитанные базой числа. Прибор обязан знать оба состояния
# моста — и до этой правки, и после: неизвестный маркер он принял бы за обычный ответ.
MARKERS = (('[NO DATA]', 'no_data'),
           ('[CLARIFICATION NEEDED]', 'clarify'),
           ('[SERVICE ERROR', 'unavailable'),
           ('[FIGURES]', 'figures'))
# `answer` и `figures` — один исход по существу: система ответила по данным, числа
# посчитаны базой. Док называет то одно, то другое, и придираться к этому прибор не вправе.
ANSWERED = {'answer', 'figures'}


def numify(s):
    s = re.sub(r'[%s\s]' % SP, '', s).replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return None


def nums(text):
    """Числа текста. Даты и время выкидываются: «2016-02-24 14:36:49» — не пять чисел."""
    text = TIME_RE.sub(' ', DATE_RE.sub(' ', text))
    return [n for n in (numify(x) for x in NUM_RE.findall(text)) if n is not None]


def dates(text):
    return DATE_RE.findall(text)


def close(a, b):
    """Совпадение эталона и числа из ответа — ТОЧНОЕ, без подобранных допусков.

    🔴 Прежде здесь стояло `abs(a-b) <= max(0.51, abs(b)*0.0001)`, и это подгонка: 0,51
    покрывало дробные «26 239,5», а 0,0001 — копеечные расхождения в суммах. Обе величины
    взяты из НАШЕЙ базы и на чужой ничего не значат, а решают они «верно / не совпало»,
    то есть стоят на пути правильности. Поймано ревизором до коммита.

    Сравниваем до копейки. Вторая ветка — не допуск, а та же величина, записанная БЕЗ
    копеек: «21 188 510» и «21 188 510,49» человек считает одним ответом, и спорить с
    ним прогонщику не о чем.
    """
    if a is None or b is None:
        return False
    return round(a, 2) == round(b, 2) or round(a) == round(b)


def parse_ref(bold):
    """Эталон → перечень величин, которые ОБЯЗАНЫ прозвучать в ответе.

    Эталон бывает составным: «186 заказов, 14 631 167,72», «1 901 запись, Сумма =
    1 137 949,71, Количество = 94 784». Вопрос задан про обе величины — значит обе и
    проверяем. Прежний прибор пытался прочитать всю строку одним `float()`, не мог, и
    записывал вопрос в «без эталона»: так не проверялись 16 вопросов из 58.

    Имена собственные («Тюренкова Наталья Сергеевна») не проверяются: у ответа на них
    нет обязательной формы. Если ни числа, ни даты в эталоне нет — прибор честно
    говорит, что проверить не может, и не выдаёт это за успех.
    """
    if not bold:
        return {'nums': [], 'dates': [], 'raw': bold}
    d = DATE_RE.findall(bold)
    return {'nums': nums(bold), 'dates': d, 'raw': bold}


def parse_cases(text):
    """Разбор набора. Заголовок — `**<N>. «вопрос»**`, БЕЗ якоря конца строки.

    🔴 Якорь `$` стоил четырёх вопросов из 58 (27, 56, 57, 58): у них после кавычек
    идёт пояснение в скобках. Прогонщик молчал об этом — «приёмка 58» на деле брала 54.
    """
    blocks = re.split(r'^\*\*(\d+)\. «(.+?)»\*\*', text, flags=re.M)
    cases = []
    for i in range(1, len(blocks) - 2, 3):
        no, q, body = int(blocks[i]), blocks[i + 1], blocks[i + 2]
        m = re.search(r'^-\s*эталон:\s*\*\*(.+?)\*\*', body, re.M | re.S)
        ref = parse_ref(m.group(1) if m else None)
        # Перечень провалов: числа берутся из ВСЕЙ строки, не только из жирного —
        # в доке половина записана без выделения («провал: 234 заказа (строки)»).
        fails, fail_kinds = [], []
        for line in re.findall(r'^-\s*(?:🔴\s*)?провал:\s*(.+)$', body, re.M):
            fails += nums(line)
            fail_kinds += KIND_RE.findall(line)
        mk = re.search(r'^-\s*(?:🔴\s*)?ожидаемый\s+`?kind`?:\s*(.+)$', body, re.M)
        # 🔴 ОЖИДАЕМОЕ ПОВЕДЕНИЕ — ТОЖЕ ЭТАЛОН, И БЕЗ НЕГО ПРИЁМКА СЛЕПА ТАМ, ГДЕ
        # ОПАСНЕЕ ВСЕГО. [замер 31.07] 13 вопросов из 29 прогонщик помечал «без
        # эталона», и я записал это как «эталонов нет». Неверно: эталоны есть, но они
        # не числовые — у этих вопросов стоит строка «ожидаемый kind», и проверяют они,
        # что система НЕ СОВРЁТ при отсутствии данных: «на какую сумму продали ООО
        # Ромашка» (такого контрагента нет), «сколько велосипедов» (ноль в корпусе),
        # «выручка за 2022» (данные кончаются 2019-11-18).
        kinds = KIND_RE.findall(mk.group(1)) if mk else []
        cases.append({'no': no, 'q': q, 'ref': ref, 'kinds': kinds,
                      'fails': fails, 'fail_kinds': fail_kinds})
    return cases


def kind_of(service_text):
    """`kind` сервиса по маркеру моста. Без языка, без списков слов."""
    if service_text is None:
        return None
    s = service_text.lstrip()
    for mark, kind in MARKERS:
        if s.startswith(mark):
            return kind
    return 'answer'


def check_values(ref, text):
    """Каких величин эталона в ответе НЕ хватает. Пустой список = все на месте."""
    got_n, got_d = nums(text), dates(text)
    missing = []
    for d in ref['dates']:
        if d in got_d:
            continue
        # Дата может быть названа словами на языке ответа («24 февраля 2016»), поэтому
        # день и год ищем числами, а название месяца не проверяем: это был бы список
        # русских слов, то есть ровно тот дефект, из-за которого прибор переписан.
        y, day = float(d[:4]), float(d[8:10])
        if any(close(g, y) for g in got_n) and any(close(g, day) for g in got_n):
            continue
        missing.append(d)
    for n in ref['nums']:
        if not any(close(g, n) for g in got_n):
            missing.append(n)
    return missing


def harm(case, obs, code):
    """🔴 ВРЕД — по мерилу владельца 03.08: «нужно 100% правильности; переспрашивать можно».

    Прежняя сводка отвечает на вопрос «сколько верных», и уточнение в ней — провал. Но раз
    переспрашивать разрешено, провалом оно быть перестаёт: цель не «всегда ответить», а
    НИКОГДА НЕ ОТВЕТИТЬ НЕВЕРНО. Считать надо ошибки, и цель по ним — ноль.

    Три исхода:
      * `ok`     — ответил и величины эталона на месте;
      * `asked`  — не утверждал ничего: переспросил или честно отказался (чисел в ответе
                   нет). По мерилу владельца это ДОПУСТИМО, хотя и не бесплатно;
      * `error`  — назвал величину, и она не сошлась с эталоном. Это и есть то, чего быть
                   не должно.

    Внешний сбой прибора (`broken`) в счёт не идёт: он не про качество ответов (`№24`).
    """
    if code == 'broken':
        return 'broken'
    if code == 'ok':
        return 'ok'
    human = obs.get('human') or ''
    if not nums(human):
        # Ни одной величины не названо — утверждения не было, значит и неверного не было.
        return 'asked'
    ref = case['ref']
    if (ref['nums'] or ref['dates']) and not check_values(ref, human):
        # Величины эталона на месте, а прежний код был не `ok` по другой причине
        # (например, ждали иной `kind`). Для вреда это не ошибка.
        return 'ok'
    return 'error'


def verdict(case, obs):
    """Вердикт по одному вопросу. Чистая функция: ни базы, ни сети, ни модели.

    obs — что наблюдали: {'human': текст человеку, 'service': текст сервиса как есть,
    'called': звал ли бот ask_1c, 'error': строка внешнего сбоя}.

    Возвращает (код, пояснение). Коды: ok / clarify / wrong / fail / unchecked / broken.
    'broken' — внешний сбой, он НЕ неверный ответ (`№24`) и в счёт качества не идёт.
    """
    if obs.get('error'):
        return 'broken', 'внешний сбой: %s' % obs['error']
    human = obs.get('human') or ''
    if not human.strip():
        return 'broken', 'пустой ответ бота'
    if not obs.get('called'):
        # Ответ без обращения к данным — дефект продукта, а не сбой прибора: гейт
        # обязан такой ход останавливать (`verify-plugin`).
        return 'wrong', 'бот ответил, не позвав ask_1c'

    kind = kind_of(obs.get('service'))
    human_nums = nums(human)

    # Сервис сказал «нет данных» или «сбой», а человеку ушло число — это выдумка, и
    # никакое совпадение с эталоном её не оправдывает. Прежний прибор такого не видел.
    if kind in ('no_data', 'unavailable') and human_nums:
        return 'wrong', 'сервис ответил %s, а человеку ушло число %s' % (kind, human_nums[:3])

    def named(kind, kinds):
        """Назван ли исход в перечне. `answer` и `figures` считаются одним."""
        return kind in kinds or (kind in ANSWERED and bool(ANSWERED & set(kinds)))

    if named(kind, case['fail_kinds']) and not named(kind, case['kinds']):
        return 'fail', 'kind `%s` назван в доке провалом' % kind

    if case['kinds'] and not named(kind, case['kinds']):
        return 'wrong', 'kind `%s`, ждали `%s`' % (kind, '/'.join(case['kinds']))

    # Уточнение — законный исход там, где док его допускает. Число при нём не сверяем:
    # система ещё не отвечала.
    if kind == 'clarify':
        return 'clarify', 'уточнение'
    if kind in ('no_data', 'unavailable'):
        return ('ok', 'поведение: %s' % kind) if kind in case['kinds'] \
            else ('wrong', 'сервис ответил %s' % kind)

    ref = case['ref']
    if not ref['nums'] and not ref['dates']:
        # 🔴 Здесь `F210` и жил. Ждать `answer` — не значит иметь эталон: «система что-то
        # ответила» проверяемым утверждением не является, и засчитывать это за ВЕРНО
        # означает хвалить прибор за то, что бот не промолчал. Проверить нечем — так и
        # говорим. Отказ и уточнение — другое дело: там сам исход и есть эталон.
        return 'unchecked', 'эталон не разобран: %s' % (ref['raw'] or 'строки «эталон:» нет')

    hit_fail = [f for f in case['fails'] if any(close(g, f) for g in human_nums)]
    missing = check_values(ref, human)
    if not missing:
        # Число из перечня провалов рядом с верным ответом — не провал: у вопросов
        # вроде «сколько товаров» док сам называет несколько законных величин.
        return 'ok', 'все величины эталона на месте'
    if hit_fail:
        return 'fail', 'число из перечня провалов: %s' % hit_fail[:3]
    return 'wrong', 'нет величин эталона: %s' % missing[:3]


# ---------------------------------------------------------------- работа с ботом

# 🔴 НАСТОЯЩАЯ ДОСТАВКА — ЕДИНСТВЕННЫЙ СПОСОБ ПОМЕРИТЬ ТО, ЧТО ПОЛУЧАЕТ КЛИЕНТ.
# Хуки, умеющие ЗАМЕНИТЬ необоснованное число готовым ответом, живут только на пути
# доставки в канал (`techContext` Ловушка 39); `openclaw agent` без `--deliver` их не
# зовёт. Поэтому доставка — переключатель прогонщика, а не правка кода под наш стенд:
# канал и адресат задаются окружением, в коде их нет (девиз: никакой привязки к базе и
# к конкретной установке).
DELIVER = os.environ.get('ACCEPTANCE_DELIVER', '0') == '1'
REPLY_CHANNEL = os.environ.get('ACCEPTANCE_REPLY_CHANNEL') or ''
REPLY_TO = os.environ.get('ACCEPTANCE_REPLY_TO') or ''


def deliver_args():
    """Аргументы доставки. Пусто, если доставка выключена."""
    if not DELIVER:
        return []
    a = ['--deliver']
    if REPLY_CHANNEL:
        a += ['--reply-channel', REPLY_CHANNEL]
    if REPLY_TO:
        a += ['--reply-to', REPLY_TO]
    return a


# 🔴 СЛЕД СЕРВИСА ЗА КАЖДЫЙ ВОПРОС. Требование владельца 03.08: «на каждом шагу логировать
# можно — время, что делается и что происходит». Сам след пишет `serene_ask` (`diag.шаги` и
# строки `ask СЛЕД` в поток ошибок); до модели он НЕ доходит и дойти не должен — там
# внутренние имена сущностей. Поэтому прогонщик берёт его из журнала юнита, а не из ответа.
#
# Имя юнита — в окружении, а не в коде: у другой установки оно другое. Не задано — след
# просто не собирается, прогон идёт как прежде.
ASK_UNIT = os.environ.get('ACCEPTANCE_ASK_UNIT') or ''


def ask_trace(since_iso):
    """Строки следа сервиса, появившиеся с момента `since_iso`."""
    if not ASK_UNIT:
        return []
    try:
        p = subprocess.run(['journalctl', '-u', ASK_UNIT, '--since', since_iso,
                            '--no-pager', '-o', 'cat'],
                           capture_output=True, text=True, timeout=60)
    except Exception:                               # noqa: BLE001 — журнал не обязателен
        return []
    out = []
    for l in p.stdout.splitlines():
        if 'TRACE ' in l and ' service ' in l:
            out.append(l.split('TRACE ', 1)[1].strip())
        elif 'ask СЛЕД' in l:
            out.append(l.split('ask СЛЕД', 1)[1].strip())
    return out


def ask_bot(q, key, run):
    p = subprocess.run(['sudo', '-u', BOT_USER, '-H', 'timeout', '400',
                        'openclaw', 'agent', '--agent', AGENT] + deliver_args() + [
                        # 🔴 СВОЯ СЕССИЯ НА КАЖДЫЙ ПРОГОН. Прежде ключ был 'acc-<номер>' и
                        # повторялся между заходами: бот ПОМНИЛ прошлый ответ и говорил
                        # «цифры те же, что и полчаса назад» — то есть я мерил не работу
                        # системы, а её память. Прогоны 3 и 4 совпали до последней цифры
                        # именно поэтому.
                        '--session-key', 'acc-%s-%s' % (run, key), '--json', '-m', q],
                       capture_output=True, text=True, timeout=420)
    raw = p.stdout or p.stderr
    try:
        d = json.loads(raw)
    except ValueError:
        return raw

    def dig(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ('text', 'content') and isinstance(v, str) and v.strip():
                    yield v
                yield from dig(v)
        elif isinstance(o, list):
            for v in o:
                yield from dig(v)
    c = list(dig(d))
    return max(c, key=len) if c else raw


def session_file(key, run):
    """Путь к стенограмме сессии — спрашиваем сам движок, а не собираем имя догадкой."""
    p = subprocess.run(['sudo', '-u', BOT_USER, '-H', 'openclaw', 'sessions',
                        '--agent', AGENT, '--json', '--limit', 'all'],
                       capture_output=True, text=True, timeout=120)
    try:
        rows = json.loads(p.stdout).get('sessions') or []
    except ValueError:
        return None
    want = 'acc-%s-%s' % (run, key)
    for r in rows:
        if (r.get('key') or '').endswith(':' + want) or r.get('key') == want:
            return r.get('sessionFile')
    return None


def service_reply(path):
    """Что ответил СЕРВИС (не модель): результат вызова ask_1c из стенограммы.

    Берём последний вызов: после уточнения бот зовёт инструмент второй раз, и отвечает
    человеку именно по нему.
    """
    if not path or not os.path.exists(path):
        return None, False
    try:
        lines = open(path, encoding='utf-8').read().splitlines()
    except PermissionError:
        p = subprocess.run(['sudo', '-u', BOT_USER, 'cat', path],
                           capture_output=True, text=True, timeout=60)
        lines = p.stdout.splitlines()
    out, called = None, False
    for line in lines:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        m = d.get('message') or {}
        if m.get('role') != 'toolResult' or not str(m.get('toolName', '')).endswith('ask_1c'):
            continue
        called = True
        sc = (m.get('details') or {}).get('structuredContent') or {}
        txt = sc.get('result')
        if txt is None:
            txt = ' '.join(c.get('text', '') for c in (m.get('content') or [])
                           if isinstance(c, dict))
        out = txt
    return out, called


# ------------------------------------------------- след гейта: сработал ли он вообще

# 🔴 ПОЧЕМУ ЭТО ЗАВЕДЕНО. [замер 03.08] по журналу шлюза за 23.07-03.08: `after_tool_call`
# 239 срабатываний, `before_agent_finalize` 443, а `message_sending` — ОДНО и
# `message_received` — ОДНО. Числовая половина гейта живёт на доставке в канал, которой у
# `openclaw agent` нет: значит КАЖДОЕ число приёмки, когда-либо снятое, получено с
# выключенной половиной защиты, и одиннадцать дней это было не видно ниоткуда.
#
# Отсюда правило прибора: прогон, в котором гейт не сработал ни разу, — НЕ результат, а
# показание сломанной установки. Прибор обязан это сказать сам, а не оставить читателя
# гадать. Это тот же урок, что в `HOW_NOT_TO`: защита, ничего не запретившая ни разу,
# подозрительна, и нужен замер, что она СРАБАТЫВАЕТ.

def gate_log_path():
    """Где журнал шлюза — спрашиваем конфиг движка, а не собираем путь догадкой."""
    p = os.environ.get('ACCEPTANCE_GATEWAY_LOG')
    if p:
        return p
    cfg = '/home/%s/.openclaw/openclaw.json' % BOT_USER
    try:
        with open(cfg, encoding='utf-8') as f:
            return (json.load(f).get('logging') or {}).get('file')
    except (OSError, ValueError):
        return None


def gate_debug_on():
    """Гейт пишет свой вердикт только при `config.debug` — без него следа не будет."""
    cfg = '/home/%s/.openclaw/openclaw.json' % BOT_USER
    try:
        with open(cfg, encoding='utf-8') as f:
            e = ((json.load(f).get('plugins') or {}).get('entries') or {}).get('braine-verify') or {}
        return bool((e.get('config') or {}).get('debug'))
    except (OSError, ValueError):
        return False


GATE_RE = re.compile(r'\[braine-verify\] (\w+)[^\n]*?sess=(\S+)')


def gate_trace(path, since_ts, key, run):
    """Что гейт сделал на сессии этого вопроса: {хук: [что решил, ...]}.

    Разбирается ТОЛЬКО собственная строка гейта — она наша, формат наш.
    """
    want = 'acc-%s-%s' % (run, key)
    out = {}
    if not path or not os.path.exists(path):
        return out
    try:
        lines = open(path, encoding='utf-8', errors='replace').read().splitlines()
    except OSError:
        return out
    for line in lines:
        if 'braine-verify' not in line:
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if (d.get('time') or '') < since_ts:
            continue
        m = GATE_RE.search(d.get('message') or '')
        if not m or not m.group(2).endswith(want):
            continue
        act = re.search(r'action=(\S+)', d.get('message') or '')
        out.setdefault(m.group(1), []).append(act.group(1) if act else 'ran')
    return out


def main():
    run = os.environ.get('RUN_TAG') or str(int(time.time()))
    lo, hi = int(sys.argv[1]), int(sys.argv[2])
    cases = [c for c in parse_cases(open(DOC, encoding='utf-8').read())
             if lo <= c['no'] <= hi]
    print('прогон %s: вопросов в диапазоне %d-%d — %d' % (run, lo, hi, len(cases)), flush=True)
    glog, gdebug = gate_log_path(), gate_debug_on()
    since = time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime())
    if not gdebug:
        print('🔴 ГЕЙТ СЛЕДА НЕ ОСТАВИТ: plugins.entries.braine-verify.config.debug выключен.\n'
              '   Прогон пойдёт, но доказать, что защита работала, будет нечем.', flush=True)
    gate = {'figures': 0, 'revised': 0, 'delivery': 0, 'silent': 0}
    tally = {'ok': 0, 'clarify': 0, 'wrong': 0, 'fail': 0, 'unchecked': 0, 'broken': 0}
    # Счёт ВРЕДА — по мерилу владельца (см. `harm`): ошибок должно быть ноль.
    harms = {'ok': 0, 'asked': 0, 'error': 0, 'broken': 0}
    bad = []
    LABEL = {'ok': 'ВЕРНО', 'clarify': 'уточнение', 'wrong': '🔴 НЕВЕРНО',
             'fail': '🔴 ПРОВАЛ', 'unchecked': '⚠ ПРИБОР НЕ ПРОВЕРИЛ', 'broken': '⚠ СБОЙ'}
    for c in cases:
        t0 = time.time()
        q_since = time.strftime('%Y-%m-%d %H:%M:%S')
        obs = {'human': '', 'service': None, 'called': False, 'error': None}
        try:
            obs['human'] = ask_bot(c['q'], str(c['no']), run)
        except Exception as e:                      # noqa: BLE001 — внешний сбой
            obs['error'] = '%s: %s' % (type(e).__name__, e)
        if not obs['error']:
            try:
                obs['service'], obs['called'] = service_reply(session_file(str(c['no']), run))
            except Exception as e:                  # noqa: BLE001
                obs['error'] = 'стенограмма недоступна: %s' % type(e).__name__
        code, why = verdict(c, obs)
        tally[code] += 1
        h = harm(c, obs, code)
        harms[h] += 1
        if h == 'error':
            bad.append(c['no'])
        # След гейта за ЭТОТ вопрос: числовая сверка на завершении хода и, если ответ
        # доставлялся в канал, — хук доставки. Пусто = защита не звалась вовсе.
        tr = gate_trace(glog, since, str(c['no']), run) if gdebug else {}
        fin = tr.get('before_agent_finalize') or []
        figures = [a for a in fin if a in ('pass', 'revise')]
        if figures:
            gate['figures'] += 1
            if 'revise' in figures:
                gate['revised'] += 1
        else:
            gate['silent'] += 1
        if tr.get('message_sending') or tr.get('reply_payload_sending'):
            gate['delivery'] += 1
        mark = ('гейт:%s' % '/'.join(figures)) if figures else '🔴 гейт молчал'
        print('%2d %-46s %5.0fс %s — %s [%s]'
              % (c['no'], c['q'][:46], time.time() - t0, LABEL[code], why, mark), flush=True)
        if code in ('wrong', 'fail', 'unchecked'):
            print('    эталон %s%s' % (c['ref']['raw'],
                  (' | поведение ' + '/'.join(c['kinds'])) if c['kinds'] else ''), flush=True)
            print('    человеку: %s' % (obs['human'] or '').replace('\n', ' ')[:200], flush=True)
            print('    сервис:   %s' % (obs['service'] or '—').replace('\n', ' ')[:160], flush=True)
        # След печатается ВСЕГДА, а не только у неверных: по верным видно, чем выбор
        # держался, и без этого «стало верно» неотличимо от везения.
        for ln in ask_trace(q_since):
            print('    след: %s' % ln, flush=True)
    done = sum(tally.values()) - tally['broken']
    print('\nИТОГ %d-%d: прогнано %d из %d (внешних сбоев %d)'
          % (lo, hi, done, len(cases), tally['broken']), flush=True)
    print('ВЕРНО %d, уточнений %d, НЕВЕРНО %d, ПРОВАЛОВ %d, прибор не проверил %d'
          % (tally['ok'], tally['clarify'], tally['wrong'], tally['fail'],
             tally['unchecked']), flush=True)
    # 🔴 ГЛАВНАЯ СВОДКА С 03.08. Указание владельца: «нужно 100% правильности ответов,
    # переспрашивать можно». Значит мерило — не «сколько верных», а СКОЛЬКО НЕВЕРНЫХ, и
    # цель по ним ноль. Уточнение и честный отказ сюда не идут: система ничего не утверждала.
    print('\nПО МЕРИЛУ «НИКОГДА НЕ ОТВЕЧАТЬ НЕВЕРНО»: 🔴 ОШИБОК %d%s, верных %d, '
          'не утверждал (спросил или отказался) %d'
          % (harms['error'], (' — вопросы %s' % bad) if bad else '',
             harms['ok'], harms['asked']), flush=True)

    # 🔴 БЕЗ ЭТОГО БЛОКА ЧИСЛА ВЫШЕ НЕ ЗНАЧАТ НИЧЕГО. Они описывают ту систему, которая
    # работала во время прогона, — а работала ли в ней защита, до 03.08 не спрашивал никто.
    print('\nГЕЙТ ЗА ЭТОТ ПРОГОН: числовая сверка отработала на %d вопросах из %d '
          '(из них потребовала переписать %d), доставка проверяла %d, молчал на %d'
          % (gate['figures'], done or len(cases), gate['revised'],
             gate['delivery'], gate['silent']), flush=True)
    if gate['figures'] == 0:
        print('🔴 ЗАЩИТА НЕ СРАБОТАЛА НИ РАЗУ — числа прогона результатом не являются.\n'
              '   Так выглядит замер сломанной установкой, а не плохое качество ответов.',
              flush=True)
    if gate['delivery'] == 0:
        print('⚠ Хуки ДОСТАВКИ не звались: `openclaw agent` без --deliver в канал не пишет.\n'
              '   Замена необоснованного числа готовым ответом проверяется только доставкой;\n'
              '   здесь проверена лишь та половина, что живёт на завершении хода.', flush=True)
    return tally


if __name__ == '__main__':
    main()
