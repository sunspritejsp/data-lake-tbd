"""Regras de qualidade: cada etapa da prata registra o que encontrou.

Ações possíveis:
- critica:     não deveria acontecer nunca; se acontecer, a execução falha
- quarentena:  a linha sai da prata e vai para uma tabela própria, com o motivo
- flag:        a linha fica, marcada numa coluna
- informativa: só é contada
"""
import logging
from datetime import datetime, timezone

import pandas as pd
import pyarrow as pa

from pipeline.catalogo import registrar
from pipeline.comum import consultar, gravar_arquivo, limpar

log = logging.getLogger(__name__)

SCHEMA = pa.schema([
    ("regra", pa.string()), ("tabela", pa.string()), ("descricao", pa.string()), ("acao", pa.string()),
    ("linhas_avaliadas", pa.int64()), ("linhas_afetadas", pa.int64()), ("pct_afetado", pa.float64()),
    ("execucao", pa.string()), ("medido_em", pa.timestamp("us")),
])


class Regras:
    def __init__(self, etapa, dt, execucao):
        self.etapa, self.dt, self.execucao, self.linhas = etapa, dt, execucao, []

    def add(self, regra, tabela, descricao, acao, avaliadas, afetadas):
        assert acao in {"critica", "quarentena", "flag", "informativa"}
        avaliadas, afetadas = int(avaliadas), int(afetadas)
        self.linhas.append({
            "regra": regra, "tabela": tabela, "descricao": descricao, "acao": acao,
            "linhas_avaliadas": avaliadas, "linhas_afetadas": afetadas,
            "pct_afetado": round(100 * afetadas / avaliadas, 4) if avaliadas else 0.0,
            "execucao": self.execucao,
            "medido_em": datetime.now(timezone.utc).replace(tzinfo=None),
        })
        log.info("[%s] %s: %s de %s (%s)", regra, descricao, afetadas, avaliadas, acao)

    def salvar(self):
        tabela = pa.Table.from_pandas(pd.DataFrame(self.linhas), schema=SCHEMA, preserve_index=False)
        # um arquivo por etapa: reexecutar a etapa substitui só o dela
        gravar_arquivo(tabela, "warehouse", f"qualidade/regras/dt_ingestao={self.dt}/{self.etapa}.parquet")


def iniciar(dt):
    limpar("warehouse", f"qualidade/regras/dt_ingestao={dt}/")


def verificar(dt):
    """Publica o relatório e falha se alguma regra crítica foi violada."""
    registrar("qualidade", "regras", "dt_ingestao")
    violadas = consultar(
        "SELECT regra, descricao, linhas_afetadas FROM hive.qualidade.regras "
        f"WHERE dt_ingestao = '{dt}' AND acao = 'critica' AND linhas_afetadas > 0")
    if violadas:
        raise ValueError(f"regras críticas violadas: {violadas}")
    return consultar(
        "SELECT regra, acao, linhas_afetadas, pct_afetado FROM hive.qualidade.regras "
        f"WHERE dt_ingestao = '{dt}' ORDER BY regra")


def medir_volumes(dt):
    """Linhas por camada, para comparar bronze, prata e ouro no dashboard."""
    consultas = {
        ("bronze", t): f"SELECT count(*) FROM hive.bronze.{t} WHERE dt_ingestao = '{dt}'"
        for t in ("alunos", "cursos", "modulos_aulas", "matriculas", "historico_aulas", "feriados")
    }
    consultas |= {
        ("prata", t): f"SELECT count(*) FROM hive.prata.{t}"
        for t in ("alunos", "cursos", "aulas", "matriculas", "historico_aulas", "feriados",
                  "quarentena_historico_aulas")
    }
    consultas |= {
        ("ouro", t): f"SELECT count(*) FROM hive.ouro.{t}"
        for t in ("dim_aluno", "dim_curso", "dim_aula", "dim_tempo", "fato_matricula", "fato_acesso_aula")
    }
    linhas = [{"camada": c, "tabela": t, "linhas": consultar(sql)[0][0]} for (c, t), sql in consultas.items()]
    schema = pa.schema([("camada", pa.string()), ("tabela", pa.string()), ("linhas", pa.int64())])
    gravar_arquivo(pa.Table.from_pandas(pd.DataFrame(linhas), schema=schema, preserve_index=False),
                   "warehouse", f"qualidade/volumes/dt_ingestao={dt}/volumes.parquet")
    registrar("qualidade", "volumes", "dt_ingestao")
    return linhas
