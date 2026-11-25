#!/bin/bash
set -e
airflow db migrate
airflow users create --username admin --password "$AIRFLOW_ADMIN_PASSWORD" \
  --firstname Admin --lastname Lake --role Admin --email admin@exemplo.com >/dev/null 2>&1 \
  || echo "Usuário admin já existe."
# remove o pid de uma parada abrupta, que impediria o webserver de subir
rm -f /opt/airflow/airflow-webserver.pid
airflow scheduler &
exec airflow webserver
