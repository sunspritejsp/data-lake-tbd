FROM apache/airflow:2.10.3-python3.11

# pandas, pyarrow, boto3 e psycopg2 já vêm na imagem. Falta só o cliente do Trino.
# O arquivo de constraints garante uma versão compatível com este Airflow.
RUN pip install --no-cache-dir trino \
    --constraint https://raw.githubusercontent.com/apache/airflow/constraints-2.10.3/constraints-3.11.txt

COPY iniciar.sh /opt/airflow/iniciar.sh
ENTRYPOINT ["bash", "/opt/airflow/iniciar.sh"]
