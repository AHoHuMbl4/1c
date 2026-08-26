#!/usr/bin/env bash
# Проба гейта check-gold-split (И5). Офлайн, без сервера/базы/сети.
#
# Случаи (минимум из PLAN_TO_TARGET §И5):
#   1) код ответа + приёмочный набор → стоп
#   2) только код ответа → проходит
#   3) только эталон приёмки с пометкой «Факт 1С:» → проходит
# Дополнительно: только эталон без пометки → стоп (правило §4 п.2).
#
# Запуск: bash work/hooks/test-gold-split.sh
# Код возврата 1 при любом провале. Печатает OK/FAIL и итог N/M.
set -uo pipefail

HOOKS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HOOKS/../.." && pwd)"
FAILED=0
PASSED=0

say() {
  if [ "$1" = 0 ]; then
    printf 'OK   %s\n' "$2"
    PASSED=$((PASSED + 1))
  else
    printf 'FAIL %s\n' "$2"
    FAILED=$((FAILED + 1))
  fi
}

asks() { printf '%s' "$1" | grep -q '"permissionDecision": *"deny"'; }

call() {
  local cmd="$1"
  printf '{"tool_input":{"command":%s}}' \
    "$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$cmd")" \
    | bash "$HOOKS/check-gold-split.sh" 2>/dev/null
}

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# Песочница: свой git + копия GOLD_SETS + lib-hooks рядом со скриптом через CLAUDE_PROJECT_DIR.
# Хук берёт корень из CLAUDE_PROJECT_DIR, а lib-hooks — из каталога скрипта (work/hooks).
mkdir -p "$TMP/ubuntu/serenedb" "$TMP/docs" "$TMP/.claude"
cp "$REPO/docs/GOLD_SETS.md" "$TMP/docs/GOLD_SETS.md"
# Минимальные файлы приёмки и кода (содержимое не важно — гейт смотрит пути).
printf '# acceptance\n**1. «вопрос»**\n' > "$TMP/docs/ACCEPTANCE_UT.md"
printf 'q\texpected\n' > "$TMP/ubuntu/serenedb/ab-acceptance-ambiguous.tsv"
printf 'def answer():\n  return 1\n' > "$TMP/ubuntu/serenedb/serene_ask.py"
printf 'def score():\n  return 0\n' > "$TMP/ubuntu/serenedb/ab_scorer.py"
printf 'x\n' > "$TMP/ubuntu/serenedb/other.py"
printf '# readme\n' > "$TMP/README.md"

cd "$TMP" || exit 1
git init -q .
git config user.email t@t
git config user.name t
git add -A
git commit -qm init

export CLAUDE_PROJECT_DIR="$TMP"

echo "== check-gold-split: И5 =="

# 1) код + приёмка → стоп
printf 'def answer():\n  return 2\n' > ubuntu/serenedb/serene_ask.py
printf '# acceptance\n**1. «вопрос изменён»**\n' > docs/ACCEPTANCE_UT.md
git add ubuntu/serenedb/serene_ask.py docs/ACCEPTANCE_UT.md
OUT=$(call 'git commit -m x -- ubuntu/serenedb/serene_ask.py docs/ACCEPTANCE_UT.md')
asks "$OUT"; say $? 'код + приёмочный набор — останавливает'
git reset -q HEAD

# 2) только код → проходит
printf 'def answer():\n  return 3\n' > ubuntu/serenedb/serene_ask.py
git add ubuntu/serenedb/serene_ask.py
OUT=$(call 'git commit -m x -- ubuntu/serenedb/serene_ask.py')
asks "$OUT"; [ $? = 1 ]; say $? 'только код ответа — проходит'
git reset -q HEAD

# 3) только эталон с пометкой → проходит
printf '# acceptance\n**1. «эталон по 1С»**\n' > docs/ACCEPTANCE_UT.md
git add docs/ACCEPTANCE_UT.md
OUT=$(call 'git commit -m '"'"'правка эталона. Факт 1С: OData Catalog_Nomenclature/$count=42'"'"' -- docs/ACCEPTANCE_UT.md')
asks "$OUT"; [ $? = 1 ]; say $? 'только эталон с пометкой Факт 1С — проходит'
git reset -q HEAD

# 4) только эталон без пометки → стоп
printf '# acceptance\n**1. «эталон без факта»**\n' > docs/ACCEPTANCE_UT.md
git add docs/ACCEPTANCE_UT.md
OUT=$(call 'git commit -m x -- docs/ACCEPTANCE_UT.md')
asks "$OUT"; say $? 'только эталон без пометки — останавливает'
git reset -q HEAD

# 5) код + ambiguous-приёмка → стоп (вторая полка §3)
printf 'def score():\n  return 1\n' > ubuntu/serenedb/ab_scorer.py
printf 'q2\texpected2\n' > ubuntu/serenedb/ab-acceptance-ambiguous.tsv
git add ubuntu/serenedb/ab_scorer.py ubuntu/serenedb/ab-acceptance-ambiguous.tsv
OUT=$(call 'git commit -m x -- ubuntu/serenedb/ab_scorer.py ubuntu/serenedb/ab-acceptance-ambiguous.tsv')
asks "$OUT"; say $? 'ab_scorer + ambiguous-приёмка — останавливает'
git reset -q HEAD

# 6) посторонний файл + приёмка с пометкой → проходит (не код ответа)
printf 'y\n' > ubuntu/serenedb/other.py
printf '# acceptance\n**1. «ok»**\n' > docs/ACCEPTANCE_UT.md
git add ubuntu/serenedb/other.py docs/ACCEPTANCE_UT.md
OUT=$(call 'git commit -m '"'"'доки. Факт 1С: отчёт ОСВ'"'"' -- ubuntu/serenedb/other.py docs/ACCEPTANCE_UT.md')
asks "$OUT"; [ $? = 1 ]; say $? 'не-код-ответа + эталон с пометкой — проходит'
git reset -q HEAD

# 7) посторонний коммит без приёмки → молчит
printf 'z\n' > README.md
git add README.md
OUT=$(call 'git commit -m x -- README.md')
asks "$OUT"; [ $? = 1 ]; say $? 'коммит без приёмки — молчит'
git reset -q HEAD

TOTAL=$((PASSED + FAILED))
echo
echo "Итого: $PASSED/$TOTAL прошло, провалов: $FAILED"
[ "$FAILED" -eq 0 ]
