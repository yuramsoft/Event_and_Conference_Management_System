#!/bin/sh
set -e

if [ "${DB_ENGINE:-mysql}" = "mysql" ]; then
  echo "Waiting for MySQL at ${MYSQL_HOST}:${MYSQL_PORT:-3306}..."
  until nc -z "$MYSQL_HOST" "${MYSQL_PORT:-3306}"; do sleep 1; done
fi

# Only the web container runs migrations and collectstatic
if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
  python manage.py migrate --noinput
  python manage.py collectstatic --noinput
fi

exec "$@"
