"""Ouro: modelo dimensional (star schema).

                         dim_tempo
                             |
    dim_aluno --- fato_acesso_aula --- dim_aula
         \            |   |            (só nos acessos)
          \       dim_curso
           \          |
            --- fato_matricula --- dim_tempo

- fato_acesso_aula: 1 linha por acesso de uma matrícula a uma aula
- fato_matricula:   1 linha por matrícula, com o progresso acumulado
"""
import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa

from pipeline.catalogo import registrar
from pipeline.comum import consultar, gravar, gravar_arquivo, ler, limpar, LINHAS_POR_ARQUIVO

log = logging.getLogger(__name__)

INICIO, FIM = "2022-01-01", "2025-12-31"
MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto",
         "Setembro", "Outubro", "Novembro", "Dezembro"]
DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
VALIDACAO = Path(__file__).parent.parent / "sql" / "validacao_ouro.sql"


def _prata(tabela, colunas=None):
    return ler("prata", f"{tabela}/", colunas).to_pandas(date_as_object=False)


def _ouro(tabela, colunas=None):
    return ler("ouro", f"{tabela}/", colunas).to_pandas(date_as_object=False)


def _salvar(df, tabela, schema):
    gravar(pa.Table.from_pandas(df, schema=pa.schema(schema), preserve_index=False), "ouro", f"{tabela}/")
    registrar("ouro", tabela)
    return len(df)


def _com_sk(df, sk, ordem, desconhecido):
    """Chave substituta sequencial, independente do id da fonte, e a linha -1 'desconhecido'."""
    df = df.sort_values(ordem, ignore_index=True)
    df.insert(0, sk, np.arange(1, len(df) + 1, dtype="int32"))
    return pd.concat([pd.DataFrame([{sk: -1, **desconhecido}]), df], ignore_index=True)


def dim_aluno():
    d = _prata("alunos").drop(columns="email")  # dado pessoal que nenhuma análise usa
    d = _com_sk(d, "sk_aluno", ["data_cadastro", "aluno_id"], {"aluno_id": -1, "nome": "Desconhecido"})
    return _salvar(d, "dim_aluno", [
        ("sk_aluno", pa.int32()), ("aluno_id", pa.int32()), ("nome", pa.string()),
        ("data_cadastro", pa.date32()), ("plano_ativo", pa.bool_()), ("coorte", pa.string())])


def dim_curso():
    d = _prata("cursos")
    d["faixa_preco"] = pd.cut(d["preco"].astype(float), [0, 200, 400, 600, 800, np.inf], right=False,
                              labels=["1. até R$ 200", "2. R$ 200 a 400", "3. R$ 400 a 600",
                                      "4. R$ 600 a 800", "5. R$ 800 ou mais"]).astype(str)
    d = _com_sk(d, "sk_curso", ["categoria", "titulo", "curso_id"],
                {"curso_id": -1, "titulo": "Desconhecido", "categoria": "Desconhecida", "faixa_preco": "Desconhecida"})
    return _salvar(d, "dim_curso", [
        ("sk_curso", pa.int32()), ("curso_id", pa.int32()), ("titulo", pa.string()), ("categoria", pa.string()),
        ("preco", pa.decimal128(10, 2)), ("faixa_preco", pa.string()), ("carga_horaria_horas", pa.int32()),
        ("carga_real_horas", pa.float64()), ("flag_carga_divergente", pa.bool_()),
        ("flag_titulo_repetido", pa.bool_())])


def dim_aula():
    d = _prata("aulas")
    d = _com_sk(d, "sk_aula", ["curso_id", "ordem_sequencial"], {"aula_id": -1, "titulo_aula": "Desconhecida"})
    return _salvar(d, "dim_aula", [
        ("sk_aula", pa.int32()), ("aula_id", pa.int32()), ("curso_id", pa.int32()), ("titulo_aula", pa.string()),
        ("ordem_sequencial", pa.int32()), ("duracao_minutos", pa.int32())])


def dim_tempo():
    d = pd.DataFrame({"data": pd.date_range(INICIO, FIM)})
    d["sk_data"] = d["data"].dt.strftime("%Y%m%d").astype("int32")
    d["ano"], d["mes"], d["dia"] = d["data"].dt.year, d["data"].dt.month, d["data"].dt.day
    d["trimestre"] = d["data"].dt.quarter
    d["ano_mes"] = d["data"].dt.strftime("%Y-%m")
    d["nome_mes"] = d["mes"].map(lambda m: MESES[m - 1])
    d["num_dia_semana"] = d["data"].dt.weekday + 1
    d["dia_semana"] = d["num_dia_semana"].map(lambda n: f"{n}. {DIAS[n - 1]}")
    d["fim_de_semana"] = d["num_dia_semana"] >= 6
    d["nome_feriado"] = d["data"].map(_prata("feriados").set_index("data")["nome"])
    d["feriado"] = d["nome_feriado"].notna()
    d["dia_util"] = ~(d["feriado"] | d["fim_de_semana"])
    d["tipo_dia"] = np.select([d["feriado"], d["fim_de_semana"]], ["Feriado", "Fim de semana"], "Dia útil")
    i32 = pa.int32()
    return _salvar(d, "dim_tempo", [
        ("sk_data", i32), ("data", pa.date32()), ("ano", i32), ("trimestre", i32), ("mes", i32), ("dia", i32),
        ("ano_mes", pa.string()), ("nome_mes", pa.string()), ("num_dia_semana", i32), ("dia_semana", pa.string()),
        ("fim_de_semana", pa.bool_()), ("feriado", pa.bool_()), ("nome_feriado", pa.string()),
        ("dia_util", pa.bool_()), ("tipo_dia", pa.string())])


def _sk(ids, dim, sk, natural):
    """Troca o id da fonte pela chave substituta; o que não existir na dimensão vira -1."""
    return ids.map(_ouro(dim, [sk, natural]).set_index(natural)[sk]).fillna(-1).astype("int32")


def _sk_data(datas):
    return (datas.dt.year * 10000 + datas.dt.month * 100 + datas.dt.day).astype("int32")


def fato_matricula():
    f = _prata("matriculas")
    f["sk_aluno"] = _sk(f["aluno_id"], "dim_aluno", "sk_aluno", "aluno_id")
    f["sk_curso"] = _sk(f["curso_id"], "dim_curso", "sk_curso", "curso_id")
    f["sk_data_matricula"] = _sk_data(f["data_matricula"])
    # preço de tabela do curso: a fonte não informa quanto foi pago de fato
    f["preco_tabela"] = f["curso_id"].map(_prata("cursos", ["curso_id", "preco"]).set_index("curso_id")["preco"])
    i32 = pa.int32()
    return _salvar(f, "fato_matricula", [
        ("matricula_id", i32), ("sk_aluno", i32), ("sk_curso", i32), ("sk_data_matricula", i32),
        ("status_fonte", pa.string()), ("status_calculado", pa.string()), ("preco_tabela", pa.decimal128(10, 2)),
        ("total_acessos", i32), ("aulas_acessadas", i32), ("aulas_concluidas", i32), ("pct_progresso", pa.float64()),
        ("flag_antes_do_cadastro", pa.bool_()), ("flag_conclusao_sem_evidencia", pa.bool_())])


def fato_acesso_aula():
    f = _prata("historico_aulas")
    f["sk_aluno"] = _sk(
        f["matricula_id"].map(_prata("matriculas", ["matricula_id", "aluno_id"])
                              .set_index("matricula_id")["aluno_id"]),
        "dim_aluno", "sk_aluno", "aluno_id")
    f["sk_curso"] = _sk(f["curso_id"], "dim_curso", "sk_curso", "curso_id")
    f["sk_aula"] = _sk(f["aula_id"], "dim_aula", "sk_aula", "aula_id")
    f["sk_data"] = _sk_data(f["data"])
    i32 = pa.int32()
    schema = pa.schema([
        ("historico_id", i32), ("matricula_id", i32), ("sk_aluno", i32), ("sk_curso", i32), ("sk_aula", i32),
        ("sk_data", i32), ("hora", i32), ("segundos_assistidos", i32), ("pct_assistido", pa.float64()),
        ("concluida_flag", pa.bool_()), ("nota_quiz", pa.float64()), ("flag_tempo_excedente", pa.bool_())])
    limpar("ouro", "fato_acesso_aula/")
    # partição por ano: uma consulta filtrada por ano só lê os arquivos daquele ano
    for ano, grupo in f.groupby(f["data"].dt.year):
        for n, i in enumerate(range(0, len(grupo), LINHAS_POR_ARQUIVO)):
            pedaco = pa.Table.from_pandas(grupo.iloc[i:i + LINHAS_POR_ARQUIVO], schema=schema, preserve_index=False)
            gravar_arquivo(pedaco, "ouro", f"fato_acesso_aula/ano={ano}/parte-{n:05d}.parquet")
    registrar("ouro", "fato_acesso_aula", "ano")
    return len(f)


def validar(dt):
    """Cada consulta devolve (teste, esperado, obtido); qualquer diferença falha a execução."""
    sql = re.sub(r"--.*", "", VALIDACAO.read_text().replace("{dt}", dt))
    resultados = [linha for q in sql.split(";") if q.strip() for linha in consultar(q)]
    for teste, esperado, obtido in resultados:
        log.info("%s %s: esperado %s, obtido %s", "OK   " if esperado == obtido else "FALHA", teste, esperado, obtido)
    falhas = [r for r in resultados if r[1] != r[2]]
    if falhas or not resultados:
        raise ValueError(f"validação da ouro falhou: {falhas or 'nenhum teste executado'}")
    return resultados
