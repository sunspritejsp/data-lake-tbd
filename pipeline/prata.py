"""Prata: dados limpos, tipados e com regras de qualidade aplicadas.

Nada é descartado em silêncio: cada regra é contada, e o que sai da prata vai para
a quarentena. Os problemas da fonte são marcados, não "corrigidos".
"""
import logging

import numpy as np
import pandas as pd
import pyarrow as pa

from pipeline.catalogo import registrar
from pipeline.comum import gravar, ler, ler_bronze
from pipeline.qualidade import Regras

log = logging.getLogger(__name__)

AULAS_POR_CURSO = 20
STATUS = {"Concluido": "Concluído", "Em Andamento": "Em andamento", "Cancelado": "Cancelado"}


def _limpo(textos):
    """Sem espaços nas pontas nem repetidos no meio."""
    return textos.str.strip().str.replace(r"\s+", " ", regex=True)


def _bronze(tabela, dt):
    t = ler_bronze(tabela, dt)
    t = t.select([c for c in t.column_names if not c.startswith("_")])
    # nota_quiz vira double: evita milhões de objetos Decimal na memória
    if "nota_quiz" in t.column_names:
        i = t.column_names.index("nota_quiz")
        t = t.set_column(i, "nota_quiz", t["nota_quiz"].cast(pa.float64()))
    return t.to_pandas(date_as_object=False)


def _prata(tabela, colunas=None):
    return ler("prata", f"{tabela}/", colunas).to_pandas(date_as_object=False)


def _salvar(df, tabela, schema):
    gravar(pa.Table.from_pandas(df, schema=pa.schema(schema), preserve_index=False), "prata", f"{tabela}/")
    registrar("prata", tabela)
    return len(df)


def cadastros(dt, execucao):
    """alunos, cursos, aulas e feriados."""
    r = Regras("cadastros", dt, execucao)

    alunos = _bronze("alunos", dt)
    alunos["nome"] = _limpo(alunos["nome"])
    alunos["email"] = alunos["email"].str.strip().str.lower()
    alunos["coorte"] = alunos["data_cadastro"].dt.strftime("%Y-%m")
    r.add("R01", "alunos", "Aluno com id repetido", "critica", len(alunos), alunos["aluno_id"].duplicated().sum())
    r.add("R02", "alunos", "E-mail fora do formato ou repetido", "critica", len(alunos),
          (~alunos["email"].str.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$") | alunos["email"].duplicated()).sum())
    _salvar(alunos, "alunos", [("aluno_id", pa.int32()), ("nome", pa.string()), ("email", pa.string()),
                               ("data_cadastro", pa.date32()), ("plano_ativo", pa.bool_()),
                               ("coorte", pa.string())])

    aulas = _bronze("modulos_aulas", dt)
    aulas["titulo_aula"] = _limpo(aulas["titulo_aula"])
    cursos = _bronze("cursos", dt)
    for c in ("titulo", "categoria"):
        cursos[c] = _limpo(cursos[c])
    cursos["carga_real_horas"] = (
        cursos["curso_id"].map(aulas.groupby("curso_id")["duracao_minutos"].sum()) / 60).round(2)
    cursos["flag_carga_divergente"] = (cursos["carga_horaria_horas"] - cursos["carga_real_horas"]).abs() > 1
    cursos["flag_titulo_repetido"] = cursos["titulo"].duplicated(keep=False)
    r.add("R03", "aulas", "Aula ligada a um curso que não existe", "critica", len(aulas),
          (~aulas["curso_id"].isin(cursos["curso_id"])).sum())
    r.add("R04", "cursos", f"Curso sem exatamente {AULAS_POR_CURSO} aulas", "critica", len(cursos),
          (cursos["curso_id"].map(aulas.groupby("curso_id").size()) != AULAS_POR_CURSO).sum())
    r.add("R05", "cursos", "Título igual ao de outro curso", "flag", len(cursos), cursos["flag_titulo_repetido"].sum())
    r.add("R06", "cursos", "Carga horária anunciada difere em mais de 1 h da soma das aulas", "flag",
          len(cursos), cursos["flag_carga_divergente"].sum())
    _salvar(cursos, "cursos", [("curso_id", pa.int32()), ("titulo", pa.string()), ("categoria", pa.string()),
                               ("carga_horaria_horas", pa.int32()), ("preco", pa.decimal128(10, 2)),
                               ("carga_real_horas", pa.float64()), ("flag_carga_divergente", pa.bool_()),
                               ("flag_titulo_repetido", pa.bool_())])
    _salvar(aulas, "aulas", [("aula_id", pa.int32()), ("curso_id", pa.int32()), ("titulo_aula", pa.string()),
                             ("ordem_sequencial", pa.int32()), ("duracao_minutos", pa.int32())])

    feriados = _bronze("feriados", dt).rename(columns={"date": "data", "name": "nome", "type": "tipo"})
    feriados["data"] = pd.to_datetime(feriados["data"], format="%Y-%m-%d")
    r.add("R07", "feriados", "Data de feriado repetida", "critica", len(feriados), feriados["data"].duplicated().sum())
    _salvar(feriados, "feriados", [("data", pa.date32()), ("nome", pa.string()), ("tipo", pa.string())])
    r.salvar()


def historico(dt, execucao):
    """Acessos às aulas: 5 milhões de linhas."""
    r = Regras("historico", dt, execucao)
    h = _bronze("historico_aulas", dt)
    total = len(h)

    # 1. duplicatas: fica o menor historico_id; as demais vão para a quarentena
    h = h.sort_values("historico_id", ignore_index=True)
    dup = h.duplicated(["matricula_id", "aula_id", "data_acesso"])
    quarentena = h[dup].assign(motivo="acesso repetido: mesma matrícula, aula e horário")
    r.add("R08", "historico_aulas", "Acesso repetido (mesma matrícula, aula e horário)", "quarentena", total, dup.sum())
    h = h[~dup].reset_index(drop=True)
    campos = [("historico_id", pa.int32()), ("matricula_id", pa.int32()), ("aula_id", pa.int32()),
              ("data_acesso", pa.timestamp("us")), ("segundos_assistidos", pa.int32()),
              ("concluida_flag", pa.bool_()), ("nota_quiz", pa.float64())]
    _salvar(quarentena, "quarentena_historico_aulas", campos + [("motivo", pa.string())])

    # 2. integridade com matrícula e aula
    m = _bronze("matriculas", dt)[["matricula_id", "curso_id", "data_matricula"]]
    a = _prata("aulas", ["aula_id", "curso_id", "duracao_minutos"]).rename(columns={"curso_id": "curso_da_aula"})
    h = h.merge(m, on="matricula_id", how="left").merge(a, on="aula_id", how="left")
    r.add("R09", "historico_aulas", "Acesso sem matrícula ou sem aula correspondente", "critica", len(h),
          (h["curso_id"].isna() | h["curso_da_aula"].isna()).sum())
    r.add("R10", "historico_aulas", "Aula de um curso diferente do curso da matrícula", "critica", len(h),
          (h["curso_id"] != h["curso_da_aula"]).sum())
    r.add("R11", "historico_aulas", "Acesso anterior à data da matrícula", "critica", len(h),
          (h["data_acesso"] < h["data_matricula"]).sum())

    # 3. notas
    r.add("R12", "historico_aulas", "Nota presente sem conclusão, ou conclusão sem nota", "critica", len(h),
          (h["nota_quiz"].notna() != h["concluida_flag"]).sum())
    r.add("R13", "historico_aulas", "Nota fora do intervalo de 0 a 10", "critica", len(h),
          (h["nota_quiz"].lt(0) | h["nota_quiz"].gt(10)).sum())

    # 4. tempo assistido: limitado a 100% e marcado, com o valor original preservado
    duracao_seg = h["duracao_minutos"] * 60
    h["flag_tempo_excedente"] = h["segundos_assistidos"] > duracao_seg
    h["pct_assistido"] = np.minimum(100 * h["segundos_assistidos"] / duracao_seg, 100).round(2)
    r.add("R14", "historico_aulas", "Tempo assistido maior que a duração da aula", "flag", len(h),
          h["flag_tempo_excedente"].sum())

    h["data"] = h["data_acesso"].dt.normalize()
    h["hora"] = h["data_acesso"].dt.hour
    _salvar(h, "historico_aulas", campos + [
        ("curso_id", pa.int32()), ("pct_assistido", pa.float64()), ("flag_tempo_excedente", pa.bool_()),
        ("data", pa.date32()), ("hora", pa.int32())])
    r.salvar()


def matriculas(dt, execucao):
    """Matrículas, com o progresso recalculado a partir dos acessos."""
    r = Regras("matriculas", dt, execucao)
    m = _bronze("matriculas", dt)
    alunos = _prata("alunos", ["aluno_id", "data_cadastro"])
    cursos = _prata("cursos", ["curso_id"])

    r.add("R15", "matriculas", "Matrícula sem aluno ou sem curso correspondente", "critica", len(m),
          (~m["aluno_id"].isin(alunos["aluno_id"]) | ~m["curso_id"].isin(cursos["curso_id"])).sum())
    r.add("R16", "matriculas", "Status fora da lista conhecida", "critica", len(m),
          (~m["status_conclusao"].isin(STATUS)).sum())
    m["status_fonte"] = m["status_conclusao"].map(STATUS)

    cadastro = m["aluno_id"].map(alunos.set_index("aluno_id")["data_cadastro"])
    m["flag_antes_do_cadastro"] = m["data_matricula"] < cadastro
    r.add("R17", "matriculas", "Matrícula anterior ao cadastro do aluno", "flag", len(m),
          m["flag_antes_do_cadastro"].sum())

    # progresso real: aulas distintas, porque a mesma aula pode ser vista várias vezes
    h = _prata("historico_aulas", ["matricula_id", "aula_id", "data_acesso", "concluida_flag"])
    por_matricula = h.groupby("matricula_id")
    distintas = h[["matricula_id", "aula_id"]].drop_duplicates().groupby("matricula_id").size()
    concluidas = (h.loc[h["concluida_flag"], ["matricula_id", "aula_id"]].drop_duplicates()
                  .groupby("matricula_id").size())
    for coluna, serie in {"total_acessos": por_matricula.size(), "aulas_acessadas": distintas,
                          "aulas_concluidas": concluidas}.items():
        m[coluna] = m["matricula_id"].map(serie).fillna(0).astype("int32")
    m["primeiro_acesso"] = m["matricula_id"].map(por_matricula["data_acesso"].min())
    m["ultimo_acesso"] = m["matricula_id"].map(por_matricula["data_acesso"].max())
    m["pct_progresso"] = (100 * m["aulas_concluidas"] / AULAS_POR_CURSO).round(2)
    m["status_calculado"] = np.select(
        [m["total_acessos"] == 0, m["aulas_concluidas"] >= AULAS_POR_CURSO],
        ["Não iniciada", "Concluída"], default="Em andamento")

    # reconciliação: a fonte diz que concluiu, mas os acessos não confirmam
    m["flag_conclusao_sem_evidencia"] = (
        (m["status_fonte"] == "Concluído") & (m["status_calculado"] != "Concluída"))
    r.add("R18", "matriculas", "Status Concluído na fonte sem as 20 aulas concluídas nos acessos", "flag",
          (m["status_fonte"] == "Concluído").sum(), m["flag_conclusao_sem_evidencia"].sum())
    r.add("R19", "matriculas", "Matrícula sem nenhum acesso", "informativa", len(m), (m["total_acessos"] == 0).sum())
    r.add("R20", "alunos", "Aluno sem nenhuma matrícula", "informativa", len(alunos),
          (~alunos["aluno_id"].isin(m["aluno_id"])).sum())

    _salvar(m, "matriculas", [
        ("matricula_id", pa.int32()), ("aluno_id", pa.int32()), ("curso_id", pa.int32()),
        ("data_matricula", pa.date32()), ("status_fonte", pa.string()), ("status_calculado", pa.string()),
        ("total_acessos", pa.int32()), ("aulas_acessadas", pa.int32()), ("aulas_concluidas", pa.int32()),
        ("pct_progresso", pa.float64()), ("primeiro_acesso", pa.timestamp("us")),
        ("ultimo_acesso", pa.timestamp("us")), ("flag_antes_do_cadastro", pa.bool_()),
        ("flag_conclusao_sem_evidencia", pa.bool_())])
    r.salvar()
