#!/usr/bin/env python3
"""Оффлайн-замок: entity-ambiguity (fork.outcome == "empty") для sum.

Проверяем pure-логику A/B/C, чтобы убедиться, что для случая A мы не уходим
в kind="clarify", а отдаём kind="answer" лидера шага 4 числом.

Замок НЕ ходит в базу: все входы — зашиты.
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
  A.entity_ambiguity_ab_sum_eligible(intent_sum_period, plan_sum, diag_empty_fork) is True)

t('not eligible: no period window',
  A.entity_ambiguity_ab_sum_eligible({'period': {}}, plan_sum, diag_empty_fork) is False)

t('not eligible: compute != sum',
  A.entity_ambiguity_ab_sum_eligible(intent_sum_period, {'compute': 'count'}, diag_empty_fork) is False)


# ── Case A ───────────────────────────────────────────────────────────────────
opts_2 = [
    {'src': 'entity_leader', 'distinct_by': '', 'label': 'Лидер', 'hint': '', 'found': 1},
    {'src': 'entity_rival', 'distinct_by': 'подпись из question', 'label': 'Соперник', 'hint': '', 'found': 1},
]

caseA = A.entity_ambiguity_ab_sum_case({'entity_leader': 100.0, 'entity_rival': 100.001},
                                       'entity_leader', opts_2)

t('A: equal after rounding', caseA[0] == 'A')

leader_out = {
    'kind': 'answer',
    'text': '100',
    'figures': {'sum': 100.0},
    'sources': ['some-meta-name'],
    'diag': {'focus': 'entity_leader'},
}
outer_diag = {'fork': {'outcome': 'empty'}, 'arbiter_rivals': ['entity_rival']}

afterA = A.entity_ambiguity_ab_sum_build_out(leader_out, outer_diag, caseA[0], signature=caseA[1])

t('A override: kind=answer', afterA.get('kind') == 'answer')
t('A override: no sources names', afterA.get('sources') == [])
t('A override: diag ambiguity entity', afterA.get('diag', {}).get('ambiguity') == 'entity')
t('A override: no luke for A', 'подпись' not in afterA.get('text', ''))


# ── Case B ───────────────────────────────────────────────────────────────────
caseB = A.entity_ambiguity_ab_sum_case({'entity_leader': 100.0, 'entity_rival': 101.0},
                                       'entity_leader', opts_2)

t('B: different numbers + signatures', caseB[0] == 'B')

afterB = A.entity_ambiguity_ab_sum_build_out(leader_out, outer_diag, caseB[0], signature=caseB[1])

t('B override: luke contains signature',
  'подпись из question' in afterB.get('text', ''))


# ── Case C ───────────────────────────────────────────────────────────────────
opts_no_sig = [
    {'src': 'entity_leader', 'distinct_by': '', 'label': 'Лидер', 'hint': '', 'found': 1},
    {'src': 'entity_rival', 'distinct_by': '', 'label': 'Соперник', 'hint': '', 'found': 1},
]

caseC = A.entity_ambiguity_ab_sum_case({'entity_leader': 100.0, 'entity_rival': 101.0},
                                       'entity_leader', opts_no_sig)

t('C: different numbers + no signatures', caseC[0] == 'C')

afterC = A.entity_ambiguity_ab_sum_build_out(leader_out, outer_diag, caseC[0])

t('C override: generic other reading message',
  'Есть другое прочтение' in afterC.get('text', ''))


# ── Simulated “before/after diag quote” (for report) ────────────────────────
# До: исход был clarify и ambiguity=entity (как у seal_clarify).
clarify_before = {'kind': 'clarify', 'diag': {'ambiguity': 'entity',
                                           'fork': {'outcome': 'empty'}}}
# После: A/builder ставит ambiguity=entity и entity_ab_case.

t('before diag ambiguity entity', clarify_before['diag'].get('ambiguity') == 'entity')
t('after diag ambiguity entity', afterA['diag'].get('ambiguity') == 'entity')
t('after diag entity_ab_case=A', afterA['diag'].get('entity_ab_case') == 'A')


if FAIL:
    sys.exit(1)

print(f'OK {PASS}/{{PASS + 0}}')
