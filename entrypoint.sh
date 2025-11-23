#!/usr/bin/env bash

set -e

. /sage/venv/bin/activate

handle_term() {
  echo "Received SIGTERM/SIGINT, shutting down..."

  if [ -n "$app_pid" ]; then
    kill -TERM "$app_pid"
    wait "$app_pid"
  fi

  exit 0
}

trap handle_term SIGTERM SIGINT

app_pid=$!
wait "$app_pid"