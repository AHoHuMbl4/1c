#!/usr/bin/env bash
# Персистентные секреты эмбеддера после старта SereneDB (О5, PLAN_WIKI_CHOICE §7).
# Self-heal: DROP всех emb_<DB>_* и qwen, затем CREATE OR REPLACE по EMBED_HOSTS + qwen.
# Запуск: systemd 1c-serene-embed-secrets.service / ExecStartPost serenedb / вручную под root.
set -euo pipefail
cd "$(dirname "$0")" || exit 1

DSN="${SERENEDB_DSN:-host=127.0.0.1 port=7890 user=postgres dbname=postgres}"
export SERENEDB_DSN="$DSN"

fail() { echo "embed_secrets_install: $1" >&2; exit 1; }

[ -n "${EMBED_PATH:-}" ] || fail "не задан EMBED_PATH"
[ -n "${EMBED_MODEL:-}" ] || fail "не задан EMBED_MODEL"

# shellcheck disable=SC1091
[ -f ./box_tune.sh ] && . ./box_tune.sh
if declare -F embed_hosts_form_check >/dev/null 2>&1; then
  embed_hosts_form_check || fail "форма EMBED_HOST(S) неверна"
fi

DB="$(psql "$DSN" -tAc 'SELECT current_database()' 2>/dev/null | tr -cd 'A-Za-z0-9_')"
[ -n "$DB" ] || fail "движок не отвечает, имя базы не получено"

IFS=',' read -r -a _KEYS <<< "${EMBED_API_KEYS:-${EMBED_API_KEY:-${ALIBABA_API_KEYS:-${ALIBABA_API_KEY:-}}}}"
IFS=',' read -r -a _HOSTS <<< "${EMBED_HOSTS:-${EMBED_HOST:-}}"
[ ${#_HOSTS[@]} -gt 0 ] || _HOSTS=("${EMBED_HOST:-}")

PAIRS=()
for _h in "${_HOSTS[@]}"; do
  _h="$(printf '%s' "$_h" | tr -d ' ')"
  [ -z "$_h" ] && continue
  case "$_h" in
    *"|"*) PAIRS+=("$_h") ;;
    *)
      for _k0 in "${_KEYS[@]}"; do
        _k0="$(printf '%s' "$_k0" | tr -d ' ')"
        [ -z "$_k0" ] && continue
        PAIRS+=("$_h|$_k0")
      done
      ;;
  esac
done
[ ${#PAIRS[@]} -gt 0 ] || fail "не задан ни один адрес/ключ эмбеддера (EMBED_HOSTS)"

SQL="$(dirname "$0")/embed_secrets_install.sql"
[ -f "$SQL" ] || fail "нет $SQL"

# Self-heal: осиротевшие emb_<DB>_* / qwen (старый EMBED_HOSTS) ломают count-check.
# Доки: sql/statements/create_secret#syntax-for-drop-secret;
# configuration/secrets_manager#deleting-secrets.
_drop_existing_openai_secrets() {
  local names name
  names="$(psql "$DSN" -tAc \
    "SELECT name FROM duckdb_secrets()
     WHERE type = 'openai'
       AND (name LIKE 'emb_${DB}_%' OR name = 'qwen')" 2>/dev/null || true)"
  while IFS= read -r name; do
    name="$(printf '%s' "$name" | tr -d '[:space:]')"
    [ -z "$name" ] && continue
    case "$name" in
      *[!A-Za-z0-9_]*) fail "неожиданное имя секрета: ${name}" ;;
    esac
    psql "$DSN" -q -v ON_ERROR_STOP=1 \
      -c "DROP SECRET IF EXISTS ${name};" >/dev/null 2>&1 \
      || fail "не удалось удалить секрет ${name}"
  done <<< "$names"
}

apply_secret() {
  local name="$1" host="$2" key="$3"
  psql "$DSN" -q -v ON_ERROR_STOP=1 \
    -v "sec_name=${name}" \
    -v "api_key=${key}" \
    -v "base_url=${host}" \
    -v "embed_path=${EMBED_PATH}" \
    -f "$SQL" >/dev/null 2>&1 || fail "секрет ${name} не создан"
}

_drop_existing_openai_secrets

first_host="" first_key=""
for i in "${!PAIRS[@]}"; do
  host="${PAIRS[$i]%%|*}"
  key="${PAIRS[$i]#*|}"
  host="${host%/}"
  [ -n "$host" ] && [ -n "$key" ] || fail "пустая пара host|key в EMBED_HOSTS"
  apply_secret "emb_${DB}_${i}" "$host" "$key"
  if [ "$i" -eq 0 ]; then
    first_host="$host"
    first_key="$key"
  fi
done

apply_secret "qwen" "$first_host" "$first_key"

want=$(( ${#PAIRS[@]} + 1 ))
got="$(psql "$DSN" -tAc \
  "SELECT count(*) FROM duckdb_secrets()
   WHERE type = 'openai'
     AND (name LIKE 'emb_${DB}_%' OR name = 'qwen')" 2>/dev/null | tr -d '[:space:]')"
[ "${got:-0}" = "$want" ] || fail "ожидали ${want} openai-секретов, в duckdb_secrets()=${got:-?}"

printf '{"base":"%s","secrets":%s,"qwen":1}\n' "$DB" "${#PAIRS[@]}"
