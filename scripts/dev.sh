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
# Отметка о полном наборе тестов: хэш коммита. Без неё deploy.sh релиз не соберёт.
STAMP="${REPO}/.git/astrofacts-full-tests"
export DEPLOY_REQUIRE_STAMP="${STAMP}"

# Полный набор: все тесты, включая сверку с независимой реализацией, без единого пропуска.
# Отметка привязана к коммиту, поэтому рабочий каталог должен совпадать с HEAD.
test_full() {
    cd "${REPO}"
    if [[ -n "$(git status --porcelain)" ]]; then
        echo "В рабочем каталоге есть незакоммиченные правки: полный набор проверяет коммит, а не черновик." >&2
        echo "Закоммитьте правки и повторите." >&2
        return 1
    fi
    local sha; sha="$(git rev-parse HEAD)"
    rm -f "${STAMP}"
    ASTROFACTS_REQUIRE_REFERENCE=1 PYTHONDONTWRITEBYTECODE=1 \
        .venv/bin/python -m pytest -q -p no:cacheprovider -W ignore -rs | tee "${STAMP}.log"
    local rc="${PIPESTATUS[0]}" summary
    summary="$(tail -n 1 "${STAMP}.log")"; rm -f "${STAMP}.log"
    (( rc == 0 )) || return "${rc}"
    if grep -q "skipped" <<<"${summary}"; then
        echo "Есть пропущенные тесты — полный набор не засчитан." >&2
        return 1
    fi
    echo "${sha}" > "${STAMP}"
    echo "Полный набор пройден для ${sha:0:12}."
}

ensure_full() {
    [[ "$(cat "${STAMP}" 2>/dev/null || true)" == "$(git -C "${REPO}" rev-parse HEAD)" ]] && return 0
    echo "Коммит ещё не проходил полный набор тестов — запускаю." >&2
    test_full
}

usage() {
    cat <<'USAGE'
Использование: scripts/dev.sh КОМАНДА

  test               тесты в рабочем каталоге (черновик; сверочные могут быть пропущены)
  test-full          полный набор для HEAD без пропусков; ставит отметку, без которой нет выкатки
  deploy [--force]   выкатить текущий коммит (HEAD) на dev: полный набор, сборка, рестарт, откат при сбое
  dry                то же без переключения релиза
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
    test-full) test_full ;;
    deploy)   ensure_full && exec "${REPO}/scripts/deploy.sh" "$@" ;;
    dry)      ensure_full && exec "${REPO}/scripts/deploy.sh" --dry-run "$@" ;;
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
