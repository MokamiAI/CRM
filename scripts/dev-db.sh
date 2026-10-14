#!/usr/bin/env bash
# Local PostgreSQL 17 for development and integration tests: port 5433,
# this PC only. Databases: ygt_dev (the app) and ygt_test (tests).
#   scripts/dev-db.sh start | stop | status
# Uses the portable PostgreSQL in $YGT_PG_HOME (default ~/ygt-local):
# pgsql/ (binaries) and data/ (the cluster, made by initdb).
set -euo pipefail
home="${YGT_PG_HOME:-$HOME/ygt-local}"
pg="$home/pgsql/bin"
case "${1:-status}" in
  start)
    # Detached from this terminal, or the server holds its output open.
    "$pg/pg_ctl" -D "$home/data" -l "$home/server.log" -w start > /dev/null 2>&1 < /dev/null
    for db in ygt_dev ygt_test; do
      "$pg/psql" -h localhost -p 5433 -U postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$db'" | grep -q 1 \
        || "$pg/psql" -h localhost -p 5433 -U postgres -qc "CREATE DATABASE $db"
    done ;;
  stop) "$pg/pg_ctl" -D "$home/data" -w stop ;;
  status) "$pg/pg_ctl" -D "$home/data" status ;;
  *) echo "usage: $0 start|stop|status" >&2; exit 2 ;;
esac
