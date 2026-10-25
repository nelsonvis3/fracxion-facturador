#!/bin/sh
set -eu
python manage.py migrate --check
python manage.py collectstatic --noinput
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers "${WEB_CONCURRENCY:-3}" --timeout 60 --error-logfile -
