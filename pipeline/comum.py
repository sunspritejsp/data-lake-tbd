"""Configuração e acesso a Postgres, S3 (SILO) e Trino, num lugar só."""
import io
import logging
import os

import boto3
import psycopg2
import pyarrow as pa
import pyarrow.parquet as pq
import trino
from botocore.config import Config

log = logging.getLogger(__name__)

LINHAS_POR_ARQUIVO = 500_000


def conectar_postgres():
    return psycopg2.connect(
        host=os.environ.get("PG_HOST", "localhost"),
        port=os.environ.get("PG_PORT", "5433"),
        dbname=os.environ["PG_DB"],
        user=os.environ["PG_USER"],
        password=os.environ["PG_PASSWORD"],
    )


def s3():
    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("S3_ENDPOINT", "http://localhost:9000"),
        aws_access_key_id=os.environ["S3_USER"],
        aws_secret_access_key=os.environ["S3_PASSWORD"],
        region_name="us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def consultar(sql):
    """Executa um comando no Trino e devolve as linhas."""
    conexao = trino.dbapi.connect(
        host=os.environ.get("TRINO_HOST", "localhost"),
        port=int(os.environ.get("TRINO_PORT", "8080")),
        user="pipeline",
    )
    cursor = conexao.cursor()
    cursor.execute(sql)
    return cursor.fetchall()


def listar(bucket, prefixo):
    paginas = s3().get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefixo)
    return [o["Key"] for pagina in paginas for o in pagina.get("Contents", [])]


def limpar(bucket, prefixo):
    """Apaga o que houver no prefixo. É o que torna cada carga idempotente."""
    assert prefixo.endswith("/") and len(prefixo) > 1, "prefixo precisa ser uma pasta"
    cliente = s3()
    for chave in listar(bucket, prefixo):
        cliente.delete_object(Bucket=bucket, Key=chave)


def gravar_arquivo(tabela: pa.Table, bucket, chave):
    buffer = io.BytesIO()
    pq.write_table(tabela, buffer, compression="snappy", coerce_timestamps="us")
    s3().put_object(Bucket=bucket, Key=chave, Body=buffer.getvalue())


def gravar(tabela: pa.Table, bucket, prefixo):
    """Substitui o conteúdo do prefixo pela tabela, dividida em arquivos menores."""
    limpar(bucket, prefixo)
    for n, inicio in enumerate(range(0, max(tabela.num_rows, 1), LINHAS_POR_ARQUIVO)):
        pedaco = tabela.slice(inicio, LINHAS_POR_ARQUIVO)
        gravar_arquivo(pedaco, bucket, f"{prefixo}parte-{n:05d}.parquet")
    log.info("%s linhas -> s3://%s/%s", tabela.num_rows, bucket, prefixo)
    return tabela.num_rows


def ler(bucket, prefixo, colunas=None) -> pa.Table:
    chaves = sorted(k for k in listar(bucket, prefixo) if k.endswith(".parquet"))
    if not chaves:
        raise FileNotFoundError(f"nenhum Parquet em s3://{bucket}/{prefixo}")
    cliente = s3()
    return pa.concat_tables(
        pq.read_table(
            io.BytesIO(cliente.get_object(Bucket=bucket, Key=k)["Body"].read()),
            columns=colunas,
        )
        for k in chaves
    )


def ler_bronze(tabela, dt, colunas=None):
    """Só a partição do dia: as de outros dias são histórico e duplicariam linhas."""
    return ler("bronze", f"{tabela}/dt_ingestao={dt}/", colunas)
