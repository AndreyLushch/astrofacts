#!/usr/bin/env bash
# Выкатка astrofacts. Один скрипт для dev (вручную, `scripts/dev.sh deploy`) и прода (по таймеру).
#
# Раскладка DEPLOY_ROOT:
#   ephe/                        файлы Swiss Ephemeris — загружаются выкаткой, в git их нет
#   releases/<sha>/              код коммита; .venv — ссылка на venvs/<ключ>
#   venvs/<ключ>/                окружение на версию requirements.lock.txt
#   current -> releases/<sha>    активный релиз, из него запускается сервис
#   repo.git/                    кэш git
#
# Шаги: взять коммит -> собрать релиз -> файлы эфемерид -> тесты -> переключить current ->
# рестарт -> проверка запуска и /health -> откат при сбое. Подробности: deploy/README.md
set -Eeuo pipefail
umask 022

usage() {
    cat <<'EOF'
Использование: scripts/deploy.sh [--dry-run] [--force] [--no-restart] | --rollback | --status

  (без флагов)   выкатить DEPLOY_REF из DEPLOY_REPO, если он новее активного релиза
  --dry-run      собрать релиз и прогнать тесты, ничего не переключая
  --force        выкатить, даже если коммит уже активен, падал раньше или сейчас тихое окно
  --no-restart   переключить релиз, но сервис не перезапускать
  --rollback     вернуть предыдущий релиз и перезапустить сервис
  --status       показать активный и предыдущий релизы

Переменные окружения:
  DEPLOY_ROOT         каталог инстанса (обязательно)
  DEPLOY_REPO         git-репозиторий: URL или локальный путь (обязательно для выкатки)
  DEPLOY_REF          ветка или HEAD (по умолчанию HEAD)
  DEPLOY_SERVICE      systemd-сервис для рестарта; пусто — не перезапускать
  DEPLOY_APP_USER     при запуске от root: пользователь для тестов
  DEPLOY_HEALTH_URL   адрес /health; пусто — проверяется только состояние сервиса
  DEPLOY_WHEELS       каталог с готовым колесом pyswisseph (по умолчанию ~/wheels)
  DEPLOY_NOTIFY_CMD   команда, которой передаётся текст сообщения об исходе выкатки; пусто — молча
  DEPLOY_QUIET        тихое окно "ЧЧ:ММ-ЧЧ:ММ": в это время выкатка откладывается
  DEPLOY_QUIET_TZ     таймзона тихого окна (по умолчанию Europe/Moscow)
  DEPLOY_KEEP         сколько релизов хранить (по умолчанию 5)
  DEPLOY_HEALTH_WAIT  секунд наблюдения за сервисом после рестарта (по умолчанию 20)
  DEPLOY_PYTHON       интерпретатор для venv (по умолчанию python3)
EOF
}

log()  { printf '[deploy] %s\n' "$*"; }
warn() { printf '[deploy] ВНИМАНИЕ: %s\n' "$*" >&2; }
die()  { printf '[deploy] ОШИБКА: %s\n' "$*" >&2; exit 1; }

# ── окружение ────────────────────────────────────────────────────────────────

# Команды приложения (тесты, самопроверка) при запуске от root идут от пользователя сервиса.
as_app() {
    if [[ ${EUID} -eq 0 && -n "${DEPLOY_APP_USER:-}" ]]; then
        runuser -u "${DEPLOY_APP_USER}" -- "$@"
    else
        "$@"
    fi
}

svc() {
    local verb="$1"; shift
    if [[ "${SYSTEMCTL}" != "systemctl" || ${EUID} -eq 0 || "${verb}" != "restart" ]]; then
        "${SYSTEMCTL}" "${verb}" "$@"
    elif ! sudo -n "${SYSTEMCTL}" "${verb}" "$@" 2>/dev/null; then
        # правила sudoers нет: спросить пароль можно только в терминале
        [[ -t 0 ]] || return 1
        sudo "${SYSTEMCTL}" "${verb}" "$@"
    fi
}

current_name() {
    [[ -L "${ROOT}/current" ]] && basename "$(readlink "${ROOT}/current")" || true
}

# У сервиса нет своего канала связи: сообщение уходит внешней командой, если она задана.
notify() {
    [[ -n "${DEPLOY_NOTIFY_CMD:-}" ]] || return 0
    ${DEPLOY_NOTIFY_CMD} "[$(hostname -s)] astrofacts: $*" >/dev/null 2>&1 || warn "уведомление не отправлено"
}

health_ok() {
    [[ -n "${DEPLOY_HEALTH_URL:-}" ]] || return 0
    local i
    for i in 1 2 3 4 5; do
        curl -fsS -m 5 "${DEPLOY_HEALTH_URL}" 2>/dev/null | grep -q '"status":"ok"' && return 0
        sleep 2
    done
    return 1
}

switch_to() {
    ln -sfn "releases/$1" "${ROOT}/current.new"
    mv -Tf "${ROOT}/current.new" "${ROOT}/current"
}

# Сервис считается здоровым, если он активен и за время наблюдения не перезапускался.
service_healthy() {
    local wait="${DEPLOY_HEALTH_WAIT:-20}" pid1 pid2
    sleep 3
    pid1="$(svc show -p MainPID --value "${SERVICE}" 2>/dev/null || echo 0)"
    sleep "$(( wait > 3 ? wait - 3 : 0 ))"
    pid2="$(svc show -p MainPID --value "${SERVICE}" 2>/dev/null || echo 0)"
    svc is-active --quiet "${SERVICE}" && [[ "${pid1}" != "0" && "${pid1}" == "${pid2}" ]] && health_ok
}

restart_and_check() {
    [[ -n "${SERVICE}" ]] || { log "DEPLOY_SERVICE не задан — сервис не перезапускается"; return 0; }
    log "перезапуск ${SERVICE}"
    svc restart "${SERVICE}" || { warn "не удалось перезапустить ${SERVICE} (нужен sudo или правило sudoers)"; return 1; }
    log "наблюдение за сервисом ${DEPLOY_HEALTH_WAIT:-20} с"
    service_healthy
}

in_quiet_window() {
    local spec="${DEPLOY_QUIET:-}" now from to
    [[ "${spec}" =~ ^([0-9]{2}):([0-9]{2})-([0-9]{2}):([0-9]{2})$ ]] || return 1
    from="${BASH_REMATCH[1]}${BASH_REMATCH[2]}"; to="${BASH_REMATCH[3]}${BASH_REMATCH[4]}"
    now="$(TZ="${DEPLOY_QUIET_TZ:-Europe/Moscow}" date +%H%M)"
    (( 10#${now} >= 10#${from} && 10#${now} <= 10#${to} ))
}

# ── сборка релиза ────────────────────────────────────────────────────────────

ensure_venv() {
    local lock="$1/requirements.lock.txt" key venv
    [[ -f "${lock}" ]] || die "в коммите нет requirements.lock.txt"
    key="$( { "${PY}" -V; cat "${lock}"; } | sha256sum | cut -c1-12 )"
    venv="${ROOT}/venvs/${key}"
    if [[ ! -f "${venv}/.ready" ]]; then
        log "новое окружение venvs/${key} (изменились зависимости или версия Python)"
        rm -rf "${venv}"
        "${PY}" -m venv "${venv}"
        # pyswisseph — только из готового колеса: на проде компилятора нет
        "${venv}/bin/pip" install --quiet --disable-pip-version-check \
            --find-links "${WHEELS}" --only-binary pyswisseph -r "${lock}" \
            || die "не удалось собрать окружение (колесо pyswisseph ищется в ${WHEELS})"
        touch "${venv}/.ready"
    fi
    ln -sfn "../../venvs/${key}" "$1/.venv"
}

# Файлы эфемерид общие для всех релизов. Скрипт загрузки ничего не делает, если они на месте
# и контрольные суммы сходятся; иначе скачивает — это единственное обращение выкатки в сеть
# помимо git и pip.
ensure_ephemeris() {
    local dir="$1"
    mkdir -p "${ROOT}/ephe"
    (cd "${dir}" && env PYTHONPATH="${dir}/src" PYTHONDONTWRITEBYTECODE=1 \
        .venv/bin/python tools/fetch_ephemeris.py "${ROOT}/ephe") \
        || die "нет файлов эфемерид в ${ROOT}/ephe и загрузить их не удалось (можно положить вручную, см. deploy/README.md)"
}

build_release() {
    local sha="$1" dir="$2"
    rm -rf "${dir}"
    mkdir -p "${dir}"
    git --git-dir="${ROOT}/repo.git" archive "${sha}" | tar -x -C "${dir}"
    echo "${sha}" > "${dir}/REVISION"
    ensure_venv "${dir}"
}

run_tests() {
    local dir="$1" out
    out="$(mktemp)"
    # чистое окружение: настройки инстанса и секреты в тесты не попадают
    if (cd "${dir}" && as_app env -i PATH="${PATH}" HOME="${TMPDIR:-/tmp}" LANG=C.UTF-8 PYTHONDONTWRITEBYTECODE=1 \
            ASTROFACTS_EPHE_DIR="${ROOT}/ephe" \
            .venv/bin/python -m pytest -q -p no:cacheprovider -W ignore) >"${out}" 2>&1; then
        log "тесты: $(tail -n 1 "${out}")"
        rm -f "${out}"
        return 0
    fi
    tail -n 25 "${out}" >&2
    TEST_SUMMARY="$(tail -n 1 "${out}")"
    rm -f "${out}"
    return 1
}

cleanup() {
    local keep="${DEPLOY_KEEP:-5}" cur prev n=0 name used
    cur="$(current_name)"; prev="$(cat "${ROOT}/.previous" 2>/dev/null || true)"
    while IFS= read -r name; do
        n=$(( n + 1 ))
        if (( n > keep )) && [[ "${name}" != "${cur}" && "${name}" != "${prev}" ]]; then
            rm -rf "${ROOT}/releases/${name}"
        fi
    done < <(ls -1t "${ROOT}/releases" 2>/dev/null)
    # окружения, на которые не ссылается ни один релиз
    used="$(for name in "${ROOT}"/releases/*/.venv; do [[ -L "${name}" ]] && basename "$(readlink "${name}")" || true; done | sort -u)"
    for name in "${ROOT}"/venvs/*/; do
        [[ -d "${name}" ]] || continue
        name="$(basename "${name}")"
        grep -qx "${name}" <<<"${used}" || rm -rf "${ROOT}/venvs/${name}"
    done
}

# ── команды ──────────────────────────────────────────────────────────────────

cmd_status() {
    local cur prev
    cur="$(current_name)"; prev="$(cat "${ROOT}/.previous" 2>/dev/null || true)"
    echo "активный:   ${cur:-нет}"
    echo "предыдущий: ${prev:-нет}"
    echo "релизы:     $(ls -1t "${ROOT}/releases" 2>/dev/null | tr '\n' ' ')"
    [[ -n "${SERVICE}" ]] && echo "сервис:     ${SERVICE} — $(svc is-active "${SERVICE}" 2>/dev/null || true)"
    return 0
}

cmd_rollback() {
    local cur prev
    cur="$(current_name)"; prev="$(cat "${ROOT}/.previous" 2>/dev/null || true)"
    [[ -n "${prev}" && -d "${ROOT}/releases/${prev}" ]] || die "предыдущего релиза нет"
    [[ "${prev}" != "${cur}" ]] || die "предыдущий релиз совпадает с активным"
    log "откат: ${cur} -> ${prev}"
    switch_to "${prev}"
    echo "${cur}" > "${ROOT}/.previous"
    # откаченный коммит не должен вернуться следующим запуском таймера
    cat "${ROOT}/releases/${cur}/REVISION" > "${ROOT}/.failed" 2>/dev/null || true
    if restart_and_check; then
        log "готово: активен ${prev}"
        notify "Откат вручную: активен ${prev}"
    else
        notify "Откат на ${prev}: сервис не поднялся, нужна ручная проверка"
        die "сервис не поднялся после отката"
    fi
}

cmd_deploy() {
    local ref="${DEPLOY_REF:-HEAD}" sha name cur dir built=0 old_prev
    [[ -n "${DEPLOY_REPO:-}" ]] || die "не задан DEPLOY_REPO"

    if (( ! FORCE )) && in_quiet_window; then
        log "тихое окно ${DEPLOY_QUIET} (${DEPLOY_QUIET_TZ:-Europe/Moscow}) — выкатка отложена"
        return 0
    fi

    [[ -d "${ROOT}/repo.git" ]] || git init --quiet --bare "${ROOT}/repo.git"
    git --git-dir="${ROOT}/repo.git" fetch --quiet --no-tags "${DEPLOY_REPO}" "${ref}" \
        || die "не удалось получить ${ref} из ${DEPLOY_REPO}"
    sha="$(git --git-dir="${ROOT}/repo.git" rev-parse FETCH_HEAD)"
    name="${sha:0:12}"
    cur="$(current_name)"
    dir="${ROOT}/releases/${name}"

    if [[ -d "${DEPLOY_REPO}" ]] && [[ -n "$(git -C "${DEPLOY_REPO}" status --porcelain 2>/dev/null)" ]]; then
        warn "в ${DEPLOY_REPO} есть незакоммиченные правки — в релиз они НЕ попадут, выкатывается коммит ${name}"
    fi

    if (( ! FORCE )); then
        if [[ "${name}" == "${cur}" ]]; then
            log "${name} уже активен — выкатывать нечего"
            return 0
        fi
        if [[ "$(cat "${ROOT}/.failed" 2>/dev/null || true)" == "${sha}" ]]; then
            log "${name} уже не прошёл выкатку — пропуск до нового коммита (или --force)"
            return 0
        fi
    fi

    log "выкатка ${name} (${ref} из ${DEPLOY_REPO}); активен: ${cur:-нет}"
    if [[ ! -f "${dir}/.ready" ]]; then
        build_release "${sha}" "${dir}"
        built=1
    fi
    ensure_ephemeris "${dir}"

    if ! run_tests "${dir}"; then
        echo "${sha}" > "${ROOT}/.failed"
        (( built )) && rm -rf "${dir}"
        notify "Выкатка ${name} отменена: тесты не прошли (${TEST_SUMMARY:-нет вывода}). Работает прежний релиз ${cur:-—}."
        die "тесты не прошли — релиз не выкачен, сервис не тронут"
    fi
    "${dir}/.venv/bin/python" -m compileall -q "${dir}/src" >/dev/null
    touch "${dir}/.ready"

    if (( DRY_RUN )); then
        (( built )) && rm -rf "${dir}"
        log "--dry-run: ${name} собран и проверен, переключение не выполнялось"
        return 0
    fi

    old_prev="$(cat "${ROOT}/.previous" 2>/dev/null || true)"
    switch_to "${name}"
    [[ -n "${cur}" && "${cur}" != "${name}" ]] && echo "${cur}" > "${ROOT}/.previous"

    if (( NO_RESTART )); then
        log "--no-restart: ${name} активен, сервис не перезапускался"
    elif ! restart_and_check; then
        echo "${sha}" > "${ROOT}/.failed"
        if [[ -n "${cur}" && "${cur}" != "${name}" && -d "${ROOT}/releases/${cur}" ]]; then
            warn "сервис не поднялся на ${name} — откат на ${cur}"
            switch_to "${cur}"
            if [[ -n "${old_prev}" ]]; then echo "${old_prev}" > "${ROOT}/.previous"; else rm -f "${ROOT}/.previous"; fi
            if svc restart "${SERVICE}" && service_healthy; then
                notify "Выкатка ${name} откачена: сервис не поднялся. Работает прежний релиз ${cur}."
                die "выкатка откачена, работает ${cur}"
            fi
            notify "Выкатка ${name}: сервис не поднялся, откат на ${cur} тоже не помог — нужна ручная проверка."
            die "сервис не поднялся и после отката на ${cur}"
        fi
        notify "Выкатка ${name}: сервис не поднялся, откатываться некуда — нужна ручная проверка."
        die "сервис не поднялся, предыдущего релиза нет"
    fi
    rm -f "${ROOT}/.failed"

    cleanup
    log "готово: активен ${name}"
    notify "Выкачен ${name} (было ${cur:-—})"
}

main() {
    DRY_RUN=0; FORCE=0; NO_RESTART=0
    local action="deploy"
    while (( $# )); do
        case "$1" in
            --dry-run)    DRY_RUN=1 ;;
            --force)      FORCE=1 ;;
            --no-restart) NO_RESTART=1 ;;
            --rollback)   action="rollback" ;;
            --status)     action="status" ;;
            -h|--help)    usage; exit 0 ;;
            *)            usage >&2; exit 2 ;;
        esac
        shift
    done

    [[ -n "${DEPLOY_ROOT:-}" ]] || die "не задан DEPLOY_ROOT"
    mkdir -p "${DEPLOY_ROOT}/releases" "${DEPLOY_ROOT}/venvs"
    ROOT="$(cd "${DEPLOY_ROOT}" && pwd)"
    SERVICE="${DEPLOY_SERVICE:-}"
    SYSTEMCTL="${DEPLOY_SYSTEMCTL:-systemctl}"
    PY="${DEPLOY_PYTHON:-python3}"
    WHEELS="${DEPLOY_WHEELS:-${HOME}/wheels}"
    TEST_SUMMARY=""

    if [[ "${action}" == "status" ]]; then
        cmd_status
        return 0
    fi

    exec 9>"${ROOT}/.deploy.lock"
    flock -n 9 || { log "другая выкатка ещё выполняется"; exit 0; }

    case "${action}" in
        rollback) cmd_rollback ;;
        deploy)   cmd_deploy ;;
    esac
}

main "$@"
