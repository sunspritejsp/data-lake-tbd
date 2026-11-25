"""Registro das tabelas no Hive Metastore, por SQL no Trino.

As tabelas são externas: DROP + CREATE só troca a definição no catálogo e não toca
nos arquivos. Assim, uma mudança de schema vale já na próxima execução.
"""
import io

import pyarrow as pa
import pyarrow.parquet as pq

from pipeline.comum import consultar, listar, s3

BUCKET = {"bronze": "bronze", "prata": "prata", "ouro": "ouro", "qualidade": "warehouse"}


def pasta(camada, tabela):
    return f"qualidade/{tabela}/" if camada == "qualidade" else f"{tabela}/"


def _tipo(t: pa.DataType):
    if pa.types.is_boolean(t):
        return "boolean"
    if pa.types.is_int32(t):
        return "integer"
    if pa.types.is_int64(t):
        return "bigint"
    if pa.types.is_floating(t):
        return "double"
    if pa.types.is_decimal(t):
        return f"decimal({t.precision},{t.scale})"
    if pa.types.is_date(t):
        return "date"
    if pa.types.is_timestamp(t):
        return "timestamp"
    if pa.types.is_string(t) or pa.types.is_large_string(t):
        return "varchar"
    raise TypeError(f"tipo sem mapeamento: {t}")


def registrar(camada, tabela, particao=None):
    """Cria a tabela externa a partir do schema do Parquet mais recente."""
    bucket, prefixo = BUCKET[camada], pasta(camada, tabela)
    chave = sorted(k for k in listar(bucket, prefixo) if k.endswith(".parquet"))[-1]
    corpo = s3().get_object(Bucket=bucket, Key=chave)["Body"].read()
    colunas = [f'"{c.name}" {_tipo(c.type)}' for c in pq.read_schema(io.BytesIO(corpo))]
    opcoes = [f"external_location = 's3a://{bucket}/{prefixo}'", "format = 'PARQUET'"]
    if particao:
        colunas.append(f'"{particao}" varchar')
        opcoes.append(f"partitioned_by = ARRAY['{particao}']")

    consultar(f"CREATE SCHEMA IF NOT EXISTS hive.{camada} "
              f"WITH (location = 's3a://warehouse/schemas/{camada}/')")
    consultar(f"DROP TABLE IF EXISTS hive.{camada}.{tabela}")
    consultar(f"CREATE TABLE hive.{camada}.{tabela} ({', '.join(colunas)}) "
              f"WITH ({', '.join(opcoes)})")
    if particao:
        consultar(f"CALL hive.system.sync_partition_metadata('{camada}', '{tabela}', 'FULL')")
