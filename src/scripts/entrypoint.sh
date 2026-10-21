#!/bin/sh
# Sage container entrypoint.
# Runs migrations then starts sage as a child process.

set -eu

APP_ROOT="${APP_ROOT:-/app}"
cd "${APP_ROOT}/src"

child=0
stopping=0

log() {
    printf '[%s] Entrypoint %s: %s\n' "$(date '+%d.%m.%y-%H:%M')" "$1" "$2"
}

forward() {
    received="$1"
    stopping=1
    if [ "${child}" -ne 0 ] && kill -0 "${child}" 2>/dev/null; then
        log INFO "Received SIG${received}, forwarding to pid ${child} as SIGTERM"
        kill -s TERM "${child}" 2>/dev/null || true
    else
        log INFO "Received SIG${received} with no running child"
    fi
}

trap 'forward TERM' TERM
trap 'forward INT' INT

run() {
    "$@" &
    child=$!
    while :; do
        set +e
        wait "${child}"
        status=$?
        set -e
        if [ "${status}" -gt 128 ] && kill -0 "${child}" 2>/dev/null; then
            continue
        fi
        break
    done
    child=0
    return "${status}"
}

log INFO "Applying database migrations"
status=0
run alembic -c "${APP_ROOT}/alembic.ini" upgrade head || status=$?

if [ "${stopping}" -eq 1 ]; then
    log WARN "Shutdown requested during migrations, not starting Sage"
    exit "${status}"
fi

if [ "${status}" -ne 0 ]; then
    log ERROR "Migrations failed with status ${status}"
    exit "${status}"
fi

log INFO "Starting Sage"
status=0
run python -m main || status=$?

if [ "${status}" -eq 0 ]; then
    log INFO "Sage exited cleanly"
else
    log ERROR "Sage exited with status ${status}"
fi
exit "${status}"
