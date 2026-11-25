"""Bronze: cópia fiel das fontes em Parquet, sem transformação.

- 5 tabelas do Postgres, lidas em chunks com cursor no servidor
- feriados nacionais da BrasilAPI (segunda fonte)
- partição por dia de ingestão; reexecutar substitui só a partição do dia
"""
import logging
from datetime import date, datetime, timezone

import pandas as pd
import pyarrow as pa
import requests

from pipeline.comum import conectar_postgres, gravar, gravar_arquivo, limpar

log = logging.getLogger(__name__)

CHUNK = 250_000
ANOS_FERIADOS = range(2022, 2026)

SCHEMAS = {
    "alunos": [("aluno_id", pa.int32()), ("nome", pa.string()), ("email", pa.string()),
               ("data_cadastro", pa.date32()), ("plano_ativo", pa.bool_())],
    "cursos": [("curso_id", pa.int32()), ("titulo", pa.string()), ("categoria", pa.string()),
               ("carga_horaria_horas", pa.int32()), ("preco", pa.decimal128(10, 2))],
    "modulos_aulas": [("aula_id", pa.int32()), ("curso_id", pa.int32()), ("titulo_aula", pa.string()),
                      ("ordem_sequencial", pa.int32()), ("duracao_minutos", pa.int32())],
    "matriculas": [("matricula_id", pa.int32()), ("aluno_id", pa.int32()), ("curso_id", pa.int32()),
                   ("data_matricula", pa.date32()), ("status_conclusao", pa.string())],
    "historico_aulas": [("historico_id", pa.int32()), ("matricula_id", pa.int32()), ("aula_id", pa.int32()),
                        ("data_acesso", pa.timestamp("us")), ("segundos_assistidos", pa.int32()),
                        ("concluida_flag", pa.bool_()), ("nota_quiz", pa.decimal128(4, 2))],
    "feriados": [("date", pa.string()), ("name", pa.string()), ("type", pa.string())],
}
METADADOS = [("_ingerido_em", pa.timestamp("us")), ("_fonte", pa.string()), ("_execucao", pa.string())]


def _tabela_arrow(df, tabela, fonte, execucao):
    df["_ingerido_em"] = datetime.now(timezone.utc).replace(tzinfo=None)
    df["_fonte"] = fonte
    df["_execucao"] = execucao
    return pa.Table.from_pandas(df, schema=pa.schema(SCHEMAS[tabela] + METADADOS), preserve_index=False)


def ingerir_postgres(tabela, dt, execucao):
    prefixo = f"{tabela}/dt_ingestao={dt}/"
    colunas = [c for c, _ in SCHEMAS[tabela]]
    conexao = conectar_postgres()
    # REPEATABLE READ: a contagem e a leitura enxergam a mesma foto da tabela
    conexao.set_session(isolation_level="REPEATABLE READ", readonly=True)
    try:
        with conexao.cursor() as c:
            c.execute(f"SELECT count(*) FROM {tabela}")
            esperado = c.fetchone()[0]

        limpar("bronze", prefixo)
        lidas = 0
        # cursor nomeado = cursor no servidor: só um chunk por vez fica na memória
        with conexao.cursor(name=f"ingestao_{tabela}") as c:
            c.itersize = CHUNK
            c.execute(f"SELECT {', '.join(colunas)} FROM {tabela} ORDER BY 1")
            parte = 0
            while linhas := c.fetchmany(CHUNK):
                # dtype=object preserva os tipos do Postgres até o schema do Arrow
                df = pd.DataFrame(linhas, columns=colunas, dtype=object)
                gravar_arquivo(_tabela_arrow(df, tabela, f"postgres/{tabela}", execucao),
                               "bronze", f"{prefixo}parte-{parte:05d}.parquet")
                lidas += len(linhas)
                parte += 1
                log.info("%s: %s de %s linhas", tabela, lidas, esperado)
    finally:
        conexao.close()

    if lidas != esperado:
        raise ValueError(f"{tabela}: a fonte tem {esperado} linhas, mas {lidas} foram gravadas")
    return lidas


def ingerir_feriados(dt, execucao):
    registros = []
    for ano in ANOS_FERIADOS:
        resposta = requests.get(f"https://brasilapi.com.br/api/feriados/v1/{ano}", timeout=30)
        resposta.raise_for_status()
        do_ano = resposta.json()
        if len(do_ano) < 10:
            raise ValueError(f"feriados de {ano}: só {len(do_ano)} registros, resposta suspeita")
        registros += do_ano
    df = pd.DataFrame(registros)[["date", "name", "type"]]
    tabela = _tabela_arrow(df, "feriados", "brasilapi/feriados/v1", execucao)
    return gravar(tabela, "bronze", f"feriados/dt_ingestao={dt}/")


def ingerir(tabela, dt, execucao):
    date.fromisoformat(dt)  # falha cedo se a data vier errada
    if tabela == "feriados":
        return ingerir_feriados(dt, execucao)
    return ingerir_postgres(tabela, dt, execucao)
