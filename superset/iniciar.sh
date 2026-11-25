#!/bin/bash
set -e
superset db upgrade
superset fab create-admin --username admin --password "$SUPERSET_ADMIN_PASSWORD" \
  --firstname Admin --lastname Lake --email admin@exemplo.com || true
superset init
exec gunicorn --bind 0.0.0.0:8088 --workers 2 --threads 8 --timeout 120 "superset.app:create_app()"
