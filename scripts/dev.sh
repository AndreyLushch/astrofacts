#!/usr/bin/env bash
# Команды dev-инстанса (~/deploy/astrofacts-dev). Работает без make.
set -Eeuo pipefail

REPO="$(cd -- "$(dirname -- "$0")/.." && pwd)"
export DEPLOY_ROOT="${ASTROFACTS_DEV_ROOT:-${HOME}/deploy/astrofacts-dev}"
export DEPLOY_REPO="${REPO}"
export DEPLOY_REF="HEAD"
export DEPLOY_SERVICE="${ASTROFACTS_DEV_SERVICE-astrofacts-dev}"
URL="${ASTROFACTS_DEV_URL:-http://127.0.0.1:8765}"
export DEPLOY_HEALTH_URL="${URL}/health"

usage() {
    cat <<'USAGE'
Использование: scripts/dev.sh КОМАНДА

  test               тесты в рабочем каталоге
  deploy [--force]   выкатить текущий коммит (HEAD) на dev: тесты, рестарт, проверка, откат при сбое
  dry                собрать релиз и прогнать тесты, ничего не переключая
  rollback           вернуть предыдущий релиз
  status             активный и предыдущий релизы, состояние сервиса
  logs [N]           последние N строк журнала сервиса (по умолчанию 50)
  check              /health работающего сервиса
  day ДАТА [TZ] [LOOKAHEAD]   ответ /day работающего сервиса (TZ по умолчанию Europe/Moscow)
USAGE
}

cmd="${1:-}"
[[ $# -gt 0 ]] && shift
case "${cmd}" in
    test)     cd "${REPO}" && PYTHONDONTWRITEBYTECODE=1 exec .venv/bin/python -m pytest -q -p no:cacheprovider -W ignore "$@" ;;
    deploy)   exec "${REPO}/scripts/deploy.sh" "$@" ;;
    dry)      exec "${REPO}/scripts/deploy.sh" --dry-run "$@" ;;
    rollback) exec "${REPO}/scripts/deploy.sh" --rollback ;;
    status)   exec "${REPO}/scripts/deploy.sh" --status ;;
    logs)     exec journalctl -u "${DEPLOY_SERVICE}" --no-pager -n "${1:-50}" ;;
    check)    curl -fsS -m 5 "${URL}/health" && echo ;;
    day)      [[ $# -ge 1 ]] || { usage >&2; exit 2; }
              curl -fsS -m 30 -G "${URL}/day" --data-urlencode "date=$1" \
                  --data-urlencode "tz=${2:-Europe/Moscow}" --data-urlencode "lookahead=${3:-0}" && echo ;;
    -h|--help|help) usage ;;
    *)        usage >&2; exit 2 ;;
esac
