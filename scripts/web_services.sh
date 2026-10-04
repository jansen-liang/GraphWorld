#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_SERVICES_DIR="$ROOT_DIR/.gw-services"
if [[ ! -x "$DEFAULT_SERVICES_DIR/bin/postgres" ]]; then
  for candidate in "${CONDA_PREFIX:-}" "/home/swzz/anaconda3/gra"; do
    if [[ -x "$candidate/bin/postgres" && -x "$candidate/bin/redis-server" ]]; then
      DEFAULT_SERVICES_DIR="$candidate"
      break
    fi
  done
fi
SERVICES_DIR="${GRAPHWORLD_SERVICES_DIR:-$DEFAULT_SERVICES_DIR}"
PG_DATA="$ROOT_DIR/backend/data/web_pg"
PG_LOG="$ROOT_DIR/backend/data/web_postgres.log"
REDIS_DIR="$ROOT_DIR/backend/data/web_redis"
REDIS_LOG="$ROOT_DIR/backend/data/web_redis.log"
PG_PORT="${GRAPHWORLD_PG_PORT:-55432}"
REDIS_PORT="${GRAPHWORLD_REDIS_PORT:-56379}"

export GRAPHWORLD_DATABASE_URL="${GRAPHWORLD_DATABASE_URL:-postgresql+psycopg://graphworld:graphworld@127.0.0.1:${PG_PORT}/graphworld}"
export GRAPHWORLD_REDIS_URL="${GRAPHWORLD_REDIS_URL:-redis://127.0.0.1:${REDIS_PORT}/0}"

require_services() {
  if [[ ! -x "$SERVICES_DIR/bin/postgres" || ! -x "$SERVICES_DIR/bin/redis-server" ]]; then
    echo "Missing local service binaries. Run:"
    echo "  conda create -y -p $SERVICES_DIR postgresql redis"
    exit 1
  fi
}

init_postgres() {
  require_services
  mkdir -p "$ROOT_DIR/backend/data" "$REDIS_DIR"
  if [[ ! -d "$PG_DATA/base" ]]; then
    "$SERVICES_DIR/bin/initdb" -D "$PG_DATA" -U graphworld --auth=trust --encoding=UTF8 --locale=C
  fi
}

start_postgres() {
  init_postgres
  if "$SERVICES_DIR/bin/pg_isready" -h 127.0.0.1 -p "$PG_PORT" -U graphworld >/dev/null 2>&1; then
    return
  fi
  "$SERVICES_DIR/bin/pg_ctl" -D "$PG_DATA" -l "$PG_LOG" -o "-p $PG_PORT -k /tmp" start
  "$SERVICES_DIR/bin/createdb" -h 127.0.0.1 -p "$PG_PORT" -U graphworld graphworld >/dev/null 2>&1 || true
  "$SERVICES_DIR/bin/psql" -h 127.0.0.1 -p "$PG_PORT" -U graphworld -d postgres -c "ALTER USER graphworld PASSWORD 'graphworld';" >/dev/null
  "$SERVICES_DIR/bin/psql" -h 127.0.0.1 -p "$PG_PORT" -U graphworld -d postgres -c "ALTER SYSTEM SET timezone TO 'UTC';" >/dev/null
  "$SERVICES_DIR/bin/pg_ctl" -D "$PG_DATA" reload >/dev/null
}

start_redis() {
  require_services
  mkdir -p "$REDIS_DIR"
  if "$SERVICES_DIR/bin/redis-cli" -p "$REDIS_PORT" ping >/dev/null 2>&1; then
    return
  fi
  "$SERVICES_DIR/bin/redis-server" --port "$REDIS_PORT" --dir "$REDIS_DIR" --daemonize yes --logfile "$REDIS_LOG"
}

case "${1:-status}" in
  init)
    init_postgres
    ;;
  start)
    start_postgres
    start_redis
    echo "GRAPHWORLD_DATABASE_URL=$GRAPHWORLD_DATABASE_URL"
    echo "GRAPHWORLD_REDIS_URL=$GRAPHWORLD_REDIS_URL"
    ;;
  stop)
    require_services
    "$SERVICES_DIR/bin/pg_ctl" -D "$PG_DATA" stop >/dev/null 2>&1 || true
    "$SERVICES_DIR/bin/redis-cli" -p "$REDIS_PORT" shutdown >/dev/null 2>&1 || true
    ;;
  status)
    require_services
    "$SERVICES_DIR/bin/pg_isready" -h 127.0.0.1 -p "$PG_PORT" -U graphworld || true
    "$SERVICES_DIR/bin/redis-cli" -p "$REDIS_PORT" ping || true
    ;;
  env)
    echo "export GRAPHWORLD_DATABASE_URL='$GRAPHWORLD_DATABASE_URL'"
    echo "export GRAPHWORLD_REDIS_URL='$GRAPHWORLD_REDIS_URL'"
    ;;
  *)
    echo "Usage: $0 {init|start|stop|status|env}"
    exit 2
    ;;
esac
