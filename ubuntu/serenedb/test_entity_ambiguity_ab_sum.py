#!/usr/bin/env python3
"""Оффлайн-замок: entity-ambiguity (fork.outcome == "empty") для sum.

Pure-логика A/B/C + воспроизведение живого пути okna «сколько продали вчера?»:
plan.compute пустой, intent.want=sum, fork.outcome=empty, два src.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault('ASK_TOKEN', 'test')
os.environ.setdefault('EMBED_BASE_URL', '-')
os.environ.setdefault('EMBED_MODEL', '-')
os.environ.setdefault('ASK_REQUIRE_SUPPORT', '0')

import serene_ask as A  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond):
    global PASS
    if cond:
        PASS += 1
        print('ok  -', name)
    else:
        FAIL.append(name)
        print('FAIL-', name)


# ── Eligibility ───────────────────────────────────────────────────────────────
intent_sum_period = {'period': {'from': '2026-08-18', 'to': '2026-08-18'}}
plan_sum = {'compute': 'sum'}
diag_empty_fork = {'fork': {'outcome': 'empty'}}

t('eligible: fork.outcome empty + compute=sum + period window',
  A.entity_ambiguity_ab_sum_eligible(intent_sum_period, plan_sum, diag_empty_fork))

t('not eligible: no period window',
  not A.entity_ambiguity_ab_sum_eligible({'period': {}}, plan_sum, diag_empty_fork))

t('not eligible: compute != sum',
  not A.entity_ambiguity_ab_sum_eligible(
      intent_sum_period, {'compute': 'count'}, diag_empty_fork))

# ── Live okna inputs (plan.compute пуст — был compute=— в entity_ab_skip) ─────
SRC_DOC = 'document_выручкаотреализациитмцфизлицо_номенклатура'
SRC_REG = 'accumulationregister_реализациятмц'
LIVE_SUM = 100.0  # оба src — один итог за день

intent_live = {
    'want': 'sum',
    'period': {'from': '2026-08-18', 'to': '2026-08-18'},
}
plan_live = {}
diag_live = {
    'fork': {'outcome': 'empty', 'pool': 3, 'classes': 2, 'srcs': 2},
    'signals_disagree': SRC_DOC,
    'arbiter_rivals': [],
}
picked_live = [SRC_DOC, SRC_REG]
opts_live = [
    {'src': SRC_DOC, 'distinct_by': '', 'label': 'Выручка', 'hint': '', 'found': 1},
    {'src': SRC_REG, 'distinct_by': 'реализация ТМЦ', 'label': 'Реализация ТМЦ',
     'hint': '', 'found': 1},
]

t('live: entity_ab_compute from intent.want',
  A.entity_ab_effective_compute(intent_live, plan_live) == 'sum')
t('live: plan_compute empty',
  A.entity_ab_effective_compute(intent_live, plan_live)
  == (plan_live.get('compute') or intent_live.get('want')))
t('live: skip None (not compute=—)',
  A.entity_ambiguity_ab_sum_skip(intent_live, plan_live, diag_live, 2) is None)

# old bug: plan-only eligible would fail
t('live: plan-only eligible False',
  not ((plan_live or {}).get('compute') == 'sum'))


def _mock_sub_answer(question, focus=None, measure_pick=None, **kw):
    return {
        'kind': 'answer',
        'text': str(LIVE_SUM),
        'figures': {'sum': LIVE_SUM},
        'diag': {'focus': focus, 'measure': measure_pick},
    }


def _mock_probe_measure(src, intent, question, match, preds):
    return 'Всего'


diag_attempt = dict(diag_live)
orig_probe = A.entity_ambiguity_ab_probe_measure
A.entity_ambiguity_ab_probe_measure = _mock_probe_measure
try:
    out_live = A.entity_ambiguity_ab_sum_attempt(
        'сколько продали вчера?', intent_live, plan_live, diag_attempt,
        picked_live, opts_live, None, '', {}, None, None,
        answer_fn=_mock_sub_answer)
finally:
    A.entity_ambiguity_ab_probe_measure = orig_probe

t('live attempt: kind=answer', (out_live or {}).get('kind') == 'answer')
t('live attempt: entity_ab_case=A',
  (out_live or {}).get('diag', {}).get('entity_ab_case') == 'A')
t('live attempt: no entity_ab_skip', 'entity_ab_skip' not in diag_attempt)
t('live attempt: plan_compute in diag', diag_attempt.get('plan_compute') is None)
t('live attempt: entity_ab_compute=sum',
  diag_attempt.get('entity_ab_compute') == 'sum')

# sub_clarify → entity_ab_skip виден (не молчит)
diag_sub_cl = dict(diag_live)


def _mock_sub_clarify(question, focus=None, measure_pick=None, **kw):
    return {
        'kind': 'clarify',
        'diag': {'measure_ambiguous': True, 'focus': focus},
        'options': [],
    }


diag_sub_cl = dict(diag_live)
A.entity_ambiguity_ab_probe_measure = _mock_probe_measure
try:
    out_cl = A.entity_ambiguity_ab_sum_attempt(
        'сколько продали вчера?', intent_live, plan_live, diag_sub_cl,
        picked_live, opts_live, None, '', {}, None, None,
        answer_fn=_mock_sub_clarify)
finally:
    A.entity_ambiguity_ab_probe_measure = orig_probe

t('sub clarify: no override', out_cl is None)
t('sub clarify: entity_ab_skip names src',
  diag_sub_cl.get('entity_ab_skip', '').endswith(':sub_clarify_measure'))

# ── Case A/B/C (pure) ─────────────────────────────────────────────────────────
opts_2 = [
    {'src': 'entity_leader', 'distinct_by': '', 'label': 'Лидер', 'hint': '', 'found': 1},
    {'src': 'entity_rival', 'distinct_by': 'подпись из question', 'label': 'Соперник',
     'hint': '', 'found': 1},
]

caseA = A.entity_ambiguity_ab_sum_case(
    {'entity_leader': 100.0, 'entity_rival': 100.001}, 'entity_leader', opts_2)
t('A: equal after rounding', caseA[0] == 'A')

leader_out = {
    'kind': 'answer',
    'text': '100',
    'figures': {'sum': 100.0},
    'sources': ['some-meta-name'],
    'diag': {'focus': 'entity_leader'},
}
outer_diag = {'fork': {'outcome': 'empty'}, 'arbiter_rivals': ['entity_rival']}
afterA = A.entity_ambiguity_ab_sum_build_out(
    leader_out, outer_diag, caseA[0], signature=caseA[1])

t('A override: kind=answer', afterA.get('kind') == 'answer')
t('A override: no sources names', afterA.get('sources') == [])
t('A override: diag ambiguity entity', afterA.get('diag', {}).get('ambiguity') == 'entity')
t('A override: no luke for A', 'подпись' not in afterA.get('text', ''))

caseB = A.entity_ambiguity_ab_sum_case(
    {'entity_leader': 100.0, 'entity_rival': 101.0}, 'entity_leader', opts_2)
t('B: different numbers + signatures', caseB[0] == 'B')
afterB = A.entity_ambiguity_ab_sum_build_out(
    leader_out, outer_diag, caseB[0], signature=caseB[1])
t('B override: luke contains signature',
  'подпись из question' in afterB.get('text', ''))

opts_no_sig = [
    {'src': 'entity_leader', 'distinct_by': '', 'label': 'Лидер', 'hint': '', 'found': 1},
    {'src': 'entity_rival', 'distinct_by': '', 'label': 'Соперник', 'hint': '', 'found': 1},
]
caseC = A.entity_ambiguity_ab_sum_case(
    {'entity_leader': 100.0, 'entity_rival': 101.0}, 'entity_leader', opts_no_sig)
t('C: different numbers + no signatures', caseC[0] == 'C')
afterC = A.entity_ambiguity_ab_sum_build_out(leader_out, outer_diag, caseC[0])
t('C override: generic other reading message',
  'Есть другое прочтение' in afterC.get('text', ''))

t('after diag entity_ab_case=A', afterA['diag'].get('entity_ab_case') == 'A')

if FAIL:
    print('FAILURES:', FAIL)
    sys.exit(1)

print('OK %d' % PASS)
# report quote for orchestrator
print('REPORT entity_ab_compute=%r entity_ab_skip=%r entity_ab_case=%r' % (
    diag_attempt.get('entity_ab_compute'),
    diag_attempt.get('entity_ab_skip'),
    (out_live or {}).get('diag', {}).get('entity_ab_case'),
))
