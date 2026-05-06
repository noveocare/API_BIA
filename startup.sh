#!/bin/bash
python manage.py migrate --noinput
python manage.py collectstatic --noinput
gunicorn API_HR.wsgi:application --bind 0.0.0.0:8000 --workers 2 --timeout 120