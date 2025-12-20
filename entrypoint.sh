#!/usr/bin/env bash
set -euo pipefail

. /sage/venv/bin/activate

_term() {
  echo "Received SIGTERM, stopping..."
}

_int() {
  echo "Received SIGINT, stopping..."
}

trap _term SIGTERM
trap _int SIGINT

alembic upgrade head

exec sage