FROM apache/superset:3.1.0
USER root
# Dialeto do Trino para SQLAlchemy
RUN pip install --no-cache-dir "trino[sqlalchemy]==0.328.0" "SQLAlchemy<2"
USER superset
