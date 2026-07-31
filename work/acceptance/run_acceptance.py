#!/usr/bin/env python3
"""Приёмка ЧЕРЕЗ БОТА, пачками. Вопросы и эталоны берутся из docs/ACCEPTANCE_UT.md."""
import json, os, re, subprocess, sys, time

DOC = os.environ.get('ACCEPTANCE_DOC', '/srv/1c/docs/ACCEPTANCE_UT.md')

def numify(s):
    s = re.sub(r'[\s    ⁠]', '', s).replace(',', '.')
    try: return float(s)
    except ValueError: return None

text = open(DOC, encoding='utf-8').read()
blocks = re.split(r'^\*\*(\d+)\. «(.+?)»\*\*$', text, flags=re.M)
cases = []
for i in range(1, len(blocks) - 2, 3):
    no, q, body = int(blocks[i]), blocks[i+1], blocks[i+2]
    m = re.search(r'^-\s*эталон:\s*\*\*(.+?)\*\*', body, re.M)
    ref = numify(m.group(1)) if m else None
    fails = [numify(x) for x in re.findall(r'^-\s*(?:🔴\s*)?провал:\s*\*\*(.+?)\*\*', body, re.M)]
    # 🔴 ОЖИДАЕМОЕ ПОВЕДЕНИЕ — ТОЖЕ ЭТАЛОН, И БЕЗ НЕГО ПРИЁМКА СЛЕПА ТАМ, ГДЕ ОПАСНЕЕ ВСЕГО.
    # [замер 31.07] 13 вопросов из 29 прогонщик помечал «без эталона», и я записал это как
    # «эталонов нет». Неверно: эталоны есть, но они не числовые — у этих вопросов стоит
    # строка «ожидаемый kind», и проверяют они, что система НЕ СОВРЁТ при отсутствии данных:
    # «на какую сумму продали ООО Ромашка» (такого контрагента нет), «сколько велосипедов»
    # (ноль в корпусе), «выручка за 2022» (данные кончаются 2019-11-18). Самый опасный класс
    # провалов не проверялся ни разу — не потому что нечем, а потому что прогонщик не читал.
    m = re.search(r'^-\s*(?:🔴\s*)?ожидаемый\s+`?kind`?:\s*(.+)$', body, re.M)
    kinds = re.findall(r'no_data|clarify|answer|figures|unavailable', m.group(1)) if m else []
    cases.append({'no': no, 'q': q, 'ref': ref, 'kinds': kinds,
                  'fails': [f for f in fails if f is not None]})

def ask_bot(q, key):
    p = subprocess.run(['sudo', '-u', 'undebot', '-H', 'timeout', '400',
                        'openclaw', 'agent', '--agent', 'main',
                        # 🔴 СВОЯ СЕССИЯ НА КАЖДЫЙ ПРОГОН. Прежде ключ был 'acc-<номер>' и
                        # повторялся между заходами: бот ПОМНИЛ прошлый ответ и говорил
                        # «цифры те же, что и полчаса назад» — то есть я мерил не работу
                        # системы, а её память. Прогоны 3 и 4 совпали до последней цифры
                        # именно поэтому.
                        '--session-key', 'acc-%s-%s' % (RUN, key), '--json', '-m', q],
                       capture_output=True, text=True, timeout=420)
    raw = p.stdout or p.stderr
    try:
        d = json.loads(raw)
        def dig(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    if k in ('text', 'content') and isinstance(v, str) and v.strip():
                        yield v
                    yield from dig(v)
            elif isinstance(o, list):
                for v in o: yield from dig(v)
        c = list(dig(d))
        return max(c, key=len) if c else raw
    except ValueError:
        return raw

def nums(t):
    t = re.sub(r'(?<=\d)[\s    ⁠](?=\d)', '', t)
    return [numify(x) for x in re.findall(r'\d+(?:[.,]\d+)?', t)]

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

RUN = os.environ.get('RUN_TAG') or str(int(time.time()))
lo, hi = int(sys.argv[1]), int(sys.argv[2])
print('прогон %s' % RUN, flush=True)
verno = utoch = nevern = bezet = 0
for c in cases:
    if not (lo <= c['no'] <= hi): continue
    t0 = time.time()
    try:
        txt = ask_bot(c['q'], str(c['no']))
    except Exception as e:
        print('%2d %-46s ОТКАЗ: %s' % (c['no'], c['q'][:46], e)); continue
    el = time.time() - t0
    got = nums(txt)
    flat = txt.lower()
    is_clar = bool(re.search(r'\?\s*$|уточн|имеете в виду|что именно|какой из|или ', txt.strip()[-260:], re.I))
    # Отказ распознаётся по СМЫСЛУ ответа, а не по числу: система обязана сказать, что
    # ответить не может (п. 18), и текст пишет модель на языке вопроса.
    is_refuse = bool(re.search(r'не могу|нет данных|не найд|отсутству|не содержит|'
                               r'не удалось|нельзя дать|не располага', flat)) and not got
    if c['ref'] is None and c['kinds']:
        # Поведенческий вопрос: сверяем ЧТО СДЕЛАЛА система, а не какое число назвала.
        ok = (('no_data' in c['kinds'] and is_refuse)
              or ('clarify' in c['kinds'] and is_clar)
              or (('answer' in c['kinds'] or 'figures' in c['kinds']) and bool(got)))
        if ok:
            v = 'ВЕРНО (поведение: %s)' % '/'.join(c['kinds']); verno += 1
        else:
            v = '🔴 НЕ ТО ПОВЕДЕНИЕ (ждали %s)' % '/'.join(c['kinds']); nevern += 1
    elif c['ref'] is None:
        v = 'нет эталона'; bezet += 1
    elif any(close(g, c['ref']) for g in got):
        v = 'ВЕРНО'; verno += 1
    elif any(close(g, f) for g in got for f in c['fails']):
        v = '🔴 ПРОВАЛ (число из перечня провалов)'; nevern += 1
    elif is_clar and not got:
        v = 'уточнение'; utoch += 1
    else:
        v = '🔴 НЕ СОВПАЛО'; nevern += 1
    print('%2d %-46s %5.0fс %s' % (c['no'], c['q'][:46], el, v), flush=True)
    if v.startswith('🔴'):
        print('    эталон %s%s | в ответе %s'
              % (c['ref'], (' / поведение ' + '/'.join(c['kinds'])) if c['kinds'] else '',
                 got[:5]), flush=True)
        print('    %s' % txt.replace('\n', ' ')[:200], flush=True)
print('\nИТОГ %d-%d: ВЕРНО %d, уточнений %d, НЕВЕРНО %d, без эталона %d'
      % (lo, hi, verno, utoch, nevern, bezet), flush=True)
